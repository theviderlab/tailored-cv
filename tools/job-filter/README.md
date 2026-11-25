# Job filter

Stage 1 of the `job-inbox` skill: decides which postings from your job alerts deserve a closer look. It deduplicates them against what you have already seen or applied to, and applies the rules in the front matter of `workspace/jobs/criteria.md`. It never calls the model and never touches the network.

## Why a script

The model reads each alert and extracts its postings with normalized fields (role family, seniority, work mode, country, salary…). The decision itself is left to this script, so that:

- the same postings with the same criteria always give the same result;
- every rejection names the rule that caused it and can be audited later with `--explain`;
- missing data **never** rejects a posting: that is guaranteed by code, not by a prompt.

The model maintains the rules with you (it proposes changes as diffs to the front matter and applies them only when you confirm), but it does not apply them.

## Usage

```sh
cd tools/job-filter
uv run job_filter.py ../../workspace/jobs/extracted/<mail-id>.json...   # filter, print JSON, change nothing
uv run job_filter.py <extracted.json>... --update-seen                   # ...and record the results in jobs/seen.json
uv run job_filter.py <posting.json> --recheck --update-seen              # second pass, with the full posting
uv run job_filter.py --explain linkedin-4492981823                       # how each rule judges a recorded posting
uv run job_filter.py --report [--days 7]                                 # what the inbox shows (JSON)
```

All of them take `--workspace DIR` (default: `workspace/` at the repo root), and `--criteria`, `--seen`, `--applications` to point at other files. `--date YYYY-MM-DD` sets the date recorded in `seen.json` (default: today). `uv` installs the only dependency, PyYAML, by itself.

Try it on the demo:

```sh
uv run job_filter.py --workspace ../../examples/alex-morgan --seen /tmp/seen.json ../../examples/alex-morgan/jobs/extracted/d02af533b6b7.json
```

## Input: extracted postings

One JSON file per job alert, `workspace/jobs/extracted/<mail-id>.json`, holding a list of postings. Pass the files oldest mail first: a posting that appears again later in the same run is a duplicate of the first one.

| Field | Values |
|---|---|
| `source` | Portal, lowercase: `linkedin`, `indeed`, `infojobs`, `tecnoempleo`, `experteer`… |
| `job_id` | The portal's ID. If it is missing, it is taken from `url` for known portals (LinkedIn, Indeed, InfoJobs, Tecnoempleo, Glassdoor, Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Wellfound, Welcome to the Jungle). |
| `url`, `title`, `company`, `location`, `salary_text`, `posted`, `applicants`, `easy_apply` | As the mail shows them. |
| `title_en` | The title in English. |
| `role_family` | One of the families in `criteria.md`, or `other`. |
| `seniority` | `intern`, `junior`, `mid`, `senior`, `lead`, `director`, `vp` |
| `modality` | `remote`, `hybrid`, `onsite` |
| `country` | ISO code (`ES`, `PT`), or a region for remote roles: `EU`, `EMEA`, `EUROPE`, `WORLD` |
| `city` | City name, as written in `criteria.md` (accents and case do not matter). |
| `contract` | `employee`, `contractor`, `freelance` |
| `salary_min`, `salary_max`, `salary_currency`, `salary_period` | Numbers, ISO currency (`EUR`), and `year`, `month`, `day` or `hour`. Only for **published** salaries; a portal's estimate goes in `salary_text`. |

What the mail does not say is `null`. A value outside its list or of the wrong type (`"seniority": "mid-senior"`, `"salary_min": "60K"`) is treated as `null` and reported in `missing` and `invalid`. So is a salary that is not plausible for its period (under 1,000 a year, 100 a month, 10 a day or 1 an hour), such as LinkedIn's "30 €-45 € / year" for what is really an hourly rate, and a minimum above the maximum.

## Deduplication

Each posting gets a key: `<source>-<job_id>`, or, without an ID, `<source>-<company>-<title>` (plus the city when there is no company either).

- **`duplicate`**: the same posting is already in `seen.json`, in `applications.md`, or earlier in the run. It is skipped; only the date and mail are added to `seen.json`. Two postings are the same when their source and ID match; when either has no ID, when company and title match after normalization (lowercase, no accents or punctuation, no legal suffixes like `S.L.` or `GmbH`, no trailing country like `España`).
- **`repost`**: same company as an application, or as a posting in `seen.json` with the same role family, but a different posting. It is **not** dropped: it goes on to the rules and, if none rejects it, to stage 2 with the earlier posting or application and its outcome in `repost_of`.

`applications.md` is read by column position (date, company, role, folder, posting link, status, notes), so its headers can be in any language. The job ID comes from the posting link; rows without a link that identifies the posting are matched by company and role.

## Rules

Set in the front matter of `criteria.md` (template: [`workspace.example/jobs/criteria.md`](../../workspace.example/jobs/criteria.md); example: [`examples/alex-morgan/jobs/criteria.md`](../../examples/alex-morgan/jobs/criteria.md)). Applied in this order; the first that rejects is the `rule_id`. A rule with nothing configured is skipped.

| `rule_id` | Rejects when… | When the data is missing |
|---|---|---|
| `role_family` | `role_family` is in `role_families.exclude`, or `include` is set and it is not there | `other` or `null` → `maybe` |
| `title_exclude` | `title` or `title_en` contains a word or phrase of `title_exclude` (whole words, ignoring case and accents) | — |
| `seniority` | `seniority` is in `seniority.exclude` | `maybe` |
| `location` | Remote: `country` is not in `remote.countries`. The list is literal: a remote role in `ES` does not match `EU`, so list every country and region you accept. The city is ignored, since portals sometimes show your own city on remote roles. Hybrid and on-site: `city` is not in `onsite.cities` | `maybe` |
| `salary_floor` | The published salary (`salary_max`, or `salary_min` without a maximum), made yearly with `salary_floor.annualize`, is below the floor for its work mode and currency. With no work mode, the lowest floor in that currency is used | No salary, no floor in that currency, no period or currency, or a `contractor`/`freelance` rate (judged in stage 2, not against a yearly salary) → the rule does not apply |
| `company_blocklist` | The normalized company is in `company_blocklist` | — |

Decisions: `pass` · `maybe` (a rule lacked its data; it goes on) · `reject` · `duplicate` · `repost`. When in doubt, it passes.

The monthly factor defaults to 14 (Spain's 14 payments), the most lenient: a monthly figure is never made to look smaller than it is.

## Output

```json
{
  "results": [
    {
      "key": "linkedin-9900000112",
      "mail_id": "d02af533b6b7",
      "title": "Senior Python Engineer",
      "company": "Veridian Ledger",
      "decision": "reject",
      "rule_id": "salary_floor",
      "reason": "62000 EUR/year is below the remote floor of 65000 EUR",
      "missing": [],
      "invalid": {},
      "duplicate_of": null,
      "repost_of": []
    }
  ],
  "counts": {"pass": 1, "maybe": 10, "repost": 1, "reject": 10, "duplicate": 2}
}
```

## `seen.json`

With `--update-seen`, each posting is recorded under its key in `workspace/jobs/seen.json`: the dates and mails it was seen in, its fields (never the posting text), and the filter decision (with `repost_of` for a repost). The skill adds the stage 2 recommendation, your decision and the path of the saved posting (`recommendation`, `user_decision`, `user_reason`, `posting_path`). This is what keeps deduplication and `--explain` working after the mail has been deleted.

`--recheck` is the second pass of stage 2: once the full posting has been read, the model corrects or completes the fields (real work mode, city, salary, contract) and the posting is judged again. The new fields are merged over the recorded ones, the posting is not treated as a duplicate of itself, and the decision is recorded as `pass: 2`.

## `--explain`

```text
linkedin-9900000112 · Senior Python Engineer · Veridian Ledger
Seen: 2026-11-25 (mails: d02af533b6b7)
Recorded decision: reject (salary_floor) on 2026-11-25, pass 1: 62000 EUR/year is below the remote floor of 65000 EUR
With the current criteria: reject (salary_floor)

  role_family        pass    role family 'backend-python' is wanted  [backend-python]
  title_exclude      pass    no excluded word in the title  [Senior Python Engineer / Senior Python Engineer]
  seniority          pass    seniority 'senior' is accepted  [senior]
  location           pass    remote from EU, which is accepted  [remote · EU]
  salary_floor       reject  62000 EUR/year is below the remote floor of 65000 EUR  [55000 62000 EUR year]
  company_blocklist  skip    no companies blocked  [Veridian Ledger]
```

It reads the fields from `seen.json` and judges them with the current criteria, so it also shows what a change to the rules would do.

## `--report`

What the skill needs to rebuild `workspace/jobs/inbox.md`, read from `seen.json` alone (so it keeps working after the mails are deleted), as JSON:

- `open`: postings that got through (`pass`, `repost`, `maybe`) and that you have not decided on yet, in the order stage 2 takes them: `pass`, then `repost`, then `maybe`; within each, newest first, then fewest applicants, then fewest missing fields. Expired postings are left out.
- `filtered`: postings rejected in the last `--days` days (default 7), newest first, with rule and reason.
- `counts`: how many of each.

## Tests

```sh
python -m pip install pyyaml   # once
python -m unittest discover -s tools/job-filter -v
```

They filter the demo postings in [`examples/alex-morgan/jobs/extracted/`](../../examples/alex-morgan/jobs/extracted/) against Alex's criteria and application log, checking the outcomes listed in [`examples/alex-morgan/eml/README.md`](../../examples/alex-morgan/eml/README.md), and cover each rule, yearly conversion, regions, invalid values, `duplicate` vs `repost`, the second pass and `--explain` after the mail is gone. They run in CI.
