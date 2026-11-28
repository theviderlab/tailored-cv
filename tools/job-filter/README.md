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
uv run job_filter.py --set linkedin-4492981823 stage=analysed recommendation=apply   # record stage 2 results
uv run job_filter.py --set '#23' user_decision=discard "user_reason=on-site"         # record your decision, by number
uv run job_filter.py --release-later                                     # 'later' decisions are to decide again
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

With `--update-seen`, each posting is recorded under its key in `workspace/jobs/seen.json`: the dates and mails it was seen in, its fields (never the posting text), and the filter decision (with `repost_of` for a repost). This is what keeps deduplication and `--explain` working after the mail has been deleted. Nobody edits the file by hand: the stage 2 results and your decisions are recorded with `--set` (below).

**Numbers.** Every posting gets a permanent number `n` when it is first recorded (the highest so far + 1), which the inbox shows and you use to refer to it ("apply 23"). A number never changes and is never reused, so it means the same posting in every run. A `seen.json` from before the numbers gets them on the first run of any command, by `first_seen` and then key.

`--recheck` is the second pass of stage 2: once the full posting has been read, the model corrects or completes the fields (real work mode, city, salary, contract) and the posting is judged again. The new fields are merged over the recorded ones, the posting is not treated as a duplicate of itself (nor is the file counted as a mail it was seen in), and the decision is recorded as `pass: 2`.

## `--set`

`--set <key> field=value...` records the outcome of stage 2, or your decision, for a posting already in `seen.json`. The key may also be the posting's number, `#23`. Every value is checked; `null` clears a field. The output lists in `also_set` the other postings of the same job that got the change (see `same_as`).

| Field | Values |
|---|---|
| `stage` | `filtered` (stage 1 done, waiting for stage 2) · `pending_text` (the posting's text could not be fetched: paste it) · `analysed` · `expired`. Changing it records `stage_date`. |
| `recommendation` | `apply` · `apply_with_reservations` · `discard` |
| `knockouts` | Number of unmet must-haves that admit no alternative |
| `must_covered` | Share of must-have requirements covered, 0–1 |
| `fit` | How well the core of the role matches the search: `high` · `medium` · `low` |
| `posting_path` | The saved posting, relative to the workspace; it must exist |
| `same_as` | Another key in `seen.json`: the same job posted twice, which shares its analysis |
| `user_decision`, `user_reason` | `apply` · `discard` · `later`, and why. Records `user_decision_date`; a new decision without a reason clears the old reason. |
| `closed` | `true` · `false`: what `posting-fetch --check` said. Records `closed_checked`. |

`user_decision`, `user_reason` and `posting_path` are shared by the postings of one job: set on a posting, they are copied to every posting whose `same_as` points to it; set on one with `same_as`, to the posting it points to and its other aliases.

`--release-later` clears every `later` decision (and its reason), so those postings are back in `to_decide`. The skill runs it at the start of each full run: "later" means "not in this run".

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

What the skill needs to rebuild `workspace/jobs/inbox.md`, read from `seen.json` (so it keeps working after the mails are deleted) and `applications.md`, as JSON. It never writes anything:

Every item carries its number `n`.

- `to_apply`: postings you decided to apply to that `cv-tailor` has not moved into an application folder yet (`posting_path` not under `output/`), oldest decision first. Aliases (`same_as`) are left out.

The other lists leave out the postings you have decided on and the expired ones:

- `to_decide`: postings analysed in stage 2, by recommendation (`apply`, `apply_with_reservations`, `discard`), then fewest knock-outs, highest share of must-haves covered and best fit. A posting the second pass rejected stays here as a `discard`, citing the rule, so you can disagree.
- `open`: the stage 2 queue, postings that got through stage 1 (`pass`, `repost`, `maybe`) and are not analysed yet: `pass`, then `repost`, then `maybe`; within each, newest first, then fewest applicants, then fewest missing fields.
- `pending_text`: postings whose text could not be fetched, in the same order.
- `filtered`: postings rejected by stage 1 in the last `--days` days (default 7), newest first, with rule and reason.
- `applied`: postings that would be in `to_apply`, `to_decide`, `open` or `pending_text` but already have a row in `applications.md` (same job ID from the row's link, or same company and role), with that row. This covers an application made outside `cv-tailor` (Easy Apply, the company's site): the posting leaves the other lists as soon as its row is added.
- `counts`: how many of each.

Items of `to_decide` and `pending_text` carry `expires`: the day `--prune` will expire them if nothing changes (`null` when it cannot tell, e.g. a posting to apply to that was open when last checked).

## `--prune`

Retention, run by the skill at the start of each full run (after `--release-later`). The mail is only the vehicle: once a posting has been filtered or analysed, what matters is in `seen.json`, the saved posting and the application folder. `--dry-run` says what it would do and changes nothing; `--date` simulates another day.

| What | When |
|---|---|
| A processed job alert in `mail/inbox/` and its `jobs/extracted/<mail-id>.json` | 10 days after the date in its file name, once every posting in it is done with it: rejected or duplicate in stage 1, analysed, expired or decided on. Postings still in the stage 2 queue or waiting for their text keep it (`alerts_waiting`). |
| A posting waiting for its text (`pending_text`) | Expires 30 days after it got there |
| An analysed posting recommended `discard` that you did not decide on | Expires 10 days after the analysis |
| An analysed posting recommended `apply` / `apply_with_reservations` that you did not decide on (also `later`, which is released before) | From 14 days after the analysis it is listed in `to_check`: the skill asks `posting-fetch --check`, records the answer with `--set <key> closed=true\|false` and runs `--prune` again. It expires when it is closed. One that cannot be checked (no supported link, or the checks keep failing for a week) expires at 30 days. |
| The saved posting (`jobs/postings/<key>.md`) | Deleted when the posting expires, 10 days after you discarded it, or right away for an alias (`same_as`) that uses the other posting's card. `posting_path` is cleared. Postings you applied to are never touched. |
| `jobs/extracted/*.json` without its mail, and leftovers (`manual-*`, `recheck-*`) | Deleted |

An expired posting keeps its fields and gets `expired_reason`; it leaves the inbox but is still deduplicated, and you can still decide on it by number. A posting whose `posting_path` points to a missing file gets it cleared (`missing_files`); if it was analysed and undecided, it goes back to the stage 2 queue (`requeued`). A saved posting of a key that is not in `seen.json` is only reported (`unreferenced_postings`). `expiring_soon` lists the postings that expire within 7 days, so the skill can warn you. Messages and process updates are never touched: the skill deletes them when they are resolved.

## `--calibration`

What the skill needs to propose changes to `criteria.md`, from the last `--days` days (default 90), without reading `seen.json` whole: `against_recommendation` (your apply or discard against the recommendation, with your reason), `user_discards`, `other_family` (postings with `role_family` other or null: candidates for a new family) and `rejections_by_rule` (stage 1 rejections per rule, with up to 10 examples). It never writes anything; the skill proposes, and changes `criteria.md` only when you agree.

## Tests

```sh
python -m pip install pyyaml   # once
python -m unittest discover -s tools/job-filter -v
```

They filter the demo postings in [`examples/alex-morgan/jobs/extracted/`](../../examples/alex-morgan/jobs/extracted/) against Alex's criteria and application log, checking the outcomes listed in [`examples/alex-morgan/eml/README.md`](../../examples/alex-morgan/eml/README.md), and cover each rule, yearly conversion, regions, invalid values, `duplicate` vs `repost`, the second pass, `--explain` after the mail is gone, the report, permanent numbers and your decisions (`same_as`, `to_apply`, `--release-later`), retention as time goes by (`--prune`) and `--calibration`. They run in CI.
