# Contributing to tailored-cv

Thanks for your interest. Bug reports, ideas, new languages, skill improvements and documentation fixes are all welcome.

For questions or ideas you are not sure about yet, start a thread in [Discussions](https://github.com/theviderlab/tailored-cv/discussions). For bugs and concrete proposals, open an [issue](https://github.com/theviderlab/tailored-cv/issues/new/choose).

## Ground rules

- **Never invent data.** This is the project's core promise: everything in a generated CV traces back to the user's profile or to something they confirmed. Changes to the skills must keep it.
- **No personal data in the repo.** Use the fictional demo in [`examples/alex-morgan/`](examples/alex-morgan/) or made-up text in issues, PRs, tests and screenshots. Never paste your own CV, profile or interview transcripts.
- **Keep it plain.** Markdown in, PDF out, no accounts, no database. Prefer small changes that fit that model.

## Setup

Requirements: Node.js 18+, Chrome or Edge, and Git. On macOS or Linux, point the build at your browser with `CHROME_PATH` (e.g. `export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` or `export CHROME_PATH=$(command -v google-chrome)`).

```sh
git clone https://github.com/<you>/tailored-cv.git
cd tailored-cv
git config core.hooksPath .githooks   # leak protection, see below
cd cv && npm install
```

### Enable the pre-commit hook

`.githooks/pre-commit` blocks commits that include `workspace/` or text matching `workspace/.private-patterns` (one regex per line: your name, email, phone…). Enable it once per clone with `git config core.hooksPath .githooks`, and add your own patterns if you keep a workspace in the same clone.

## Testing your change

There is no unit test suite yet. Build the demo PDFs and check that they still look right and fit their page limits (the CV build fails above 2 pages and the cover letter build fails on overflow):

```sh
cd cv
npm run cv -- ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cv-fieldstone-analytics-senior-python-engineer.md
npm run cover -- ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cover-letter-fieldstone-analytics-senior-python-engineer.md ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cv-fieldstone-analytics-senior-python-engineer.md
```

CI runs the same builds on every pull request. Commit the regenerated demo PDFs only if your change is meant to alter the output.

For skill changes (`.claude/skills/*/SKILL.md`), run the skill end to end on the demo workspace (`cp -r examples/alex-morgan workspace`) with a made-up posting, and describe in the PR what you tried.

## Common contributions

### Adding a language

1. Add a block to [`cv/i18n.json`](cv/i18n.json) with **all** the keys from `en`. Use the standard headings recruiters and ATS expect in that language.
2. Build a demo CV with `CV_LANG=<code>` (or front matter `lang: <code>`) and check the headings.
3. Mention the language in the README's *Languages* section.

### Changing the PDF design

The templates and styles live in [`cv/design/`](cv/design/). The layout is single-column on purpose, for ATS parsing: keep the visual order equal to the reading order, use real text (no images or icons for content) and keep the rules in [`docs/ats-guidelines.md`](docs/ats-guidelines.md).

### Changing a skill

Skills are plain markdown instructions read by the agent. Keep them in English, keep the markdown contract in `cv-tailor` in sync with `cv/build-cv.js`, and update the README if the user-facing behaviour changes.

## Pull requests

- One topic per PR; small PRs get reviewed faster.
- Commit messages: short imperative summary (`Add Portuguese headings`, `Fix overflow check in cover letter`).
- Add a line under *Unreleased* in [`CHANGELOG.md`](CHANGELOG.md) if users will notice the change.
- Fill in the PR template checklist.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
