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

## Usage

In Claude Code, pass the posting link to the skill:

```
/cv-tailor https://www.linkedin.com/jobs/view/1234567890
```

The agent then:

1. **Reads the posting** (if the link cannot be fetched, e.g. behind a login, it asks you to paste the text).
2. **Compares it with your profile** and classifies each requirement: already on record, a known gap, or unknown.
3. **Asks you about anything unclear** in a single message (e.g. *"The posting asks for Kubernetes — do you use it?"*) and saves your answers to the profile.
4. **Writes the tailored CV and cover letter**, shows you what changed and where each fact comes from, and builds the PDFs once you approve.
5. **Logs the application** in `workspace/applications.md`.

The result lands in its own subfolder, one per posting:

```
workspace/output/<company>-<role>/
├── cv-<company>-<role>.md
├── cv-<company>-<role>.pdf
├── cover-letter-<company>-<role>.md
└── cover-letter-<company>-<role>.pdf
```

Other things you can ask: *"update the Acme application to interview"*, *"add to my profile that I use Terraform"*, or `/profile-audit` to polish the profile for ATS without a specific posting.

## Your workspace

### Profile (`workspace/profile/`)

The profile is the source of truth the CVs are built from. You don't have to fill it in upfront: it **grows over time** as you give the agent information, whether from your initial CV, the answers to its questions on each application, or anything you tell it directly. Every entry records where it came from and when.

| File | What it stores |
|---|---|
| `skills.md` | Technical and management skills, with level and evidence |
| `experience.md` | Achievement bank per role (more bullets than fit in a CV) |
| `projects.md` | Projects, talks and community work |
| `education.md` | Degrees, certifications and languages |
| `stories.md` | Reusable anecdotes and arguments for cover letters |
| `facts.md` | Practical data: contact, location, availability, answers to application forms |
| `gaps.md` | What you confirmed you do **not** know or don't want to highlight, so it is not asked again |
| `audit.md` | State of the ATS audit (`profile-audit`): pending, resolved and dismissed items |

`workspace/cv-base.md` and `workspace/cover-letter-base.md` are the default selection (up to two pages) that each application starts from; the profile can hold much more than fits in a CV.

### Application log (`workspace/applications.md`)

A table with one row per application, most recent first: date, company, role, output folder, posting link, status and notes. `cv-tailor` adds the row when it builds the PDFs, and you update the status yourself or by asking the agent. Statuses:

| Status | Meaning |
|---|---|
| `?` | PDFs generated, sending not confirmed yet |
| `sent` | Application sent |
| `interview` | In the interview process |
| `offer` | Offer received |
| `rejected` | Rejected |
| `dropped` | Decided not to send it |

The log also lets the agent warn you when you already applied to a company, and suggest updating the base CV when the same addition keeps showing up across applications.

## Building PDFs by hand

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
