# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-11-15

### Added

- `interview` skill: records an online interview (microphone and call audio on separate tracks, Windows), transcribes it locally with Whisper and reviews the answers against the profile.
- Interview question bank (`workspace/interview-bank/`): questions grouped by what they test, with the history of each answer and the best answer so far.
- `/interview prep`: a prep sheet for an upcoming interview, with the likely questions you answer worst first.
- Microphone selection and automatic language detection in the recorder.
- `CV_MAX_PAGES` and `CV_SPLIT_FIRST_JOB` for an extended CV on request.
- Fictional demo workspace in `examples/alex-morgan/`, with a tailored CV and cover letter.
- MIT license, contributing guide, security policy, Spanish README, issue and PR templates, `AGENTS.md`.
- CI that builds the demo PDFs on every push and pull request, and Dependabot.

### Changed

- README rewritten: features, screenshots, privacy, limitations and OpenCode usage.

### Fixed

- The pre-commit hook keeps LF line endings on every platform (`.gitattributes`).

## [1.0.0] - 2026-11-06

First stable version of the CV workflow.

### Added

- `cv-tailor` skill: reads a job posting, matches it against the profile, asks only about what is missing, writes the tailored CV and cover letter and logs the application.
- `profile-audit` skill: reviews the profile against ATS best practices and asks what is needed to fix it.
- Professional profile that grows with use (`workspace/profile/`), with the source and date of every entry.
- Single-column, ATS-optimized PDF build for the CV (up to 2 pages) and the cover letter (1 page), with Node and headless Chrome/Edge.
- Multilingual PDF headings (`cv/i18n.json`: English and Spanish).
- Application log with statuses.
- Pre-commit hook that blocks personal data from reaching the public repo.

[Unreleased]: https://github.com/theviderlab/tailored-cv/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/theviderlab/tailored-cv/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/theviderlab/tailored-cv/releases/tag/v1.0.0
