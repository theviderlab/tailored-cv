# tailored-cv

Tailor your CV and cover letter to each job posting with an AI agent (Claude Code or OpenCode), and generate ATS-optimized PDFs ready to send.

The core idea is a **professional profile that grows with use**: whenever a posting asks for something that is not on record, the agent asks you, saves the answer and reuses it in future applications. It never invents data: everything in the CV comes from your profile or from something you confirmed.

## How it works

| Piece | What it does |
|---|---|
| `.claude/skills/cv-tailor/` | Reads the posting (link or text), matches it against your profile, asks you what is missing, writes the tailored CV and cover letter and generates the PDFs. |
| `.claude/skills/profile-audit/` | Reviews your profile against ATS best practices and asks you the questions needed to improve it. |
| `docs/ats-guidelines.md` | The ATS rules both skills apply. |
| `cv/` | Markdown → PDF build with Node and headless Chrome/Edge. |
| `workspace.example/` | Empty template for your personal workspace. |
| `workspace/` | **Your** workspace: profile, base CV, applications and generated PDFs. It is in `.gitignore`. |

## Getting started

Requirements: Node 18+ and Chrome or Edge installed.

```sh
git clone https://github.com/theviderlab/tailored-cv.git
cd tailored-cv
cp -r workspace.example workspace
cd cv && npm install
```

Then open the project with Claude Code and ask something like *"build my profile from this CV"* (pasting your CV) or straight away *"tailor my CV to this posting: <link>"*. If `workspace/` does not exist, the skill creates it from the template and guides you.

Building a PDF by hand:

```sh
cd cv
npm run cv -- ../workspace/cv-base.md          # ATS-optimized CV
npm run cover -- ../workspace/cover-letter-base.md
```

## Backing up your data (optional, recommended)

`workspace/` stays out of this repo, so you can version it as an independent **private** repo:

```sh
cd workspace
git init
git add .
git commit -m "Initial profile"
gh repo create <your-user>/tailored-cv-workspace --private --source . --push
```

From then on, changes to the tool are committed at the root and changes to your data inside `workspace/`.

### Safety net against leaks

The `.githooks/pre-commit` hook blocks any commit to the tool's repo that includes files from `workspace/` or text matching the patterns in `workspace/.private-patterns` (your name, email, phone…; one per line). Enable it once per clone:

```sh
git config core.hooksPath .githooks
```

## Language

The skills talk to you in your language; the profile is kept in English and the CV content follows the language of the posting. For a CV or cover letter in another language, start the markdown with front matter (`---` / `lang: es` / `---`): the PDF headings come from `cv/i18n.json`, where more languages can be added.
