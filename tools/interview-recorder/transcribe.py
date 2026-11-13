# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#   "faster-whisper>=1.1",
#   "soundfile",
#   "scipy",
#   "nvidia-cublas-cu12==12.*",
#   "nvidia-cudnn-cu12==9.*",
# ]
# ///
"""Transcribe me.flac + them.flac from a recording directory, locally, into transcript.md.

Usage:
    uv run transcribe.py <dir> [--lang en|es|...] [--model large-v3-turbo] [--device cuda|cpu] [--delete-audio]

Each track is transcribed separately with faster-whisper, so "who speaks" comes from
the track (ME / THEM) without diarization. Segments are merged by timestamp into:

    [00:03:12] THEM: How would you approach chunking for a large codebase?
    [00:03:20] ME: ...

Without --lang, the language is detected once from the speech on both tracks together
(a few 30 s windows each) and that single language is used for both tracks. This beats
Whisper's own per-track detection, which can pick a different language for each track
and garble a track that mixes languages. Pass --lang to skip detection.
If CUDA cannot be loaded, it falls back to the CPU (slower, same output).

Transcription is the heavy step (GPU, several CPU cores, up to a few GB of RAM on an
hour of audio). Run it after the call, never during one. It runs below normal priority.
"""
import argparse
import os
import sys
import time
from pathlib import Path

TRACKS = (("ME", "me.flac"), ("THEM", "them.flac"))
MAX_BLOCK_SECONDS = 60  # start a new timestamped block after this, even if the speaker is the same
MAX_GAP_SECONDS = 3  # same speaker after a pause longer than this also starts a new block


def add_cuda_dlls():
    """Make the pip-installed cuBLAS/cuDNN DLLs visible to CTranslate2 on Windows."""
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        return
    for root in spec.submodule_search_locations:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


def lower_priority():
    """Run below normal priority so a video call or other work stays responsive."""
    if sys.platform == "win32":
        import ctypes

        BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    else:
        os.nice(10)


def load_16k(path):
    """Decode with soundfile and resample to 16 kHz mono float32 (avoids PyAV/ffmpeg).

    Works in ~30 s blocks so memory stays at the size of the 16 kHz result (~230 MB per
    hour) instead of the whole file at its native rate (~2 GB peak for an hour at 48 kHz).
    """
    from math import gcd

    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    info = sf.info(path)
    rate = info.samplerate
    g = gcd(rate, 16000)
    up, down = 16000 // g, rate // g
    block = (rate * 30 // down) * down  # multiple of `down`, so blocks resample cleanly
    out = np.empty(int(info.frames * up / down) + up, dtype=np.float32)
    n = 0
    for chunk in sf.blocks(path, blocksize=block, dtype="float32", always_2d=True):
        mono = chunk.mean(axis=1)
        res = mono if rate == 16000 else resample_poly(mono, up, down).astype(np.float32)
        out[n:n + len(res)] = res
        n += len(res)
    return out[:n]


def load_model(name, device):
    from faster_whisper import WhisperModel

    if device == "cuda":
        try:
            return WhisperModel(name, device="cuda", compute_type="int8_float16"), "cuda"
        except Exception as e:  # no NVIDIA GPU, driver or DLL problems
            print(f"CUDA unavailable ({e}); falling back to CPU", flush=True)
    return WhisperModel(name, device="cpu", compute_type="int8"), "cpu"


def detect_language(model, audios, windows=4):
    """Pick one language for the whole interview by summing detection scores over all tracks."""
    scores = {}
    for audio in audios:
        try:
            _, _, probs = model.detect_language(audio, vad_filter=True, language_detection_segments=windows)
        except Exception as e:  # e.g. a silent track: VAD leaves nothing to detect on
            print(f"Language detection skipped a track ({e})", flush=True)
            continue
        for lang, p in probs:
            scores[lang] = scores.get(lang, 0.0) + p
    if not scores:
        return None, 0.0
    lang = max(scores, key=scores.get)
    return lang, scores[lang] / sum(scores.values())


def fmt(t):
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def merge(segments):
    """Join consecutive segments of the same speaker into blocks, keeping blocks short."""
    blocks = []
    for start, end, speaker, text in sorted(segments):
        b = blocks[-1] if blocks else None
        if b and b["speaker"] == speaker and start - b["end"] <= MAX_GAP_SECONDS and end - b["start"] <= MAX_BLOCK_SECONDS:
            b["text"] += " " + text
            b["end"] = end
        else:
            blocks.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return [f"[{fmt(b['start'])}] {b['speaker']}: {b['text']}" for b in blocks]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path, help="recording directory (with me.flac / them.flac)")
    ap.add_argument("--lang", default=None, help="interview language code (en, es, ...); default: detect one language from both tracks")
    ap.add_argument("--model", default="large-v3-turbo", help="faster-whisper model (default: large-v3-turbo)")
    ap.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    ap.add_argument("--delete-audio", action="store_true", help="delete the FLAC files after a successful transcription")
    args = ap.parse_args()

    tracks = [(speaker, args.dir / name) for speaker, name in TRACKS if (args.dir / name).exists()]
    if not tracks:
        sys.exit(f"No me.flac / them.flac found in {args.dir}")
    if (args.dir / "recording.lock").exists():
        sys.exit(f"{args.dir} is still recording (recording.lock exists)")

    lower_priority()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if sys.platform == "win32":
        add_cuda_dlls()

    t = time.time()
    model, device = load_model(args.model, args.device)
    print(f"Model {args.model} on {device} loaded in {time.time() - t:.1f} s", flush=True)

    audios = {speaker: load_16k(path) for speaker, path in tracks}
    lang = args.lang
    if not lang:
        lang, share = detect_language(model, audios.values())
        print(f"Detected language: {lang} ({share:.0%} of the detection score)" if lang
              else "Language detection found no speech; Whisper will detect per track", flush=True)

    segments = []
    for speaker, _ in tracks:
        t = time.time()
        segs, info = model.transcribe(audios[speaker], language=lang, vad_filter=True, beam_size=5)
        segs = list(segs)
        print(f"{speaker}: {info.duration:.0f} s of audio, lang={info.language} ({info.language_probability:.2f}), "
              f"{len(segs)} segments in {time.time() - t:.1f} s", flush=True)
        segments += [(s.start, s.end, speaker, s.text.strip()) for s in segs]

    out = args.dir / "transcript.md"
    out.write_text("# Transcript\n\n" + "\n\n".join(merge(segments)) + "\n", encoding="utf-8")
    print(f"Wrote {out} (language: {lang or 'per track'})")

    if args.delete_audio:
        for _, path in tracks:
            path.unlink()
        print("Deleted the audio files")


if __name__ == "__main__":
    main()
