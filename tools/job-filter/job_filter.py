# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Stage 1 filter for the job-inbox skill: deduplicate job postings and apply the rules in criteria.md.

Usage:
    uv run job_filter.py <extracted.json>...                 filter postings (oldest mail first), print JSON
    uv run job_filter.py <extracted.json>... --update-seen   ...and record them in jobs/seen.json
    uv run job_filter.py <posting.json> --recheck --update-seen
                                                             second pass with the full posting (stage 2)
    uv run job_filter.py --explain <key>                     show how each rule judges a recorded posting
    uv run job_filter.py --report [--days 7]                 open postings and recent rejections, for the inbox
    uv run job_filter.py --set <key|#n> field=value...       record stage 2 results or the user's decision
    uv run job_filter.py --release-later                     'later' decisions back to undecided (start of a run)
    (all of them take --workspace DIR, --criteria, --seen, --applications and --date YYYY-MM-DD)

The model extracts and normalizes the postings of each job alert into
workspace/jobs/extracted/<mail-id>.json (a JSON list); this script decides. For every posting it:

1. validates the fields: a value outside its enum or of the wrong type becomes null and is
   reported in "missing" and "invalid";
2. deduplicates it against jobs/seen.json, applications.md and the postings before it in the
   same run: "duplicate" (same posting, skipped) or "repost" (same company, another posting:
   it goes on, flagged);
3. applies the rules in the front matter of jobs/criteria.md, in this order: role_family,
   title_exclude, seniority, location, salary_floor, company_blocklist.

Decisions: pass, maybe (a rule lacked its data: it goes on), reject (cites rule_id), duplicate,
repost. A null field never rejects a posting. Same postings + same criteria = same output.
Never calls the model or the network.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2] / "workspace"

RULES = ["role_family", "title_exclude", "seniority", "location", "salary_floor", "company_blocklist"]

SENIORITY = ["intern", "junior", "mid", "senior", "lead", "director", "vp"]
MODALITY = ["remote", "hybrid", "onsite"]
CONTRACT = ["employee", "contractor", "freelance"]
SALARY_PERIOD = ["year", "month", "day", "hour"]
REGIONS = ["EU", "EMEA", "EUROPE", "WORLD"]
DEFAULT_ANNUALIZE = {"month": 14, "day": 220, "hour": 1760}
# Below these, a salary is not plausible for its period (e.g. "30 €-45 € / year", an hourly rate
# with the wrong label): the amounts are treated as invalid instead of failing the salary floor.
MIN_PLAUSIBLE = {"year": 1000, "month": 100, "day": 10, "hour": 1}

AS_IS_TEXT = ["source", "url", "title", "company", "location", "salary_text", "posted"]
NORMALIZED = ["title_en", "role_family", "seniority", "modality", "country", "city", "contract",
              "salary_min", "salary_max", "salary_currency", "salary_period"]
FIELDS = AS_IS_TEXT[:1] + ["job_id"] + AS_IS_TEXT[1:] + ["applicants", "easy_apply"] + NORMALIZED

# Job IDs found in posting links, per portal: (source, pattern). The first group is the ID.
PORTAL_IDS = [
    ("linkedin", r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*?-)?(\d{6,})"),
    ("linkedin", r"linkedin\.com/jobs/.*[?&]currentJobId=(\d{6,})"),
    ("indeed", r"indeed\.[a-z.]+/.*[?&]jk=([0-9a-f]{8,})"),
    ("infojobs", r"infojobs\.net/.*/of-i([0-9a-f]{8,})"),
    ("tecnoempleo", r"tecnoempleo\.com/.*/rf-([0-9a-f]{8,})"),
    ("glassdoor", r"glassdoor\.[a-z.]+/.*[?&]jobListingId=(\d+)"),
    ("greenhouse", r"greenhouse\.io/(?:[^/?#]+/)?jobs/(\d+)"),
    ("greenhouse", r"greenhouse\.io/.*[?&]gh_jid=(\d+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/[^/?#]+/([0-9a-f-]{36})"),
    ("ashby", r"jobs\.ashbyhq\.com/[^/?#]+/([0-9a-f-]{36})"),
    ("smartrecruiters", r"jobs\.smartrecruiters\.com/[^/?#]+/(\d{6,})"),
    ("workable", r"apply\.workable\.com/[^/?#]+/j/([0-9A-Fa-f]{6,})"),
    ("wellfound", r"wellfound\.com/jobs/(\d+)"),
    ("welcometothejungle", r"welcometothejungle\.com/[^?#]*/jobs/([^/?#]+)"),
]
PORTAL_IDS = [(source, re.compile(pattern, re.I)) for source, pattern in PORTAL_IDS]

COMPANY_SUFFIXES = {
    "sl", "slu", "sll", "sa", "sau", "sas", "sarl", "srl", "spa", "gmbh", "ag", "kg", "ug", "ltd", "limited",
    "inc", "incorporated", "llc", "llp", "lp", "plc", "corp", "corporation", "co", "bv", "nv", "lda", "oy",
    "ab", "as", "aps", "sp", "zoo", "pty", "pte", "kk",
}
COMPANY_COUNTRIES = {
    "espana", "spain", "iberia", "portugal", "france", "deutschland", "germany", "italia", "italy", "uk",
    "usa", "us", "europe", "emea", "latam", "mexico", "ireland", "netherlands", "nederland", "belgium",
    "switzerland", "schweiz", "suisse", "austria", "osterreich", "poland", "polska", "nordics", "international",
    "global",
}


class ConfigError(Exception):
    pass


# ---------------------------------------------------------------- normalization

def fold(text):
    """Lowercase, no accents, punctuation as spaces, spaces collapsed."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^\w\s]|_", " ", text)
    return " ".join(text.split())


def normalize_title(title):
    return fold(title) if title else ""


def normalize_company(company):
    """fold() without legal suffixes (S.L., GmbH, Inc…) or a country at the end."""
    if not company:
        return ""
    text = re.sub(r"(?<=\b\w)\.", "", str(company))  # S.L.U. -> SLU
    words = fold(text).split()
    while len(words) > 1 and (words[-1] in COMPANY_SUFFIXES or words[-1] in COMPANY_COUNTRIES):
        words.pop()
    return " ".join(words)


def slug(text):
    return fold(text).replace(" ", "-")


def contains_word(text, phrase):
    """True if the folded phrase appears in the folded text as whole words."""
    phrase = fold(phrase)
    return bool(phrase) and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", fold(text)) is not None


def id_from_url(url):
    """(source, job_id) from a posting link, or (None, None)."""
    for source, pattern in PORTAL_IDS:
        match = pattern.search(url or "")
        if match:
            return source, match.group(1)
    return None, None


# ---------------------------------------------------------------- criteria

def read_front_matter(path):
    import yaml

    text = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    match = re.match(r"---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not match:
        raise ConfigError(f"{path}: no front matter (a YAML block between --- lines at the top)")
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: the front matter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the front matter must be a mapping")
    return data


def _strings(value, where):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, (str, int, float)) and not isinstance(v, bool)
                                               for v in value):
        raise ConfigError(f"{where} must be a list of words")
    return [str(v).strip() for v in value if str(v).strip()]


def _mapping(value, where):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping")
    return value


def _amounts(value, where):
    out = {}
    for currency, amount in _mapping(value, where).items():
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            raise ConfigError(f"{where}.{currency} must be a positive number")
        out[str(currency).strip().upper()] = amount
    return out


def load_criteria(path):
    data = read_front_matter(path)
    if "filter" not in data:
        raise ConfigError(f"{path}: the front matter has no 'filter' block")
    f = _mapping(data["filter"], "filter")
    families = _mapping(f.get("role_families"), "filter.role_families")
    definitions = _mapping(families.get("definitions"), "filter.role_families.definitions")
    seniority = _strings(_mapping(f.get("seniority"), "filter.seniority").get("exclude"), "filter.seniority.exclude")
    seniority = [s.lower() for s in seniority]
    unknown = [s for s in seniority if s not in SENIORITY]
    if unknown:
        raise ConfigError(f"filter.seniority.exclude: unknown level(s) {unknown}; use {SENIORITY}")
    floors = _mapping(f.get("salary_floor"), "filter.salary_floor")
    annualize = dict(DEFAULT_ANNUALIZE)
    for period, factor in _mapping(floors.get("annualize"), "filter.salary_floor.annualize").items():
        if period not in annualize:
            raise ConfigError(f"filter.salary_floor.annualize: unknown period '{period}'; use month, day, hour")
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or factor <= 0:
            raise ConfigError(f"filter.salary_floor.annualize.{period} must be a positive number")
        annualize[period] = factor
    criteria = {
        "include": [s.lower() for s in _strings(families.get("include"), "filter.role_families.include")],
        "exclude": [s.lower() for s in _strings(families.get("exclude"), "filter.role_families.exclude")],
        "definitions": [str(k).lower() for k in definitions],
        "title_exclude": _strings(f.get("title_exclude"), "filter.title_exclude"),
        "seniority_exclude": seniority,
        "remote_countries": [s.upper() for s in _strings(_mapping(f.get("remote"), "filter.remote").get("countries"),
                                                         "filter.remote.countries")],
        "onsite_cities": _strings(_mapping(f.get("onsite"), "filter.onsite").get("cities"), "filter.onsite.cities"),
        "annualize": annualize,
        "floors": {m: _amounts(floors.get(m), f"filter.salary_floor.{m}") for m in MODALITY},
        "company_blocklist": _strings(f.get("company_blocklist"), "filter.company_blocklist"),
    }
    criteria["families"] = set(criteria["include"]) | set(criteria["exclude"]) | set(criteria["definitions"])
    return criteria


# ---------------------------------------------------------------- postings

def _text(value):
    if isinstance(value, str):
        return value.strip() or None
    return value  # anything else is invalid; None stays None


def validate(raw, criteria):
    """Return (posting, invalid): every field of FIELDS, with bad values set to None.

    invalid maps each rejected field to the value it had.
    """
    if not isinstance(raw, dict):
        raise ValueError("each posting must be a JSON object")
    p, invalid = {}, {}

    def bad(field, value):
        invalid[field] = value
        p[field] = None

    for field in AS_IS_TEXT + ["title_en", "city"]:
        value = _text(raw.get(field))
        if value is None or isinstance(value, str):
            p[field] = value
        else:
            bad(field, value)
    if p["source"] is not None:
        p["source"] = re.sub(r"[^a-z0-9]", "", p["source"].lower()) or None

    job_id = raw.get("job_id")
    if isinstance(job_id, int) and not isinstance(job_id, bool):
        job_id = str(job_id)
    job_id = _text(job_id)
    if job_id is None or (isinstance(job_id, str) and re.fullmatch(r"[\w.-]+", job_id)):
        p["job_id"] = job_id
    else:
        bad("job_id", job_id)
    url_source, url_id = id_from_url(p["url"])
    if p["job_id"] is None and url_id:
        p["job_id"] = url_id
        p["source"] = p["source"] or url_source
    elif p["source"] is None and url_source:
        p["source"] = url_source

    applicants = raw.get("applicants")
    if applicants is None or (isinstance(applicants, int) and not isinstance(applicants, bool)) \
            or isinstance(applicants, str):
        p["applicants"] = applicants
    else:
        bad("applicants", applicants)
    easy_apply = raw.get("easy_apply")
    if easy_apply is None or isinstance(easy_apply, bool):
        p["easy_apply"] = easy_apply
    else:
        bad("easy_apply", easy_apply)

    def enum(field, allowed, transform=str.lower):
        value = raw.get(field)
        if value is None:
            p[field] = None
        elif isinstance(value, str) and transform(value.strip()) in allowed:
            p[field] = transform(value.strip())
        else:
            bad(field, value)

    enum("role_family", criteria["families"] | {"other"})
    enum("seniority", SENIORITY)
    enum("modality", MODALITY)
    enum("contract", CONTRACT)
    enum("salary_period", SALARY_PERIOD)

    country = raw.get("country")
    if country is None:
        p["country"] = None
    elif isinstance(country, str) and (re.fullmatch(r"[A-Za-z]{2}", country.strip())
                                       or country.strip().upper() in REGIONS):
        p["country"] = country.strip().upper()
    else:
        bad("country", country)

    currency = raw.get("salary_currency")
    if currency is None:
        p["salary_currency"] = None
    elif isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
        p["salary_currency"] = currency.strip().upper()
    else:
        bad("salary_currency", currency)

    for field in ("salary_min", "salary_max"):
        value = raw.get(field)
        if value is None:
            p[field] = None
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            p[field] = int(value) if float(value).is_integer() else value
        else:
            bad(field, value)
    if p["salary_min"] and p["salary_max"] and p["salary_min"] > p["salary_max"]:
        bad("salary_min", p["salary_min"])
        bad("salary_max", raw.get("salary_max"))
    if p["salary_period"]:
        for field in ("salary_min", "salary_max"):
            if p[field] is not None and p[field] < MIN_PLAUSIBLE[p["salary_period"]]:
                bad(field, p[field])
    return p, invalid


def posting_key(p):
    """<source>-<job_id>, or a name key when there is no ID."""
    if p.get("job_id"):
        return f"{p.get('source') or 'unknown'}-{p['job_id']}"
    parts = [p.get("source") or "unknown", slug(p.get("company") or "") or None, slug(p.get("title") or "") or None]
    if not p.get("company"):
        parts.append(slug(p.get("city") or p.get("location") or "") or None)
    return "-".join(x for x in parts if x)


def same_posting(a, b):
    """IDs decide when both postings have one; otherwise company + title (or source + title + place)."""
    if a.get("job_id") and b.get("job_id"):
        return (a.get("source"), str(a["job_id"])) == (b.get("source"), str(b["job_id"]))
    title_a, title_b = normalize_title(a.get("title")), normalize_title(b.get("title"))
    if not title_a or title_a != title_b:
        return False
    company_a, company_b = normalize_company(a.get("company")), normalize_company(b.get("company"))
    if company_a or company_b:
        return company_a == company_b
    place = lambda x: fold(x.get("city") or x.get("location") or "")  # noqa: E731
    return a.get("source") == b.get("source") and place(a) == place(b)


# ---------------------------------------------------------------- applications.md

def read_applications(path):
    """Rows of the application log, read by column position (headers can be in any language):
    date, company, role, folder, posting link, status, notes."""
    path = Path(path)
    if not path.exists():
        return []
    rows, lines = [], path.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("|") or re.fullmatch(r"\|[\s:|-]*", line):
            continue
        is_header = i + 1 < len(lines) and re.fullmatch(r"\|[\s:|-]*-[\s:|-]*", lines[i + 1].strip())
        if is_header:
            continue
        cells = [c.strip().strip("`").strip() for c in line.strip("|").split("|")]
        cells += [""] * (7 - len(cells))
        link = re.search(r"https?://[^\s)>\]]+", cells[4])
        url = link.group(0) if link else None
        source, job_id = id_from_url(url)
        rows.append({
            "date": cells[0], "company": cells[1] or None, "title": cells[2] or None, "folder": cells[3] or None,
            "url": url, "source": source, "job_id": job_id, "status": cells[5] or None, "notes": cells[6] or None,
        })
    return rows


# ---------------------------------------------------------------- seen.json

def load_seen(path):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "postings": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("postings"), dict):
        raise ConfigError(f"{path}: expected an object with a 'postings' object")
    return data


def save_seen(path, seen):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen["postings"] = dict(sorted(seen["postings"].items()))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(seen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def assign_numbers(seen):
    """Give every posting without one its permanent number `n` (highest + 1), by first_seen and then
    in the order the postings were added (key order for the ones read from disk). The user refers to
    postings by these numbers ("apply 23"), so a number never changes or gets reused.
    Returns how many were assigned."""
    postings = seen["postings"]
    used = [e["n"] for e in postings.values() if isinstance(e.get("n"), int)]
    next_n = max(used, default=0) + 1
    order = {k: i for i, k in enumerate(postings)}
    todo = sorted((k for k, e in postings.items() if not isinstance(e.get("n"), int)),
                  key=lambda k: (postings[k].get("first_seen") or "", order[k]))
    for k in todo:
        postings[k]["n"] = next_n
        next_n += 1
    return len(todo)


def find_key(ref, postings):
    """A posting's key from its key (any case) or its number (`#23`). None if there is no such posting."""
    ref = ref.strip()
    if re.fullmatch(r"#\d+", ref):
        n = int(ref[1:])
        return next((k for k, e in postings.items() if e.get("n") == n), None)
    return next((k for k in postings if k.lower() == ref.lower()), None)


def _add_unique(entry, field, value):
    if value and value not in entry.setdefault(field, []):
        entry[field].append(value)


# ---------------------------------------------------------------- rules

def num(n):
    return f"{n:.0f}" if float(n).is_integer() else f"{n:.2f}"


def evaluate(p, c):
    """Judge one posting with every rule. Returns a list of
    {rule_id, result: pass|reject|maybe|skip, reason, missing}."""
    out = []

    def add(rule, result, reason, missing=()):
        out.append({"rule_id": rule, "result": result, "reason": reason, "missing": list(missing)})

    # role_family
    family = p["role_family"]
    if not c["include"] and not c["exclude"]:
        add("role_family", "skip", "no role families configured")
    elif family in (None, "other"):
        add("role_family", "maybe", f"role family is {family or 'unknown'}", ["role_family"])
    elif family in c["exclude"]:
        add("role_family", "reject", f"role family '{family}' is excluded")
    elif c["include"] and family not in c["include"]:
        add("role_family", "reject", f"role family '{family}' is not among the wanted ones ({', '.join(c['include'])})")
    else:
        add("role_family", "pass", f"role family '{family}' is wanted")

    # title_exclude
    titles = [t for t in (p["title"], p["title_en"]) if t]
    if not c["title_exclude"]:
        add("title_exclude", "skip", "no excluded title words configured")
    elif not titles:
        add("title_exclude", "maybe", "no title", ["title"])
    else:
        hit = next(((w, t) for w in c["title_exclude"] for t in titles if contains_word(t, w)), None)
        if hit:
            add("title_exclude", "reject", f"title '{hit[1]}' contains the excluded word '{hit[0]}'")
        else:
            add("title_exclude", "pass", "no excluded word in the title")

    # seniority
    level = p["seniority"]
    if not c["seniority_exclude"]:
        add("seniority", "skip", "no excluded seniority levels configured")
    elif level is None:
        add("seniority", "maybe", "seniority unknown", ["seniority"])
    elif level in c["seniority_exclude"]:
        add("seniority", "reject", f"seniority '{level}' is excluded")
    else:
        add("seniority", "pass", f"seniority '{level}' is accepted")

    # location
    modality = p["modality"]
    if modality is None:
        if c["remote_countries"] or c["onsite_cities"]:
            add("location", "maybe", "work mode unknown", ["modality"])
        else:
            add("location", "skip", "no countries or cities configured")
    elif modality == "remote":
        country = p["country"]
        if not c["remote_countries"]:
            add("location", "skip", "no countries configured for remote roles")
        elif country is None:
            add("location", "maybe", "remote, country or region unknown", ["country"])
        elif country in c["remote_countries"]:
            add("location", "pass", f"remote from {country}, which is accepted")
        else:
            add("location", "reject",
                f"remote from {country}, not in the accepted countries ({', '.join(c['remote_countries'])})")
    else:
        city = p["city"]
        cities = {fold(x): x for x in c["onsite_cities"]}
        if not cities:
            add("location", "skip", f"no cities configured for {modality} roles")
        elif city is None:
            add("location", "maybe", f"{modality}, city unknown", ["city"])
        elif fold(city) in cities:
            add("location", "pass", f"{modality} in {city}, which is accepted")
        else:
            add("location", "reject",
                f"{modality} in {city}, not in the accepted cities ({', '.join(c['onsite_cities'])})")

    # salary_floor
    amount = p["salary_max"] or p["salary_min"]
    currency, period = p["salary_currency"], p["salary_period"]
    configured = any(c["floors"][m] for m in MODALITY)
    if not configured:
        add("salary_floor", "skip", "no salary floors configured")
    elif p["contract"] in ("contractor", "freelance"):
        add("salary_floor", "skip", f"{p['contract']} rate: compared in stage 2, not with a yearly salary")
    elif amount is None:
        add("salary_floor", "skip", "no published salary")
    elif currency is None or period is None:
        add("salary_floor", "skip", "salary without currency or period",
            [f for f, v in (("salary_currency", currency), ("salary_period", period)) if v is None])
    else:
        yearly = amount * (1 if period == "year" else c["annualize"][period])
        if modality:
            floor, label = c["floors"][modality].get(currency), f"the {modality} floor"
        else:
            candidates = [c["floors"][m][currency] for m in MODALITY if currency in c["floors"][m]]
            floor, label = (min(candidates) if candidates else None), "the lowest floor (work mode unknown)"
        shown = f"{num(amount)} {currency}/{period}" + ("" if period == "year" else f" = {num(yearly)} {currency}/year")
        if floor is None:
            add("salary_floor", "skip", f"no floor for {currency}" + (f" on {modality} roles" if modality else ""))
        elif yearly < floor:
            add("salary_floor", "reject", f"{shown} is below {label} of {num(floor)} {currency}")
        else:
            add("salary_floor", "pass", f"{shown} meets {label} of {num(floor)} {currency}")

    # company_blocklist
    company = normalize_company(p["company"])
    blocked = {normalize_company(x) for x in c["company_blocklist"]}
    if not blocked:
        add("company_blocklist", "skip", "no companies blocked")
    elif not company:
        add("company_blocklist", "skip", "no company name")
    elif company in blocked:
        add("company_blocklist", "reject", f"company '{p['company']}' is blocked")
    else:
        add("company_blocklist", "pass", "company not blocked")
    return out


def decide(evaluations):
    """(decision, rule_id, reason, missing) from the rule results: the first reject wins."""
    missing = [f for e in evaluations for f in e["missing"]]
    for e in evaluations:
        if e["result"] == "reject":
            return "reject", e["rule_id"], e["reason"], missing
    maybes = [e for e in evaluations if e["result"] == "maybe"]
    if maybes:
        return "maybe", None, "; ".join(e["reason"] for e in maybes), missing
    return "pass", None, "every configured rule is met", missing


# ---------------------------------------------------------------- filtering

def _application_ref(row):
    return {"date": row["date"], "company": row["company"], "role": row["title"], "folder": row["folder"],
            "status": row["status"], "notes": row["notes"]}


def _seen_ref(key, entry):
    return {"key": key, "title": entry.get("title"), "company": entry.get("company"),
            "filter": (entry.get("filter") or {}).get("decision"), "recommendation": entry.get("recommendation"),
            "user_decision": entry.get("user_decision"), "user_reason": entry.get("user_reason")}


def filter_postings(batches, criteria, seen, applications, today, recheck=False):
    """Filter every posting of every batch, in order. batches: [(mail_id, [raw posting, ...])].

    seen is updated in place, so postings earlier in the run count as seen; the caller decides
    whether to save it. Returns the list of results.
    """
    results = []
    postings = seen["postings"]
    for mail_id, raws in batches:
        for raw in raws:
            p, invalid = validate(raw, criteria)
            key = posting_key(p)
            stored = postings.get(key) if recheck else None
            if stored:  # second pass: the stored fields, completed or corrected by the new ones
                merged = {f: stored.get(f) for f in FIELDS}
                merged.update({f: v for f, v in p.items() if v is not None})
                p, _ = validate(merged, criteria)
                invalid = {f: v for f, v in invalid.items() if p[f] is None}
            others = {k: e for k, e in postings.items() if not (recheck and k == key)}
            result = {"key": key, "mail_id": mail_id, "title": p["title"], "company": p["company"]}

            dup_key = next((k for k, e in others.items() if same_posting(p, e)), None)
            dup_row = next((r for r in applications if same_posting(p, r)), None)
            if dup_key or dup_row:
                if dup_row:
                    of = f"applications.md: {dup_row['date']} {dup_row['company']} — {dup_row['title']}"
                    reason = f"already applied on {dup_row['date']} ({dup_row['status'] or 'no status'})"
                else:
                    of = dup_key
                    reason = f"already seen as {dup_key} on {postings[dup_key].get('first_seen')}"
                result.update(decision="duplicate", rule_id=None, reason=reason, missing=[],
                              invalid=invalid, duplicate_of=of, repost_of=[])
                results.append(result)
                entry = postings.get(dup_key or key)
                if entry is None:  # first seen, and already applied: recorded so --explain finds it
                    entry = postings[key] = _new_entry(p, today)
                    entry["filter"] = {"decision": "duplicate", "rule_id": None, "reason": reason,
                                       "missing": [], "date": today, "pass": 1}
                    entry["application"] = _application_ref(dup_row)
                _add_unique(entry, "seen", today)
                _add_unique(entry, "mail_ids", mail_id)
                continue

            company = normalize_company(p["company"])
            repost_of = []
            if company:
                repost_of += [{"seen": _seen_ref(k, e)} for k, e in others.items()
                              if normalize_company(e.get("company")) == company
                              and p["role_family"] and e.get("role_family") == p["role_family"]]
                repost_of += [{"application": _application_ref(r)} for r in applications
                              if normalize_company(r["company"]) == company]

            evaluations = evaluate(p, criteria)
            decision, rule_id, reason, missing = decide(evaluations)
            missing = list(dict.fromkeys(missing + list(invalid)))
            if repost_of and decision != "reject":
                decision = "repost"
                reason = "possible repost: same company as an earlier posting or application; " + reason
            result.update(decision=decision, rule_id=rule_id, reason=reason, missing=missing,
                          invalid=invalid, duplicate_of=None, repost_of=repost_of)
            results.append(result)

            entry = stored or postings.setdefault(key, _new_entry(p, today))
            entry.update({f: p[f] for f in FIELDS})
            entry["filter"] = {"decision": decision, "rule_id": rule_id, "reason": reason, "missing": missing,
                               "date": today, "pass": 2 if stored else 1}
            if repost_of:  # kept for the stage 2 signals, which may come after the mail is gone
                entry["filter"]["repost_of"] = repost_of
            if not stored:  # a second pass reads the full posting, not a mail
                _add_unique(entry, "seen", today)
                _add_unique(entry, "mail_ids", mail_id)
    assign_numbers(seen)
    for r in results:
        entry = postings.get(r["key"]) or postings.get(r.get("duplicate_of") or "")
        r["n"] = entry.get("n") if entry else None
    return results


def _new_entry(p, today):
    entry = {"first_seen": today, "seen": [], "mail_ids": []}
    entry.update({f: p[f] for f in FIELDS})
    entry.update({"stage": "filtered", "filter": None, "recommendation": None, "user_decision": None,
                  "user_reason": None, "posting_path": None})
    return entry


# ---------------------------------------------------------------- explain

def explain(key, criteria, seen):
    """Human-readable account of how each rule judges a recorded posting, with the current criteria."""
    postings = seen["postings"]
    match = find_key(key, postings)
    if match is None:
        close = [k for k in postings if key.lower() in k.lower()]
        hint = f" Did you mean: {', '.join(close[:5])}?" if close else ""
        raise ConfigError(f"'{key}' is not in seen.json.{hint}")
    entry = postings[match]
    p, invalid = validate({f: entry.get(f) for f in FIELDS}, criteria)
    number = f"#{entry['n']} " if isinstance(entry.get("n"), int) else ""
    lines = [f"{number}{match} · {p['title'] or '?'} · {p['company'] or '?'}"]
    seen_on = ", ".join(entry.get("seen") or []) or "?"
    lines.append(f"Seen: {seen_on} (mails: {', '.join(entry.get('mail_ids') or []) or '?'})")
    f = entry.get("filter") or {}
    if f:
        stored = f.get("decision", "?") + (f" ({f['rule_id']})" if f.get("rule_id") else "")
        lines.append(f"Recorded decision: {stored} on {f.get('date', '?')}, pass {f.get('pass', 1)}: {f.get('reason', '')}")
    if entry.get("stage") and entry["stage"] != "filtered":
        lines.append(f"Stage: {entry['stage']}" + (f" on {entry['stage_date']}" if entry.get("stage_date") else "")
                     + (f" · posting: {entry['posting_path']}" if entry.get("posting_path") else ""))
    for label, field in (("Recommendation", "recommendation"), ("Your decision", "user_decision")):
        if entry.get(field):
            lines.append(f"{label}: {entry[field]}" + (f" ({entry['user_reason']})"
                                                      if field == "user_decision" and entry.get("user_reason") else ""))
    if f.get("decision") == "duplicate":
        lines.append("Duplicates skip the rules; below is how the rules would judge it now.")
    evaluations = evaluate(p, criteria)
    decision, rule_id, _, _ = decide(evaluations)
    lines.append(f"With the current criteria: {decision}" + (f" ({rule_id})" if rule_id else ""))
    lines.append("")
    values = {
        "role_family": p["role_family"], "title_exclude": " / ".join(t for t in (p["title"], p["title_en"]) if t),
        "seniority": p["seniority"],
        "location": " · ".join(str(v) for v in (p["modality"], p["country"], p["city"]) if v),
        "salary_floor": " ".join(str(v) for v in (p["salary_min"], p["salary_max"], p["salary_currency"],
                                                   p["salary_period"], p["contract"]) if v),
        "company_blocklist": p["company"],
    }
    width = max(len(r) for r in RULES)
    for e in evaluations:
        value = values[e["rule_id"]] or "null"
        lines.append(f"  {e['rule_id']:<{width}}  {e['result']:<6}  {e['reason']}  [{value}]")
    if invalid:
        lines.append("")
        lines.append("Invalid values, treated as null: " + ", ".join(f"{k}={v!r}" for k, v in invalid.items()))
    return "\n".join(lines)


# ---------------------------------------------------------------- stage 2 results (--set)

STAGES = ["filtered", "pending_text", "analysed", "expired"]
RECOMMENDATIONS = ["apply", "apply_with_reservations", "discard"]
USER_DECISIONS = ["apply", "discard", "later"]
FITS = ["high", "medium", "low"]
SETTABLE = ["stage", "recommendation", "knockouts", "must_covered", "fit", "posting_path", "same_as",
            "user_decision", "user_reason"]
NULLS = {"", "null", "none"}
# Shared by the postings of one job published twice (same_as): set on one, copied to the others.
SHARED = ["user_decision", "user_reason", "user_decision_date", "posting_path"]


def same_job(key, postings):
    """The keys of the postings that are the same job as `key`: the one the same_as links point to,
    and every posting whose same_as points to it. Just [key] when there are no links."""
    root = postings[key].get("same_as") or key
    if root not in postings:
        root = key
    return [root] + sorted(k for k, e in postings.items() if k != root and e.get("same_as") == root)


def set_fields(key, assignments, seen, workspace, today):
    """Record stage 2 results (or the user's decision) for a posting: `field=value` strings, validated.
    The key may also be the posting's number (`#23`). The fields in SHARED are copied to the other
    postings of the same job (same_as).

    Returns (key, updated entry, keys of the other postings it was copied to).
    Raises ConfigError on an unknown posting, field or value.
    """
    postings = seen["postings"]
    match = find_key(key, postings)
    if match is None:
        raise ConfigError(f"'{key}' is not in seen.json")
    entry = postings[match]
    changes = {}
    for assignment in assignments:
        field, sep, value = assignment.partition("=")
        field, value = field.strip(), value.strip()
        if not sep or field not in SETTABLE:
            raise ConfigError(f"'{assignment}': expected field=value with a field among {SETTABLE}")
        if value.lower() in NULLS and field != "stage":
            changes[field] = None
            continue

        def one_of(allowed):
            if value.lower() not in allowed:
                raise ConfigError(f"{field}: '{value}' is not one of {allowed}")
            return value.lower()

        if field == "stage":
            changes[field] = one_of(STAGES)
        elif field == "recommendation":
            changes[field] = one_of(RECOMMENDATIONS)
        elif field == "user_decision":
            changes[field] = one_of(USER_DECISIONS)
        elif field == "fit":
            changes[field] = one_of(FITS)
        elif field == "knockouts":
            if not re.fullmatch(r"\d+", value):
                raise ConfigError(f"knockouts: '{value}' is not a whole number")
            changes[field] = int(value)
        elif field == "must_covered":
            try:
                share = float(value)
            except ValueError:
                share = -1
            if not 0 <= share <= 1:
                raise ConfigError(f"must_covered: '{value}' is not a share between 0 and 1")
            changes[field] = round(share, 3)
        elif field == "posting_path":
            path = Path(value)
            if not (path if path.is_absolute() else Path(workspace) / path).is_file():
                raise ConfigError(f"posting_path: {value} does not exist (paths are relative to the workspace)")
            changes[field] = path.as_posix()
        elif field == "same_as":
            other = next((k for k in postings if k.lower() == value.lower()), None)
            if other is None or other == match:
                raise ConfigError(f"same_as: '{value}' is not another posting in seen.json")
            changes[field] = other
        else:  # user_reason: free text
            changes[field] = value
    if "stage" in changes and changes["stage"] != entry.get("stage"):
        changes["stage_date"] = today
    if "user_decision" in changes:
        changes["user_decision_date"] = today if changes["user_decision"] else None
        changes.setdefault("user_reason", None)  # a new decision does not keep the old one's reason
    entry.update(changes)
    shared = {f: v for f, v in changes.items() if f in SHARED}
    others = [k for k in same_job(match, postings) if k != match] if shared else []
    for k in others:
        postings[k].update(shared)
    return match, entry, others


def release_later(seen):
    """Clear every `later` decision, so those postings come back to be decided (start of a full run).
    Returns the keys released."""
    released = [k for k, e in seen["postings"].items() if e.get("user_decision") == "later"]
    for k in released:
        seen["postings"][k].update(user_decision=None, user_decision_date=None, user_reason=None)
    return released


# ---------------------------------------------------------------- report

OPEN_DECISIONS = ["pass", "repost", "maybe"]  # also the queue order of stage 2
CLOSED_STAGES = {"expired"}
QUEUE_STAGES = {None, "filtered"}
REPORT_FIELDS = ["source", "job_id", "url", "title", "company", "location", "salary_text", "posted", "applicants",
                 "easy_apply", "title_en", "role_family", "seniority", "modality", "country", "city", "contract"]


def _ordinal(day):
    try:
        return date.fromisoformat(day).toordinal()
    except (TypeError, ValueError):
        return 0


def _applicant_count(entry):
    a = entry.get("applicants")
    return a if isinstance(a, int) and not isinstance(a, bool) else float("inf")


def _decide_order(e):
    """Order of the analysed postings (spec §6.4): recommendation, knock-outs (fewest first),
    share of must-haves covered (highest first), role fit; unknowns last."""
    rec = e.get("recommendation")
    knockouts = e.get("knockouts")
    covered = e.get("must_covered")
    fit = e.get("fit")
    return (RECOMMENDATIONS.index(rec) if rec in RECOMMENDATIONS else len(RECOMMENDATIONS),
            knockouts if isinstance(knockouts, int) else float("inf"),
            -covered if isinstance(covered, (int, float)) else 1,
            FITS.index(fit) if fit in FITS else len(FITS),
            -_ordinal(e["first_seen"]), e["key"])


def report(seen, today, days=7):
    """What the job-inbox tray shows, from seen.json alone (so it works after the mails are gone).

    Every item carries the posting's permanent number `n`.
    to_apply: the user decided to apply and cv-tailor has not moved the posting into an application
    folder yet (posting_path not under output/); oldest decision first. Postings with same_as are
    left out (their decision is the one of the posting they point to).
    The rest, only postings without a decision from the user and not expired:
    to_decide: analysed in stage 2, in the order of _decide_order (also those a second pass rejected:
    they show as "discard", citing the rule).
    open: the stage 2 queue, postings that got through stage 1 (pass, repost, maybe) and are not analysed
    yet: pass, then repost, then maybe; newest first; then fewest applicants; then fewest missing fields.
    pending_text: stage 2 could not get the posting's text; the user has to paste it.
    filtered: postings rejected by stage 1 in the last `days` days, newest first.
    """
    since = date.fromordinal(_ordinal(today) - days).isoformat()
    to_apply, to_decide, open_, pending, filtered = [], [], [], [], []
    for key, entry in seen["postings"].items():
        f = entry.get("filter") or {}
        stage = entry.get("stage")
        item = {"n": entry.get("n"), "key": key, **{field: entry.get(field) for field in REPORT_FIELDS},
                "first_seen": entry.get("first_seen"), "seen": entry.get("seen") or [],
                "mail_ids": entry.get("mail_ids") or [], "stage": stage,
                "decision": f.get("decision"), "rule_id": f.get("rule_id"), "reason": f.get("reason"),
                "missing": f.get("missing") or [], "filter_date": f.get("date"), "filter_pass": f.get("pass", 1)}
        undecided = not entry.get("user_decision") and stage not in CLOSED_STAGES
        stage2 = {"repost_of": f.get("repost_of") or [], "recommendation": entry.get("recommendation"),
                  "knockouts": entry.get("knockouts"), "must_covered": entry.get("must_covered"),
                  "fit": entry.get("fit"), "posting_path": entry.get("posting_path"),
                  "same_as": entry.get("same_as"), "stage_date": entry.get("stage_date")}
        if entry.get("user_decision") == "apply":
            if not entry.get("same_as") and not (entry.get("posting_path") or "").startswith("output/"):
                to_apply.append({**item, **stage2, "user_reason": entry.get("user_reason"),
                                 "user_decision_date": entry.get("user_decision_date")})
        elif undecided and stage == "analysed" and f.get("decision") != "duplicate":
            to_decide.append({**item, **stage2})
        elif undecided and f.get("decision") in OPEN_DECISIONS and stage == "pending_text":
            pending.append({**item, **stage2})
        elif undecided and f.get("decision") in OPEN_DECISIONS and stage in QUEUE_STAGES:
            open_.append({**item, **stage2})
        elif f.get("decision") == "reject" and stage not in ("analysed", "pending_text") \
                and (f.get("date") or "") >= since:
            item["user_decision"] = entry.get("user_decision")
            filtered.append(item)
    to_apply.sort(key=lambda e: (e["user_decision_date"] or "", e["n"] or 0, e["key"]))
    to_decide.sort(key=_decide_order)
    queue_order = lambda e: (OPEN_DECISIONS.index(e["decision"]), -_ordinal(e["first_seen"]),  # noqa: E731
                             _applicant_count(seen["postings"][e["key"]]), len(e["missing"]), e["key"])
    open_.sort(key=queue_order)
    pending.sort(key=queue_order)
    filtered.sort(key=lambda e: (-_ordinal(e["filter_date"]), e["key"]))
    counts = {d: sum(e["decision"] == d for e in open_) for d in OPEN_DECISIONS}
    counts["reject"] = len(filtered)
    counts["to_apply"] = len(to_apply)
    counts["to_decide"] = len(to_decide)
    counts["pending_text"] = len(pending)
    return {"date": today, "days": days, "to_apply": to_apply, "to_decide": to_decide, "open": open_,
            "pending_text": pending, "filtered": filtered, "counts": counts}


# ---------------------------------------------------------------- CLI

def read_batches(paths):
    batches = []
    for path in paths:
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as e:
            raise ConfigError(f"{path}: {e}") from e
        if isinstance(data, dict) and isinstance(data.get("postings"), list):
            data = data["postings"]
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise ConfigError(f"{path}: expected a JSON list of postings")
        batches.append((path.stem, data))
    return batches


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage 1 filter for job postings (job-inbox).")
    parser.add_argument("extracted", nargs="*", help="jobs/extracted/<mail-id>.json files, oldest mail first")
    parser.add_argument("--explain", metavar="KEY", help="show how each rule judges a posting recorded in seen.json")
    parser.add_argument("--report", action="store_true",
                        help="print what the inbox shows: open postings and recent rejections, from seen.json")
    parser.add_argument("--set", nargs="+", metavar=("KEY", "FIELD=VALUE"), dest="set_fields",
                        help="record stage 2 results or the user's decision for a posting in seen.json: "
                             + ", ".join(SETTABLE) + " (value null clears a field); KEY may be the number, #23")
    parser.add_argument("--release-later", action="store_true",
                        help="clear every 'later' decision, so those postings are to decide again (start of a run)")
    parser.add_argument("--days", type=int, default=7, help="--report: rejections of the last N days (default 7)")
    parser.add_argument("--update-seen", action="store_true", help="record the results in seen.json")
    parser.add_argument("--recheck", action="store_true",
                        help="second pass (stage 2): judge postings already in seen.json again, merged with the new fields")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--criteria", type=Path, help="default: <workspace>/jobs/criteria.md")
    parser.add_argument("--seen", type=Path, help="default: <workspace>/jobs/seen.json")
    parser.add_argument("--applications", type=Path, help="default: <workspace>/applications.md")
    parser.add_argument("--date", default=date.today().isoformat(), help="date recorded in seen.json (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # names with accents on a Windows console
        sys.stdout.reconfigure(encoding="utf-8")

    criteria_path = args.criteria or args.workspace / "jobs" / "criteria.md"
    seen_path = args.seen or args.workspace / "jobs" / "seen.json"
    applications_path = args.applications or args.workspace / "applications.md"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date) or not _ordinal(args.date):
        parser.error("--date must be YYYY-MM-DD")
    if sum((bool(args.explain), bool(args.report), bool(args.extracted), bool(args.set_fields),
            args.release_later)) != 1:
        parser.error("give extracted .json files, --explain KEY, --report, --set KEY FIELD=VALUE... "
                     "or --release-later")
    if args.set_fields and len(args.set_fields) < 2:
        parser.error("--set needs a posting key and at least one FIELD=VALUE")
    if args.days < 0:
        parser.error("--days must be 0 or more")
    try:
        if not Path(criteria_path).exists():
            raise ConfigError(f"{criteria_path} not found; the job-inbox skill creates it on the first run")
        criteria = load_criteria(criteria_path)
        seen = load_seen(seen_path)
        if assign_numbers(seen):  # seen.json files from before the numbers, once
            save_seen(seen_path, seen)
        if args.explain:
            print(explain(args.explain, criteria, seen))
            return 0
        if args.report:
            print(json.dumps(report(seen, args.date, args.days), ensure_ascii=False, indent=2))
            return 0
        if args.release_later:
            released = release_later(seen)
            save_seen(seen_path, seen)
            print(json.dumps({"released": released}, ensure_ascii=False, indent=2))
            return 0
        if args.set_fields:
            key, entry, others = set_fields(args.set_fields[0], args.set_fields[1:], seen, args.workspace,
                                            args.date)
            save_seen(seen_path, seen)
            shown = ["stage", "stage_date"] + SETTABLE[1:] + ["user_decision_date"]
            print(json.dumps({"n": entry.get("n"), "key": key, **{f: entry.get(f) for f in shown},
                              "also_set": others}, ensure_ascii=False, indent=2))
            return 0
        batches = read_batches(args.extracted)
        results = filter_postings(batches, criteria, seen, read_applications(applications_path), args.date,
                                  recheck=args.recheck)
    except ConfigError as e:
        print(f"job-filter: {e}", file=sys.stderr)
        return 2
    if args.update_seen:
        save_seen(seen_path, seen)
    counts = {d: sum(r["decision"] == d for r in results) for d in ("pass", "maybe", "repost", "reject", "duplicate")}
    out = {"results": results, "counts": counts}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
