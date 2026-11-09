---
name: interview
description: Records an online job interview locally (microphone + system audio), transcribes it on the user's machine with Whisper and reviews it - questions asked, how the user answered, better answers, new facts about the role and next steps - updating the application log and the profile. Use when the user says they are about to start an interview or call, asks to record, stop or transcribe one, or wants to review / debrief an interview transcript (/interview start, /interview stop, /interview review).
---

# Interview

Records an online interview, transcribes it **locally** and reviews it. The audio never leaves the user's machine: only the transcript text reaches the model.

Talk to the user in their own language. Write `review.md` in the user's language; quotes from the transcript stay in the interview's language.

Golden rule (same as `cv-tailor`): **never invent data**. Improved answers use only facts from the profile (`workspace/profile/`) or from the transcript.

## Tools

The engine lives in `tools/interview-recorder/` (see its `README.md`). Both scripts are self-contained [uv](https://docs.astral.sh/uv/) scripts: `uv run` installs Python 3.12 and the dependencies on first use. Run them from that folder.

- `record.py --out <dir>`: records `me.flac` (microphone) and `them.flac` (system audio via WASAPI loopback). **Windows only.** While running it keeps `<dir>/recording.lock`; it stops when `<dir>/STOP` appears, on Ctrl+C, or after `--seconds N`.
- `record.py --list`: shows which microphone and output device would be used.
- `transcribe.py <dir> --lang <code> [--delete-audio]`: writes `<dir>/transcript.md` with lines like `[00:03:12] THEM: ...` / `[00:03:20] ME: ...`. Uses the NVIDIA GPU if available, otherwise the CPU. The first run downloads several GB (CUDA libraries and the model).

If `uv` is missing, tell the user to install it (`winget install astral-sh.uv`) and stop.

## Where things go

Each interview gets its own folder inside the application's folder:

```
workspace/output/<company>-<role>/interviews/<YYYY-MM-DD>-<stage>/
├── me.flac, them.flac   (deleted after transcribing, unless the user wants to keep them)
├── transcript.md
└── review.md
```

`<stage>` is a short slug for the round (`recruiter`, `technical`, `manager`, `case`, `final`…). If the application has no folder yet, create `workspace/output/<company>-<role>/` with the same slug rules as `cv-tailor`. Everything stays inside `workspace/` (git-ignored).

## /interview start [application] [stage]

1. **Find the application.** Match what the user said against the folders in `workspace/output/` and the rows of `workspace/applications.md`. If it is ambiguous or missing, ask (one short question). Ask for the stage only if it is not obvious.
2. **Check nothing is already recording:** look for `workspace/output/*/interviews/*/recording.lock`. If one exists, tell the user and ask whether to stop it first.
3. **Check the devices:** run `uv run record.py --list` and show the two device names. If the microphone looks like a built-in laptop mic and the output like laptop speakers, warn in one line: without headphones, the interviewers' voices leak into the ME track; use headphones.
4. **Start the recording detached from this session**, so it survives if the editor or the session restarts. From PowerShell:

   ```powershell
   Start-Process -FilePath uv -ArgumentList @('run', '"<abs path>\tools\interview-recorder\record.py"', '--out', '"<abs path to the interview folder>"') -WindowStyle Minimized
   ```

   Then wait until `recording.lock` appears in the folder (up to ~60 s on the first run, while uv installs dependencies). If it does not appear, report the error.
5. **Tell the user**, briefly:
   - recording to `<folder>`; a minimized console window is the recorder;
   - ask the interviewers for consent at the start (e.g. *"Do you mind if I record this for my notes?"*). Recording rules differ by country; some require everyone's consent;
   - when finished: `/interview stop` (or press Ctrl+C in the recorder window if the session is gone).

Do nothing else while the interview runs. Never offer live help or answers during the interview.

## /interview stop

1. Find the running recording (`recording.lock`, see above). If there is none but a folder has `me.flac`/`them.flac` and no `transcript.md`, go straight to step 3.
2. Create the `STOP` file in that folder and wait until `recording.lock` disappears (a few seconds). Report the duration if visible.
3. **Pick the language.** Use the interview's language: the application's CV front matter (`lang:`), the posting, or what the user said; if unsure, ask. Passing `--lang` matters: auto-detection assumes one language per track and garbles the rest.
4. **Make sure no call is running.** Transcribing is heavy (GPU, several CPU cores, a few GB of RAM for an hour of audio) and can make a video call stutter on a modest machine. Never transcribe while any `recording.lock` exists. Ask in one line whether the call is over and nothing else is about to start; if the user has another call soon, leave the audio in place and transcribe later (`/interview stop` again, or "transcribe the pending interview").
5. **Transcribe in the background** (it takes minutes for a long interview; the first run also downloads the model). It runs below normal priority, but heavy work may still feel slower meanwhile:

   ```
   uv run transcribe.py "<folder>" --lang <code> --delete-audio
   ```

   Drop `--delete-audio` only if the user asked to keep the audio. Tell the user it is running; continue with the review when it finishes.
6. Run **/interview review** on the new transcript.

## /interview review [transcript]

Without an argument, use the most recent `transcript.md` without a `review.md` next to it. The user may also paste a transcript or point to one made elsewhere (e.g. Teams' own transcription).

1. **Read the context:** the transcript, the application folder (tailored CV, cover letter, any notes such as company research or earlier reviews), its row in `workspace/applications.md`, and `workspace/profile/`.
2. **Read the transcript critically.** Whisper misspells names, companies and technical terms (e.g. "chunking" may come out as "chunky"); fix obvious ones silently and mark doubtful ones with `[?]`. Ignore hallucinated filler on silences ("Thanks for watching"). ME is the user; THEM can be several interviewers on one track: tell them apart from context when possible.
3. **Write `review.md`** next to the transcript with these sections:
   - **Summary:** who was there (names and roles, if said), the stage, length, overall impression in 2-3 lines.
   - **Questions and answers:** for each substantive question, in order:
     - the question (timestamp + close paraphrase or quote);
     - what the user answered, in 1-3 lines;
     - assessment: did it answer what was asked; structure (STAR for behavioral questions); technical accuracy; concrete examples and metrics; length; missed opportunities;
     - a **better answer** when the original was weak or incomplete, built only from the profile and the transcript. If the best answer needs knowledge the user may not have (a technical concept), explain the concept briefly and say so.
   - **What they told us:** new facts about the role, team, stack, process, compensation, benefits, location or work mode, with timestamps.
   - **Questions the user asked** and what was answered; questions worth asking next time.
   - **Next steps and preparation:** what comes next in the process and what to prepare, most important first.
4. **Propose updates** in one message, one line each, and apply them once the user confirms:
   - `workspace/applications.md`: status (e.g. `interview`) and a short note about this round.
   - **Profile:** new facts the user stated about themselves (achievements, metrics, skills, anecdotes) go to the matching file with `source: interview <company>-<role> (<YYYY-MM-DD>)`, following the rules in `workspace/profile/README.md`. A strong answer can become a reusable entry in `stories.md`.
   - **Application notes:** facts about the company or role go to a notes file in the application folder (an existing one if there is one, such as `company-research.md`).
   - If the agent keeps persistent memory about the user's job search, update it with the process stage and next steps.
5. Finish with the three or four most useful takeaways in the chat, and the path to `review.md`.

## Troubleshooting

- **THEM track is silent:** the call audio is playing on a device other than the Windows default output. Set the headphones as the default output device before starting, and do not switch devices mid-call.
- **Echo or interviewers' voices in the ME track:** no headphones. The review still works; mention it if it confuses who said what.
- **`CUDA unavailable … falling back to CPU`:** transcription still works, just slower. On CPU, `--model medium` or `--model small` is faster at some cost in accuracy.
- **Recording left running** (e.g. the session closed): `/interview stop` finds it through `recording.lock`. If the recorder process died, the FLAC files written so far are still valid; delete the stale `recording.lock` and transcribe.
