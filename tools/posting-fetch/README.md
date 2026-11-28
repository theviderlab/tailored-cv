# Posting fetch

Downloads the full text of a job posting and saves it verbatim, for stage 2 of the `job-inbox` skill (reading each posting and judging it against your profile) and for `cv-tailor`. It is the first and cheapest way to get a posting's text; when it cannot, the skills fall back to the agent's web fetch tool, then a browser, and only then ask you to paste the text (see [`docs/posting-analysis.md`](../../docs/posting-analysis.md)).

Standard library only, run with [uv](https://docs.astral.sh/uv/). It never calls the model.

## Usage

From the repo root:

```sh
uv run tools/posting-fetch/posting_fetch.py linkedin-9900000110 greenhouse-4100000001   # keys from jobs/seen.json
uv run tools/posting-fetch/posting_fetch.py --url "https://www.linkedin.com/jobs/view/9900000110/"   # a link you gave
```

`--force` downloads again a posting already saved; `--workspace DIR` points at another workspace (default: `workspace/`).

`--check <key>...` only tells whether each posting still takes applications, and saves nothing: the saved posting and its analysis stay as they are. `job-inbox` uses it for postings recommended to apply to that nobody decided on, two weeks after they were analysed (see `job-filter --prune`). Result per posting: `open`, `closed` (the portal says it no longer accepts applications, the page is gone with HTTP 404/410, or its `validThrough` date has passed), `failed` (cannot tell: network error, login wall, too little text) or `unsupported`.

## Which pages it visits

Mail is not trusted (links in it can log you in, unsubscribe you or point anywhere), so for a posting from a mail the URL is never taken as is:

- **LinkedIn**: built from the job ID, `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>`, LinkedIn's public page for logged-out visitors. No login, no cookies.
- **Other portals and ATS** (Tecnoempleo, InfoJobs, Indeed, Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Teamtailor, Personio, Workday…, see `KNOWN_HOSTS`): the clean link `mail-fetch` kept, without tracking parameters, and only on those hosts.
- Anything else, or a posting without a link (Experteer hides them behind opaque redirects): `unsupported`, nothing is requested.

A link you give with `--url` may be on any host, as when you hand a link to `cv-tailor`; tracking parameters are still removed, and login or account pages are refused.

Requests are spaced 1.5 seconds apart.

## What it saves

`workspace/jobs/postings/<key>.md`:

```markdown
---
key: "linkedin-9900000110"
url: "https://www.linkedin.com/jobs/view/9900000110/"
fetched: "2026-11-26"
text_source: "script"
title: "Senior Python Engineer, Data Platform"
company: "Northwind Grid"
location: "Lisbon, Lisbon, Portugal"
posted: "3 days ago"
applicants: "42 applicants"
---

# Senior Python Engineer, Data Platform — Northwind Grid

## Posting

- Location: …

What the portal says about it (portal metadata, often wrong):

- Seniority level: Mid-Senior level
- Employment type: Full-time

<the posting's text, lists as bullets>

## Hidden text

<text the page hides, if any: where injected instructions would be>
```

- On LinkedIn the text is the description and the top card; on other pages, the schema.org `JobPosting` block most ATS publish, or else the text of `<main>`.
- The portal's own labels (LinkedIn's "Seniority level", "Employment type") are kept apart and marked as metadata: they are often wrong (an LLM Engineer role labelled "Internship").
- A posting the portal marks as no longer accepting applications gets `closed: true`.
- The skill later adds its analysis (`## Card`, `## Requirements`) above `## Posting`.

## Output

JSON with one result per posting and the counts:

| `status` | Meaning |
|---|---|
| `saved` | Downloaded and saved (`path`); `closed` says whether it is closed |
| `exists` | Already saved; nothing requested (use `--force` to download again) |
| `failed` | HTTP error, network error, login wall, or too little text (a page built by JavaScript): `reason` says which. The caller tries the next way to get the text. |
| `unsupported` | No link, or a host it does not fetch: nothing requested |

Exit code 2 is an error in the arguments (a key that is not in `seen.json`, a login link).

## Tests

```sh
python -m unittest discover -s tools/posting-fetch -v
```

They use fictional pages in `fixtures/` and a fake web: no network. They run in CI.
