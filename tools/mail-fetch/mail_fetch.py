# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Turn job-search mail into normalized markdown files for the job-inbox skill.

Usage:
    uv run mail_fetch.py                      download new mail over IMAP (settings in workspace/.env)
    uv run mail_fetch.py --since 2026-11-01   first load: every mail since that date
    uv run mail_fetch.py --test               check the connection and list the folders
    uv run mail_fetch.py --import <folder-or-.eml>...
    (all of them take --workspace DIR)

IMAP is read-only: the folder is opened with EXAMINE and mail is read with BODY.PEEK[], so
nothing is marked as read, moved or deleted. workspace/mail/state.json keeps UIDVALIDITY and
the last UID, so each run only downloads what is new.

Each mail becomes workspace/mail/inbox/<date>-<id>.md: front matter (sender, subject, date,
forward data, status: new), the body as text taken from the HTML (links kept as
[text](url)), hidden HTML text and calendar invites in their own sections, and the list
of links. Links are made canonical: tracking redirects whose target is in the URL are
resolved, tracking and session parameters are removed (some of them log you in without a
password), LinkedIn job links are rebuilt from the job ID, and unsubscribe, account and
login links are dropped.

Read-only and idempotent: workspace/mail/state.json remembers every mail ID ever
imported, so a mail is never created twice, even after its .md was deleted.
Standard library only; the model is never called.
"""
import argparse
import base64
import binascii
import email
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2] / "workspace"

# ---------------------------------------------------------------- text helpers

INVISIBLE = dict.fromkeys(map(ord, "͏​‌‍⁠﻿­"), None)


def clean_text(text):
    """Drop invisible characters, normalize spaces and keep at most one blank line in a row."""
    text = text.translate(INVISIBLE).replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


# ---------------------------------------------------------------- links

# Query parameters that carry a destination URL in tracking redirects.
REDIRECT_KEYS = ("url", "u", "q", "dest", "destination", "redirect", "redirect_url", "redirect_uri", "target", "link", "goto", "to")
# Keys inside a JWT payload that carry the destination.
JWT_DEST_KEYS = ("dest", "url", "destination", "target", "redirect", "link")
# Tracking, session and login parameters, matched on the lowercased name.
SENSITIVE_PARAM = re.compile(
    r"^(utm_.*|trk.*|tracking.*|refid|ref|lipi|midtoken|midsig|otptoken|eid|ek|e|m|ts|t|li|loid|"
    r".*token.*|.*sig|.*signature|.*session.*|sid|auth.*|.*hash|.*_esuh|ems_.*|mc_.*|_hs.*|"
    r"fbclid|gclid|msclkid|referrer|cid|uid|user.*|email|mail|ml|tk|cs|ida|key|apikey|code|ticket|otp)$"
)
# On LinkedIn every other parameter is tracking: keep only these.
LINKEDIN_KEEP = {"keywords", "geoid", "location", "f_tpr", "currentjobid"}
LINKEDIN_JOB = re.compile(r"/(?:comm/)?jobs/view/(?:[^/]*-)?(\d{6,})")
# Unsubscribe, preferences, account and login pages: never kept.
DROP_PATH = re.compile(
    r"unsub|opt-?out|desactiva|cancelar|darse-de-baja|mypreferences|/preferences|/settings|"
    r"login|log-in|signin|sign-in|signup|logout|password|forgot|/account",
    re.I,
)
# Redirectors whose destination is not in the URL: they cannot be resolved without a request.
OPAQUE_HOST = re.compile(r"^(link|links|click|clicks|track|tracking|t|e|em|email|go|r|url\d*)\.", re.I)
OPAQUE_PATH = re.compile(r"(nrd\.php|/click|/track|tracking\.php|/redirect|/r/|/ls/click|/wf/click)", re.I)
TOKEN_VALUE = re.compile(r"^[A-Za-z0-9_\-+/=.%~]{24,}$")


def _jwt_payload(value):
    parts = value.split(".")
    if len(parts) != 3:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        data = json.loads(raw)
    except (binascii.Error, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _embedded_destination(query):
    """A destination URL carried by a redirect: plain, URL-encoded, or inside a JWT."""
    for key, value in parse_qsl(query, keep_blank_values=True):
        value = unquote(value) if "%3a" in value.lower() else value
        if key.lower() in REDIRECT_KEYS and re.match(r"https?://", value, re.I):
            return value
        payload = _jwt_payload(value)
        if payload:
            for k in JWT_DEST_KEYS:
                dest = payload.get(k)
                if isinstance(dest, str) and re.match(r"https?://", dest, re.I):
                    return dest
    return None


def canonical_url(url):
    """The URL to keep, without tracking or tokens, or None if the link must not be kept."""
    url = html.unescape(url or "").strip()
    for _ in range(5):  # redirects can be nested (e.g. Safe Links around a tracker)
        if not re.match(r"https?://", url, re.I):
            return None
        parts = urlsplit(url)
        dest = _embedded_destination(parts.query)
        if not dest or dest == url:
            break
        url = dest
    parts = urlsplit(url)
    host = parts.hostname or ""
    path = parts.path or "/"

    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        job = LINKEDIN_JOB.search(path)
        if job:
            return f"https://www.linkedin.com/jobs/view/{job.group(1)}/"
        path = re.sub(r"^/comm/", "/", path)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() in LINKEDIN_KEEP]
        host = "www.linkedin.com"
    else:
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not SENSITIVE_PARAM.match(k.lower()) and "@" not in v and not TOKEN_VALUE.match(v)
        ]
        if OPAQUE_HOST.match(host) or OPAQUE_PATH.search(path):
            return None

    if DROP_PATH.search(path) or any(v.lower() == "unsubscribe" for _, v in parse_qsl(parts.query)):
        return None
    return urlunsplit(("https" if parts.scheme.lower() == "https" else "http", host, path, urlencode(query, quote_via=quote), ""))


# ---------------------------------------------------------------- HTML to text

BLOCK = {"p", "div", "tr", "table", "tbody", "thead", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
         "blockquote", "section", "article", "header", "footer", "pre", "hr", "center", "dl", "dt", "dd"}
CELL = {"td", "th"}
SKIP = {"style", "script", "head", "title", "noscript", "template"}
VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr", "source"}
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])|max-height\s*:\s*0(?![.\d])", re.I)


class HtmlToText(HTMLParser):
    """Visible text with links as [text](url), plus the hidden text and the kept links apart."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buffers = [[]]       # one buffer per open <a>, the base buffer first
        self.anchors = []         # (canonical url or None, buffer had a nested link)
        self.hidden = []          # hidden text fragments
        self.hide = None          # [tag, depth] of the element that started hiding
        self.skip = 0
        self.links = []

    # The element that started hiding text ends when its own tag closes.
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in SKIP:
            self.skip += 1
            return
        if self.hide:
            if tag == self.hide[0] and tag not in VOID:
                self.hide[1] += 1
            if tag in BLOCK or tag == "br":
                self.hidden.append("\n")
            return
        if tag not in VOID and HIDDEN_STYLE.search(attrs.get("style") or ""):
            self.hide = [tag, 1]
            self.hidden.append("\n")
            return
        out = self.buffers[-1]
        if tag == "br":
            out.append("\n")
        elif tag in BLOCK:
            out.append("\n")
        elif tag in CELL:
            out.append(" ")
        elif tag == "a":  # image-only links (logos, icons) leave no text, only their URL in the list
            self.buffers.append([])
            self.anchors.append(canonical_url(attrs.get("href") or ""))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.hide:
            if tag == self.hide[0]:
                self.hide[1] -= 1
                if self.hide[1] == 0:
                    self.hide = None
            return
        if tag == "a" and self.anchors:
            url = self.anchors.pop()
            inner = "".join(self.buffers.pop())
            text = re.sub(r"\s+", " ", inner).strip()
            nested = "](" in inner
            block = "\n" in inner.strip()
            out = self.buffers[-1]
            if nested or (block and not url):
                out.append(inner)
            elif block:  # a link around a whole card: its first line (the job title) carries the link
                lead, first, rest = re.match(r"(\s*)([^\n]*)(.*)", inner, re.S).groups()
                first = re.sub(r"\s+", " ", first).strip()
                out.append(f"{lead}[{first}]({url}){rest}")
            elif not url or not text:
                out.append(f" {text} " if text else "")
            else:
                out.append(f"[{text}]({url})")
            if url and url not in self.links:
                self.links.append(url)
        elif tag in BLOCK:
            self.buffers[-1].append("\n")
        elif tag in CELL:
            self.buffers[-1].append(" ")

    def handle_data(self, data):
        if self.skip:
            return
        if self.hide:
            self.hidden.append(data)
        else:
            self.buffers[-1].append(data)

    def result(self):
        while len(self.buffers) > 1:  # unclosed anchors
            self.handle_endtag("a")
        return clean_text("".join(self.buffers[0])), clean_text("".join(self.hidden)), self.links


def html_to_text(markup):
    parser = HtmlToText()
    parser.feed(markup)
    parser.close()
    return parser.result()


URL_IN_TEXT = re.compile(r"https?://[^\s<>()\"']+")


def plain_to_text(text):
    """Plain-text body: entities decoded, URLs made canonical (dropped ones removed)."""
    links = []

    def repl(match):
        url = canonical_url(match.group(0).rstrip(".,;"))
        if url and url not in links:
            links.append(url)
        return url or ""

    return clean_text(URL_IN_TEXT.sub(repl, html.unescape(text))), links


# ---------------------------------------------------------------- inline forwards

FWD_MARKER = re.compile(
    r"^-{2,}\s*(forwarded message|mensaje reenviado|mensagem encaminhada|original message|mensaje original|"
    r"mensagem original|weitergeleitete nachricht|message transféré|message d'origine)\s*-{2,}\s*$"
    r"|^(begin forwarded message|inicio del mensaje reenviado|início da mensagem reencaminhada)\s*:\s*$"
    r"|^_{10,}\s*$|^-{3,}\s*original message\s*-{3,}$",
    re.I | re.M,
)
FWD_LABELS = {
    "from": "from", "de": "from", "von": "from", "da": "from",
    "date": "date", "sent": "date", "fecha": "date", "enviado": "date", "enviada": "date", "data": "date",
    "datum": "date", "gesendet": "date", "envoyé": "date",
    "subject": "subject", "asunto": "subject", "assunto": "subject", "betreff": "subject", "objet": "subject",
    "to": "to", "para": "to", "destinatario": "to", "an": "to", "à": "to", "cc": "cc",
}
FWD_SUBJECT = re.compile(r"^\s*(fwd?|rv|tr|wg|enc|i)\s*:", re.I)
LABEL_LINE = re.compile(r"^\*?([A-Za-zÀ-ÿ]+)\*?\s*:\s*(.*)$")


def split_forward(text, subject=""):
    """(user_note, original headers, forwarded body) of an inline forward, or None."""
    lines = text.split("\n")
    note_end = start = None  # note_end: first line of the forward block; start: first header line
    for i, line in enumerate(lines):
        if FWD_MARKER.match(line.strip()):
            note_end, start = i, i + 1
            break
    if start is None:
        if not FWD_SUBJECT.match(subject):
            return None
        # Outlook without a marker line: a block of "From:" … "Subject:" headers.
        for i, line in enumerate(lines):
            m = LABEL_LINE.match(line.strip())
            if m and FWD_LABELS.get(m.group(1).lower()) == "from":
                note_end = start = i
                break
        if start is None:
            return None
    headers, i, last = {}, start, None
    while i < len(lines) and i < start + 20:
        line = lines[i].strip()
        m = LABEL_LINE.match(line)
        key = FWD_LABELS.get(m.group(1).lower()) if m else None
        if key:
            value = m.group(2).strip()
            if not value and i + 1 < len(lines):  # Roundcube's plain part puts the value on the next line
                i += 1
                value = lines[i].strip()
            headers.setdefault(key, value)
            last = i
        elif line:
            break
        i += 1
    if "from" not in headers:
        return None
    return strip_signature("\n".join(lines[:note_end])), headers, clean_text("\n".join(lines[last + 1:]))


def strip_signature(text):
    """The text before a "-- " signature line."""
    return clean_text(re.split(r"\n-- ?\n", "\n" + text + "\n", maxsplit=1)[0])


DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%a, %b %d, %Y at %I:%M %p", "%A, %B %d, %Y %I:%M %p",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%d %b %Y %H:%M")


def parse_date(value):
    """ISO 8601 if the date can be parsed, else the original text."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.replace(" ", " "), fmt).isoformat()
        except ValueError:
            continue
    return value


# ---------------------------------------------------------------- one mail

def mail_id(msg, raw):
    message_id = (msg.get("Message-ID") or "").strip()
    return hashlib.sha1((message_id.encode() if message_id else raw)).hexdigest()[:12]


def _addr(value):
    pairs = getaddresses([str(value)]) if value else []
    out = [f"{n} <{a}>" if n else a for n, a in pairs if a or n]
    return ", ".join(out) if out else None


def _text_of(part):
    try:
        return part.get_content()
    except (LookupError, UnicodeError, KeyError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def _parts(msg):
    """Body parts of a message, without descending into attached messages."""
    if msg.get_content_type() == "message/rfc822":
        return []
    if not msg.is_multipart():
        return [msg]
    out = []
    for part in msg.iter_parts():
        out += [] if part.get_content_type() == "message/rfc822" else _parts(part)
    return out


def _attached_message(msg):
    attached = [p for p in msg.walk() if p.get_content_type() == "message/rfc822"]
    if len(attached) != 1:
        return None
    inner = attached[0].get_payload()
    inner = inner[0] if isinstance(inner, list) else inner
    return inner if isinstance(inner, email.message.Message) else None


def _calendar(part):
    text = re.sub(r"\r?\n[ \t]", "", _text_of(part))  # unfold
    fields = {}
    for line in text.splitlines():
        m = re.match(r"^(SUMMARY|DTSTART|DTEND|LOCATION)(;[^:]*)?:(.*)$", line)
        if m and m.group(1) not in fields:
            tz = re.search(r"TZID=([^;:]+)", m.group(2) or "")
            fields[m.group(1)] = m.group(3).strip() + (f" ({tz.group(1)})" if tz else "")
    return fields


def body_of(msg):
    """(text, hidden text, links, calendar fields, attachment names) of a message."""
    parts = _parts(msg)
    htmls = [p for p in parts if p.get_content_type() == "text/html" and not p.is_attachment()]
    plains = [p for p in parts if p.get_content_type() == "text/plain" and not p.is_attachment()]
    text, hidden, links = "", "", []
    if htmls:
        text, hidden, links = html_to_text("\n".join(_text_of(p) for p in htmls))
    if not text and plains:
        text, links = plain_to_text("\n".join(_text_of(p) for p in plains))
    calendar = {}
    for p in parts:
        if p.get_content_type() == "text/calendar":
            calendar = calendar or _calendar(p)
    attachments = [p.get_filename() for p in parts if p.is_attachment() and p.get_filename()]
    return text, hidden, links, calendar, attachments


def normalize(raw):
    """(id, file date, markdown) for the raw bytes of one mail."""
    outer = email.message_from_bytes(raw, policy=policy.default)
    meta = {
        "message_id": (outer.get("Message-ID") or "").strip() or None,
        "from": _addr(outer.get("From")),
        "to": _addr(outer.get("To")),
        "subject": str(outer.get("Subject") or "").strip() or None,
        "date": parse_date(outer.get("Date")),
        "status": "new",
    }
    the_id = mail_id(outer, raw)
    inner = _attached_message(outer)
    if inner is not None:  # forwarded as an attachment: the inner message is the mail
        note = strip_signature(body_of(outer)[0])
        text, hidden, links, calendar, attachments = body_of(inner)
        the_id = mail_id(inner, inner.as_bytes(policy=policy.SMTP))
        meta.update({
            "message_id": (inner.get("Message-ID") or "").strip() or meta["message_id"],
            "forwarded": True,
            "original_from": _addr(inner.get("From")),
            "original_date": parse_date(inner.get("Date")),
            "original_subject": str(inner.get("Subject") or "").strip() or None,
        })
        if note:
            meta["user_note"] = note
    else:
        text, hidden, links, calendar, attachments = body_of(outer)
        fwd = split_forward(text, meta["subject"] or "")
        if fwd:
            note, headers, text = fwd
            meta.update({
                "forwarded": True,
                "original_from": _addr(headers.get("from")),
                "original_date": parse_date(headers.get("date")),
                "original_subject": headers.get("subject"),
            })
            if note:
                meta["user_note"] = note
        elif FWD_SUBJECT.match(meta["subject"] or ""):
            meta["forwarded"] = True  # the model finds the original sender during triage
    if attachments:
        meta["attachments"] = attachments
    meta = {"id": the_id, **meta}

    front = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items() if v is not None)
    out = [f"---\n{front}\n---", text or "(no text)"]
    if calendar:
        out.append("## Calendar invite\n\n" + "\n".join(f"- {k}: {v}" for k, v in calendar.items()))
    if hidden:
        out.append("## Hidden text\n\nText the HTML hides from the reader (preview lines, or possibly instructions meant for software):\n\n" + hidden)
    if links:
        out.append("## Links\n\n" + "\n".join(f"- {u}" for u in links))
    day = (meta.get("date") or "")[:10]
    day = day if re.match(r"\d{4}-\d{2}-\d{2}$", day) else "0000-00-00"
    return the_id, day, "\n\n".join(out) + "\n"


# ---------------------------------------------------------------- state and import

def load_state(path):
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("uidvalidity", None)
    state.setdefault("last_uid", None)
    state["ids"] = set(state.get("ids", []))
    return state


def save_state(path, state):
    data = {**state, "ids": sorted(state["ids"])}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def store(raw, inbox, state):
    """Write one mail unless its ID was seen before. Returns the new path or None."""
    the_id, day, markdown = normalize(raw)
    if the_id in state["ids"]:
        return None
    path = inbox / f"{day}-{the_id}.md"
    path.write_text(markdown, encoding="utf-8", newline="\n")
    state["ids"].add(the_id)
    return path


def eml_files(sources):
    for src in sources:
        p = Path(src)
        if p.is_dir():
            yield from sorted(p.glob("*.eml"))
        elif p.suffix.lower() == ".eml" and p.is_file():
            yield p
        else:
            print(f"skipped (not a folder or .eml): {p}", file=sys.stderr)


def import_eml(sources, workspace):
    mail_dir = Path(workspace) / "mail"
    inbox = mail_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    state_path = mail_dir / "state.json"
    state = load_state(state_path)
    new, seen, failed = [], 0, 0
    for f in eml_files(sources):
        try:
            path = store(f.read_bytes(), inbox, state)
        except Exception as exc:  # one broken mail must not stop the rest
            failed += 1
            print(f"error: {f.name}: {exc}", file=sys.stderr)
            continue
        if path:
            new.append(path)
        else:
            seen += 1
    save_state(state_path, state)
    return new, seen, failed


# ---------------------------------------------------------------- IMAP (read-only)

ENV_KEYS = ("IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASSWORD", "IMAP_FOLDER")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
BATCH = 25


class ConfigError(Exception):
    pass


def load_config(workspace, environ=None):
    """IMAP settings from workspace/.env, overridden by environment variables."""
    environ = os.environ if environ is None else environ
    config = {}
    env_file = Path(workspace) / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip().removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            config[key] = value
    for key in ENV_KEYS:
        if environ.get(key):
            config[key] = environ[key]
    missing = [k for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD") if not config.get(k)]
    if missing:
        where = env_file if env_file.exists() else f"{env_file} (not found)"
        raise ConfigError(f"missing {', '.join(missing)} in {where} or the environment; see workspace.example/.env.example")
    try:
        port = int(config.get("IMAP_PORT") or 993)
    except ValueError:
        raise ConfigError(f"IMAP_PORT is not a number: {config['IMAP_PORT']!r}") from None
    return {
        "host": config["IMAP_HOST"],
        "port": port,
        "user": config["IMAP_USER"],
        "password": config["IMAP_PASSWORD"],
        "folder": config.get("IMAP_FOLDER") or "INBOX",
    }


def connect(config):
    """A logged-in connection: TLS on port 993, STARTTLS on any other port (plain text is refused)."""
    import imaplib
    import ssl

    context = ssl.create_default_context()
    if config["port"] == 993:
        conn = imaplib.IMAP4_SSL(config["host"], config["port"], ssl_context=context, timeout=30)
    else:
        conn = imaplib.IMAP4(config["host"], config["port"], timeout=30)
        conn.starttls(ssl_context=context)
    conn.login(config["user"], config["password"])
    return conn


def _quote_mailbox(name):
    return name if re.fullmatch(r"[A-Za-z0-9_./\-]+", name) else '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _check(typ, data, what):
    if typ != "OK":
        detail = b" ".join(d for d in data if isinstance(d, bytes)).decode(errors="replace") if data else ""
        raise RuntimeError(f"{what} failed: {detail}".strip())
    return data


def examine(conn, folder):
    """Open the folder read-only (EXAMINE). Returns (UIDVALIDITY, message count)."""
    data = _check(*conn.select(_quote_mailbox(folder), readonly=True), f"EXAMINE {folder}")
    count = int(data[0]) if data and data[0] else 0
    _, values = conn.response("UIDVALIDITY")
    if not values or values[0] is None:
        status = _check(*conn.status(_quote_mailbox(folder), "(UIDVALIDITY)"), "STATUS")
        values = re.findall(rb"UIDVALIDITY (\d+)", status[0] or b"")
    return int(values[0]), count


def imap_date(day):
    """2026-11-01 → 01-Nov-2026 (IMAP dates use English month names, whatever the locale)."""
    d = datetime.strptime(day, "%Y-%m-%d")
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def search_uids(conn, criteria):
    data = _check(*conn.uid("SEARCH", *criteria), "SEARCH")
    return sorted({int(u) for u in b" ".join(d for d in data if d).split()})


def fetch_raw(conn, uids):
    """{uid: raw bytes} with BODY.PEEK[], which never sets the \\Seen flag."""
    data = _check(*conn.uid("FETCH", ",".join(map(str, uids)), "(UID BODY.PEEK[])"), "FETCH")
    out = {}
    for i, item in enumerate(data):
        if not isinstance(item, tuple):
            continue
        header, raw = item
        uid = re.search(rb"UID (\d+)", header)
        if not uid and i + 1 < len(data) and isinstance(data[i + 1], bytes):  # some servers send UID after the body
            uid = re.search(rb"UID (\d+)", data[i + 1])
        if uid:
            out[int(uid.group(1))] = raw
    return out


def fetch_imap(config, workspace, since=None, connect_fn=connect, log=print):
    """Download new mail. Returns (new paths, already known, failed)."""
    mail_dir = Path(workspace) / "mail"
    inbox = mail_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    state_path = mail_dir / "state.json"
    state = load_state(state_path)
    conn = connect_fn(config)
    try:
        uidvalidity, _ = examine(conn, config["folder"])
        same = state["uidvalidity"] == uidvalidity and state.get("folder", config["folder"]) == config["folder"]
        if not same and state["uidvalidity"] is not None:
            log("UIDVALIDITY or folder changed: checking every mail again (known mails are skipped by ID)")
        last = state["last_uid"] if same and state["last_uid"] else 0
        if since:
            uids = search_uids(conn, ["SINCE", imap_date(since)])
        elif last:
            uids = [u for u in search_uids(conn, ["UID", f"{last + 1}:*"]) if u > last]  # n:* always matches the last mail
        else:
            uids = search_uids(conn, ["ALL"])
        new, seen, failed = [], 0, 0
        top = last
        for start in range(0, len(uids), BATCH):
            batch = uids[start:start + BATCH]
            raws = fetch_raw(conn, batch)
            for uid in batch:
                raw = raws.get(uid)
                try:
                    if raw is None:
                        raise RuntimeError("the server returned no body")
                    path = store(raw, inbox, state)
                except Exception as exc:  # one broken mail must not stop the rest
                    failed += 1
                    log(f"error: UID {uid}: {exc}")
                    continue
                if path:
                    new.append(path)
                else:
                    seen += 1
            top = max([top, *batch])
            state.update(uidvalidity=uidvalidity, last_uid=top, folder=config["folder"])
            save_state(state_path, state)  # after every batch, so an interrupted run resumes
        state.update(uidvalidity=uidvalidity, last_uid=top or None, folder=config["folder"])
        save_state(state_path, state)
        return new, seen, failed
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def test_connection(config, workspace, connect_fn=connect, log=print):
    """Log in, list the folders and check the configured one, read-only."""
    conn = connect_fn(config)
    try:
        log(f"connected to {config['host']}:{config['port']} as {config['user']}")
        folders = _check(*conn.list(), "LIST")
        log("folders:")
        for line in folders:
            if isinstance(line, bytes):
                m = re.match(rb'\((.*?)\) (?:"[^"]*"|NIL) (.*)$', line)
                log(f"  {(m.group(2) if m else line).decode(errors='replace').strip(chr(34))}")
        uidvalidity, count = examine(conn, config["folder"])
        state = load_state(Path(workspace) / "mail" / "state.json")
        if state["uidvalidity"] == uidvalidity and state["last_uid"]:
            pending = len([u for u in search_uids(conn, ["UID", f"{state['last_uid'] + 1}:*"]) if u > state["last_uid"]])
            log(f"{config['folder']}: {count} mails, {pending} not downloaded yet")
        else:
            log(f"{config['folder']}: {count} mails, none downloaded yet")
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ---------------------------------------------------------------- command line

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="Without --import or --test, downloads new mail over IMAP (settings in workspace/.env).",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--import", dest="sources", nargs="+", metavar="PATH",
                      help="import .eml files or folders of them instead of reading IMAP")
    mode.add_argument("--test", action="store_true", help="check the IMAP connection and list the folders")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="IMAP: also look at every mail since this date (first load)")
    ap.add_argument("--workspace", default=os.environ.get("TAILORED_CV_WORKSPACE", DEFAULT_WORKSPACE),
                    help="workspace folder (default: the repo's workspace/)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.since:
        try:
            imap_date(args.since)
        except ValueError:
            ap.error(f"--since must be YYYY-MM-DD, got {args.since!r}")
        if args.sources or args.test:
            ap.error("--since only applies to downloading over IMAP")

    if args.sources:
        new, seen, failed = import_eml(args.sources, args.workspace)
        known = "already imported"
    else:
        import imaplib
        import socket
        import ssl

        try:
            config = load_config(args.workspace)
            if args.test:
                test_connection(config, args.workspace)
                return 0
            new, seen, failed = fetch_imap(config, args.workspace, since=args.since,
                                           log=lambda m: print(m, file=sys.stderr))
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except imaplib.IMAP4.error as exc:
            msg = exc.args[0].decode(errors="replace") if exc.args and isinstance(exc.args[0], bytes) else str(exc)
            print(f"error: IMAP: {msg}. Check IMAP_USER and IMAP_PASSWORD (an app password for Gmail).", file=sys.stderr)
            return 2
        except (OSError, ssl.SSLError, socket.timeout, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        known = "already downloaded"
    for p in new:
        print(f"new: {p.name}")
    print(f"{len(new)} new, {seen} {known}, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
