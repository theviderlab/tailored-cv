# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["pyaudiowpatch", "soundfile", "numpy"]
# ///
"""Record the microphone (you) and the system audio (the interviewers) to two FLAC files.

Windows only: system audio is captured through WASAPI loopback, so it works with
Teams, Zoom, Meet or any other app without bots or integrations.

Usage:
    uv run record.py --out <dir> [--seconds N]
    uv run record.py --list

Writes <dir>/me.flac and <dir>/them.flac. Stops after --seconds, on Ctrl+C, or when
a file named STOP appears in <dir>. While recording, <dir>/recording.lock holds the
PID and start time so other tools can find a running recording.

WASAPI loopback delivers no frames while nothing is playing, so the writer pads
silence based on wall-clock time to keep both tracks aligned.
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
import soundfile as sf


def find_devices(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    mic = p.get_device_info_by_index(wasapi["defaultInputDevice"])
    spk = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if not spk.get("isLoopbackDevice"):
        for lb in p.get_loopback_device_info_generator():
            if spk["name"] in lb["name"]:
                spk = lb
                break
        else:
            sys.exit(f"No loopback device found for output '{spk['name']}'")
    return mic, spk


class Track:
    def __init__(self, p, device, path, t0):
        self.rate = int(device["defaultSampleRate"])
        self.channels = max(1, int(device["maxInputChannels"]))
        self.q = queue.Queue()
        self.t0 = t0
        self.written = 0
        self.peak = 0
        self.file = sf.SoundFile(path, "w", samplerate=self.rate, channels=1, format="FLAC")
        self.stream = p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=1024,
            stream_callback=self._callback,
        )
        self.thread = threading.Thread(target=self._writer, daemon=True)
        self.thread.start()

    def _callback(self, data, frames, time_info, status):
        self.q.put((time.monotonic(), data))
        return (None, pyaudio.paContinue)

    def _writer(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            t, data = item
            pcm = np.frombuffer(data, dtype=np.int16).reshape(-1, self.channels)
            mono = pcm.mean(axis=1).astype(np.int16)
            expected_start = int((t - self.t0) * self.rate) - len(mono)
            gap = expected_start - self.written
            if gap > self.rate // 10:  # more than 100 ms missing: pad with silence
                self.file.write(np.zeros(gap, dtype=np.int16))
                self.written += gap
            self.file.write(mono)
            self.written += len(mono)
            self.peak = max(self.peak, int(np.abs(mono).max(initial=0)))

    def close(self, t_end):
        self.stream.stop_stream()
        self.stream.close()
        self.q.put(None)
        self.thread.join()
        tail = int((t_end - self.t0) * self.rate) - self.written
        if tail > 0:
            self.file.write(np.zeros(tail, dtype=np.int16))
            self.written += tail
        self.file.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="output directory")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = until Ctrl+C or STOP file)")
    ap.add_argument("--list", action="store_true", help="show the devices that would be used and exit")
    args = ap.parse_args()

    p = pyaudio.PyAudio()
    mic, spk = find_devices(p)
    print(f"Mic (ME):     {mic['name']} @ {int(mic['defaultSampleRate'])} Hz, {mic['maxInputChannels']} ch")
    print(f"System (THEM): {spk['name']} @ {int(spk['defaultSampleRate'])} Hz, {spk['maxInputChannels']} ch")
    if args.list:
        return
    if not args.out:
        sys.exit("--out is required")

    args.out.mkdir(parents=True, exist_ok=True)
    stop_file = args.out / "STOP"
    lock_file = args.out / "recording.lock"
    stop_file.unlink(missing_ok=True)
    lock_file.write_text(json.dumps({"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds")}))

    t0 = time.monotonic()
    tracks = {
        "me": Track(p, mic, args.out / "me.flac", t0),
        "them": Track(p, spk, args.out / "them.flac", t0),
    }
    print(f"Recording to {args.out} ... (Ctrl+C or create {stop_file} to stop)", flush=True)
    try:
        while not stop_file.exists():
            if args.seconds and time.monotonic() - t0 >= args.seconds:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        t_end = time.monotonic()
        for name, tr in tracks.items():
            tr.close(t_end)
            print(f"{name}: {tr.written / tr.rate:.1f} s, peak {tr.peak} / 32767", flush=True)
        p.terminate()
        stop_file.unlink(missing_ok=True)
        lock_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
