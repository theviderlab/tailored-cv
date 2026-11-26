# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Download the full text of job postings for stage 2 of the job-inbox skill (and for cv-tailor).

Usage:
    uv run posting_fetch.py <key>...          postings recorded in workspace/jobs/seen.json
    uv run posting_fetch.py --url <url>       a posting link the user gave in the chat
    (both take --workspace DIR and --force to download again a posting already saved)

For a key in seen.json the URL is never taken as is from a mail: it is built from the portal and the
job ID (LinkedIn: the public jobs-guest endpoint, which needs no login), or it is the clean link the
mail gave, and only on a known job portal or ATS. Any other posting is "unsupported" and the caller
falls back to other means (web fetch, browser, or asking the user to paste the text).

Each posting is saved verbatim as workspace/jobs/postings/<key>.md: front matter (key, url, fetched,
text_source: script, what the page says about title, company, location...) and a "## Posting"
section with the text; hidden text, if any, goes to its own section (it is where injected
instructions hide). The analysis is added later by the skill, above "## Posting".

Prints JSON: one result per posting with status saved, exists, failed or unsupported.
Standard library only; the model is never called.
"""
import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mail-fetch"))
sys.path.insert(0, str(HERE.parent / "job-filter"))
import job_filter  # noqa: E402  (id_from_url, posting_key; PyYAML is only needed to read criteria)
import mail_fetch  # noqa: E402  (canonical_url, HtmlToText, clean_text)

DEFAULT_WORKSPACE = HERE.parents[1] / "workspace"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
TIMEOUT = 20
DELAY = 1.5  # seconds between two requests to the same portal
RETRY_WAITS = [5, 15]  # seconds to wait after "429 Too Many Requests" before trying again
MIN_TEXT = 300  # less than this is a login wall, a closed posting or a page built by JavaScript

# Job portals and ATS whose clean posting links may be fetched (the host or a parent domain).
KNOWN_HOSTS = [
    "linkedin.com", "tecnoempleo.com", "infojobs.net", "indeed.com", "indeed.es", "glassdoor.com", "glassdoor.es",
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "workable.com", "wellfound.com",
    "welcometothejungle.com", "teamtailor.com", "personio.de", "personio.com", "jobs.personio.de", "recruitee.com",
    "myworkdayjobs.com", "bamboohr.com", "jobvite.com", "icims.com", "successfactors.com", "successfactors.eu",
    "join.com", "factorialhr.com", "breezy.hr", "pinpointhq.com", "homerun.co", "remoteok.com", "himalayas.app",
    "weworkremotely.com", "remotive.com",
]


class ConfigError(Exception):
    pass


def known_host(url):
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in KNOWN_HOSTS)


# ---------------------------------------------------------------- HTML helpers

class PostingText(mail_fetch.HtmlToText):
    """mail-fetch's HTML to text, with list items as markdown bullets."""

    def handle_starttag(self, tag, attrs):
        if tag == "li" and not self.skip and not self.hide:
            self.buffers[-1].append("\n- ")
            return
        super().handle_starttag(tag, attrs)


def to_text(markup):
    parser = PostingText()
    parser.feed(markup or "")
    parser.close()
    text, hidden, _ = parser.result()
    text = re.sub(r"^- *\n+(?=\S)", "- ", text, flags=re.M)  # a bullet whose text starts after a <p>
    text = re.sub(r"^- *$\n?", "", text, flags=re.M)
    text = mail_fetch.clean_text(text)
    text = re.sub(r"^(- .*)\n\n(?=- )", r"\1\n", text, flags=re.M)  # no blank lines inside a list
    text = re.sub(r"^(- .*)\n\n(?=- )", r"\1\n", text, flags=re.M)  # (overlapping matches need a second pass)
    return text, hidden


def element(markup, cls):
    """Inner HTML of the first element whose class list contains `cls`, or None."""
    start = re.search(r'<([a-zA-Z0-9]+)\b[^>]*\bclass="[^"]*(?<![\w-])' + re.escape(cls) + r'(?![\w-])[^"]*"[^>]*>',
                      markup)
    if not start:
        return None
    tag, depth, pos = start.group(1).lower(), 1, start.end()
    for m in re.finditer(r"<(/?)" + tag + r"\b[^>]*?(/?)>", markup[pos:], re.I):
        if m.group(1):
            depth -= 1
        elif not m.group(2):
            depth += 1
        if depth == 0:
            return markup[pos:pos + m.start()]
    return markup[pos:]


def element_text(markup, cls):
    inner = element(markup, cls)
    if inner is None:
        return None
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
    return text or None


# ---------------------------------------------------------------- parsers

def parse_linkedin(markup):
    """The jobs-guest page: top card, salary, LinkedIn's criteria box and the description."""
    meta = {
        "title": element_text(markup, "top-card-layout__title"),
        "company": element_text(markup, "topcard__org-name-link") or element_text(markup, "topcard__flavor"),
        "location": element_text(markup, "topcard__flavor--bullet"),
        "posted": element_text(markup, "posted-time-ago__text"),
        "applicants": element_text(markup, "num-applicants__caption")
                      or element_text(markup, "num-applicants__figure"),
        "salary_text": element_text(markup, "compensation__salary") or element_text(markup, "salary"),
    }
    closed = re.search(r"No longer accepting applications|Ya no se aceptan solicitudes", markup, re.I)
    meta["closed"] = True if closed else None
    criteria = re.findall(r'class="description__job-criteria-subheader"[^>]*>(.*?)</h3>\s*'
                          r'<span[^>]*class="description__job-criteria-text[^"]*"[^>]*>(.*?)</span>', markup, re.S)
    lines = [f"- {_clean(k)}: {_clean(v)}" for k, v in criteria]
    body, hidden = to_text(element(markup, "show-more-less-html__markup")
                           or element(markup, "description__text") or "")
    return meta, body, hidden, lines


def _clean(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _job_postings(markup):
    """schema.org JobPosting objects in the page's JSON-LD blocks (most ATS and portals publish them)."""
    found = []
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', markup, re.S | re.I):
        try:
            data = json.loads(html.unescape(block.strip()))
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                kind = item.get("@type")
                if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                    found.append(item)
                stack.extend(v for k, v in item.items() if k == "@graph")
    return found


def _name(value):
    if isinstance(value, dict):
        return value.get("name")
    return value if isinstance(value, str) else None


def _place(value):
    places = value if isinstance(value, list) else [value]
    out = []
    for p in places:
        if isinstance(p, dict):
            a = p.get("address") or {}
            if isinstance(a, dict):
                parts = [a.get("addressLocality"), a.get("addressRegion"), _name(a.get("addressCountry"))]
                out.append(", ".join(str(x) for x in parts if x))
            elif isinstance(a, str):
                out.append(a)
    return "; ".join(x for x in out if x) or None


def _salary(value):
    if not isinstance(value, dict):
        return None
    v = value.get("value")
    currency = value.get("currency") or ""
    if isinstance(v, dict):
        low, high, unit = v.get("minValue"), v.get("maxValue"), v.get("unitText") or ""
        amount = f"{low}–{high}" if low and high else (low or high or v.get("value"))
        return " ".join(str(x) for x in (amount, currency, f"/ {unit.lower()}" if unit else "") if x) or None
    return " ".join(str(x) for x in (v, currency) if x) or None


def parse_generic(markup):
    """JSON-LD JobPosting when the page has one, else the text of <main> or <body>."""
    postings = _job_postings(markup)
    if postings:
        jp = postings[0]
        remote = "TELECOMMUTE" in json.dumps(jp.get("jobLocationType") or "").upper()
        meta = {
            "title": jp.get("title"), "company": _name(jp.get("hiringOrganization")),
            "location": _place(jp.get("jobLocation")) or ("Remote" if remote else None),
            "posted": jp.get("datePosted"), "applicants": None, "salary_text": _salary(jp.get("baseSalary")),
            "closed": None,
        }
        lines = []
        for label, field in (("Employment type", "employmentType"), ("Valid through", "validThrough"),
                             ("Remote", "jobLocationType"), ("Applicant location", "applicantLocationRequirements"),
                             ("Experience", "experienceRequirements"), ("Education", "educationRequirements")):
            value = jp.get(field)
            if value:
                value = ", ".join(_name(v) or json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                                  for v in (value if isinstance(value, list) else [value]))
                lines.append(f"- {label}: {value}")
        body, hidden = to_text(jp.get("description") or "")
        return meta, body, hidden, lines
    main_match = re.search(r"<main\b[^>]*>(.*)</main>", markup, re.S | re.I)
    main = main_match.group(1) if main_match else None
    if not main:
        body_match = re.search(r"<body\b[^>]*>(.*)</body>", markup, re.S | re.I)
        main = body_match.group(1) if body_match else markup
    title = re.search(r"<h1\b[^>]*>(.*?)</h1>", markup, re.S | re.I) \
        or re.search(r"<title\b[^>]*>(.*?)</title>", markup, re.S | re.I)
    meta = {"title": _clean(title.group(1)) if title else None, "company": None, "location": None, "posted": None,
            "applicants": None, "salary_text": None, "closed": None}
    body, hidden = to_text(main)
    return meta, body, hidden, []


# ---------------------------------------------------------------- fetching

def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept-Language": "en,es;q=0.8"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.geturl(), response.read().decode(charset, errors="replace")


def target(entry):
    """(url to show, url to request, parser) for a seen.json entry, or (url, None, reason)."""
    source, job_id, url = entry.get("source"), entry.get("job_id"), entry.get("url")
    if source == "linkedin" and job_id:
        return (f"https://www.linkedin.com/jobs/view/{job_id}/",
                f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}", parse_linkedin)
    clean = mail_fetch.canonical_url(url) if url else None
    if not clean:
        return url, None, "no link to the posting in the mail"
    if not known_host(clean):
        return clean, None, f"{urlsplit(clean).hostname} is not a known job portal or ATS"
    return clean, clean, parse_generic


def render(key, url, meta, body, hidden, lines, today):
    fm = {"key": key, "url": url, "fetched": today, "text_source": "script"}
    fm.update({k: v for k, v in meta.items() if v is not None})
    out = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()] + ["---", ""]
    heading = " — ".join(x for x in (meta.get("title"), meta.get("company")) if x) or key
    out += [f"# {heading}", "", "## Posting", ""]
    facts = [f"- {label}: {meta[field]}" for label, field in (("Location", "location"), ("Posted", "posted"),
                                                              ("Applicants", "applicants"), ("Salary", "salary_text"))
             if meta.get(field)]
    if meta.get("closed"):
        facts.append("- Closed: the portal says it no longer accepts applications")
    if facts:
        out += facts + [""]
    if lines:
        out += ["What the portal says about it (portal metadata, often wrong):", ""] + lines + [""]
    out += [body, ""]
    if hidden:
        out += ["## Hidden text", "", hidden, ""]
    return "\n".join(out)


def fetch_one(key, url, request_url, parser, postings_dir, today, force=False, get=http_get, sleep=time.sleep):
    path = postings_dir / f"{key}.md"
    result = {"key": key, "url": url, "path": path.as_posix(), "status": None, "reason": None}
    if path.exists() and not force:
        return {**result, "status": "exists"}
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            final_url, markup = get(request_url)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < len(RETRY_WAITS):  # too many requests: wait and try again
                retry_after = e.headers.get("Retry-After") if e.headers else None
                wait = int(retry_after) if retry_after and str(retry_after).isdigit() else RETRY_WAITS[attempt]
                sleep(min(wait, 60))
                continue
            return {**result, "status": "failed", "reason": f"HTTP {e.code}", "path": None}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {**result, "status": "failed", "reason": f"network error: {getattr(e, 'reason', e)}", "path": None}
    if re.search(r"/(authwall|login|signin|uas/login)", urlsplit(final_url).path, re.I):
        return {**result, "status": "failed", "reason": "the portal asks to log in", "path": None}
    meta, body, hidden, lines = parser(markup)
    if len(body) < MIN_TEXT:
        return {**result, "status": "failed", "path": None,
                "reason": f"only {len(body)} characters of text (login wall, closed posting or JavaScript page)"}
    postings_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render(key, url, meta, body, hidden, lines, today), encoding="utf-8")
    return {**result, "status": "saved", "closed": bool(meta.get("closed")), "title": meta.get("title"),
            "company": meta.get("company")}


def key_for_url(url):
    source, job_id = job_filter.id_from_url(url)
    if job_id:
        return f"{source}-{job_id}", {"source": source, "job_id": job_id, "url": url}
    host = (urlsplit(url).hostname or "web").removeprefix("www.").split(".")[0]
    return f"{host}-{hashlib.sha1(url.encode()).hexdigest()[:10]}", {"source": host, "job_id": None, "url": url}


def run(keys, urls, workspace, today, force=False, get=http_get, delay=DELAY, sleep=time.sleep):
    postings_dir = Path(workspace) / "jobs" / "postings"
    jobs = []
    if keys:
        seen_path = Path(workspace) / "jobs" / "seen.json"
        if not seen_path.exists():
            raise ConfigError(f"{seen_path} not found")
        postings = json.loads(seen_path.read_text(encoding="utf-8")).get("postings") or {}
        for key in keys:
            match = next((k for k in postings if k.lower() == key.lower()), None)
            if match is None:
                raise ConfigError(f"'{key}' is not in seen.json")
            jobs.append((match, postings[match]))
    for url in urls:
        clean = mail_fetch.canonical_url(url)
        if not clean:
            raise ConfigError(f"{url}: not a link that can be fetched (http(s), not a login or account page)")
        key, entry = key_for_url(clean)
        if entry["source"] != "linkedin" or not entry["job_id"]:
            # a link the user gave: any host is fine, it is what cv-tailor already did with WebFetch
            jobs.append((key, {**entry, "_any_host": True}))
        else:
            jobs.append((key, entry))
    results, last = [], 0.0
    for key, entry in jobs:
        url, request_url, parser = target(entry)
        if request_url is None and entry.get("_any_host") and url:
            request_url, parser = url, parse_generic
        if request_url is None:
            results.append({"key": key, "url": url, "path": None, "status": "unsupported", "reason": parser})
            continue
        wait = last + delay - time.monotonic()
        if wait > 0 and not (postings_dir / f"{key}.md").exists():
            sleep(wait)
        result = fetch_one(key, url, request_url, parser, postings_dir, today, force=force, get=get, sleep=sleep)
        if result["status"] != "exists":
            last = time.monotonic()
        results.append(result)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download the full text of job postings (job-inbox, cv-tailor).")
    parser.add_argument("keys", nargs="*", help="posting keys recorded in jobs/seen.json (linkedin-4492981823)")
    parser.add_argument("--url", action="append", default=[], help="a posting link the user gave (repeatable)")
    parser.add_argument("--force", action="store_true", help="download again postings already saved")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--date", default=date.today().isoformat(), help="date recorded as fetched (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not args.keys and not args.url:
        parser.error("give posting keys or --url")
    try:
        results = run(args.keys, args.url, args.workspace, args.date, force=args.force)
    except (ConfigError, ValueError) as e:
        print(f"posting-fetch: {e}", file=sys.stderr)
        return 2
    counts = {s: sum(r["status"] == s for r in results) for s in ("saved", "exists", "failed", "unsupported")}
    print(json.dumps({"results": results, "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
