# Interview recorder

Record an online job interview on your PC, transcribe it **locally**, and let the agent review it: the questions you were asked, how you answered, better answers, and what you learned about the role.

It is usually driven by the [`interview` skill](../../.claude/skills/interview/SKILL.md) (`/interview start`, `/interview stop`, `/interview review`, `/interview prep`), but both scripts work on their own.

## Why

During an interview it is hard to take complete notes. Afterwards you are left wondering what exactly they asked, how you answered and whether that was what they were looking for. A transcript fixes that, and the agent can turn it into a debrief and preparation for the next round.

## How it works

1. **Record** (`record.py`): two tracks at once.
   - `me.flac`: your **microphone**.
   - `them.flac`: the **system audio** (whatever the call plays), captured through Windows WASAPI loopback. It works with Teams, Zoom, Meet or any other app, with no bots or integrations.

   Separate tracks answer "who is speaking" (you vs. them) without speaker diarization.
2. **Transcribe** (`transcribe.py`): [faster-whisper](https://github.com/SYSTRAN/faster-whisper) runs on each track, on the GPU if there is one. The segments are merged by timestamp into `transcript.md`:

   ```
   [00:03:12] THEM: How would you approach chunking for a large codebase?

   [00:03:20] ME: ...
   ```
3. **Review**: the `interview` skill reads the transcript and writes `review.md` (questions, answers, assessment, better answers, new facts, next steps), then offers to update `workspace/applications.md` and your profile.

**Privacy:** the audio never leaves your machine. Only the transcript text reaches the model, and everything is stored inside `workspace/`, which is git-ignored.

## Requirements

- **Windows** (system audio capture uses WASAPI loopback).
- [uv](https://docs.astral.sh/uv/): `winget install astral-sh.uv`. The scripts declare their own dependencies ([PEP 723](https://peps.python.org/pep-0723/)); `uv run` installs Python 3.12 and everything else on first use. No venv to manage, and no ffmpeg needed.
- **Optional:** an NVIDIA GPU. The CUDA libraries (cuBLAS, cuDNN) come as pip packages, so nothing has to be installed system-wide. Without a GPU it falls back to the CPU.
- **Headphones**, so your microphone does not pick up the interviewers.

The first transcription downloads several GB (CUDA libraries and the `large-v3-turbo` model); later runs reuse the cache.

## Manual use

```sh
cd tools/interview-recorder

uv run record.py --list                      # which mic and output device will be used, plus all mics
uv run record.py --out <dir>                 # record until Ctrl+C (or until <dir>/STOP exists)
uv run record.py --out <dir> --mic "Pixel"   # record a specific mic (part of its name)
uv run record.py --out <dir> --seconds 60    # quick test

uv run transcribe.py <dir>                   # detects the language, writes <dir>/transcript.md
uv run transcribe.py <dir> --lang es --delete-audio
uv run transcribe.py <dir> --device cpu --model medium
```

**Microphone:** by default the recorder uses the Windows default input, which is not always the one the call app uses (e.g. headset in Teams, webcam as the Windows default). Pass `--mic` with the one the call uses.

**Language:** without `--lang`, the language is detected once from the speech on both tracks together and used for both. That works when you don't know the language in advance. Whisper's own detection works per track and can garble a track. Pass `--lang` when you know it, or to re-run after a wrong detection.

## Reference numbers

Measured on a laptop with a GTX 1650 (4 GB), `large-v3-turbo` in `int8_float16`:

- ~600 MB of VRAM;
- model load: ~9 s (cached);
- transcription: roughly 5-10x faster than real time, so a 45-minute interview takes a few minutes.

## Design notes

- **Silence padding.** WASAPI loopback delivers no frames while nothing is playing. The recorder pads silence based on wall-clock time, so both tracks stay aligned and timestamps match.
- **Stop file.** The recorder stops cleanly when `<dir>/STOP` appears, so the agent (or anything else) can stop a recording that runs detached from the session. `<dir>/recording.lock` (PID and start time) marks a recording in progress.
- **Crash-safe.** FLAC is written in blocks as it records; if the process dies, what was recorded so far is still usable.
- **No PyAV.** Audio is decoded with soundfile and resampled with scipy, because recent PyAV releases broke faster-whisper's own decoder.
- **Transcribe after, not live.** It is simpler and more accurate, and the tool is for debriefing, not for getting help during the interview.

## Consent

Ask at the start, e.g. *"Do you mind if I record this for my notes?"*. Rules differ by country: in some places recording a conversation you take part in is legal for personal use; in others every party must consent. Check yours.

## Ideas for later

- Tell several interviewers apart on the `them` track (e.g. pyannote).
- Support macOS and Linux capture (BlackHole / PulseAudio monitor sources).
