# Security policy

tailored-cv handles personal data (CVs, contact details, interview recordings), so privacy bugs count as security bugs.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through [GitHub's private vulnerability reporting](https://github.com/theviderlab/tailored-cv/security/advisories/new).

Include what you found, how to reproduce it and what an attacker or a leak could expose. Use made-up data in your report. You can expect a first reply within a week. Once a fix is released, you will be credited in the advisory unless you prefer otherwise.

## Supported versions

Only the latest release on `main` receives fixes.

## What is in scope

- Anything that could send a user's workspace data somewhere they did not intend: into a commit, a log, a URL, or a service other than their configured model provider.
- Ways around the pre-commit hook's protection of `workspace/`.
- The PDF build or the recorder running untrusted content as code (e.g. markdown or posting text injected into the HTML template).
- Prompt injection in job postings that makes a skill act against the user (e.g. writing unconfirmed data into the profile or the CV, or exfiltrating it).

## Out of scope

- The data policies of the AI model provider your agent uses.
- Vulnerabilities in Chrome, Edge, Node.js or Python themselves (report them upstream).
