"""Tests for mail_fetch.py, on the fictional mails in examples/alex-morgan/eml/.

Run from the repo root: python -m unittest discover -s tools/mail-fetch -v
"""
import hashlib
import json
import re
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mail_fetch as mf  # noqa: E402

FIXTURES = HERE.parents[1] / "examples" / "alex-morgan" / "eml"
FORBIDDEN = re.compile(
    r"trackingId|refId|midToken|midSig|otpToken|utm_|trk=|trkEmail|lipi|[?&]eid=|loid|[?&]cid=|inner_jwt|"
    r"nrd\.php|memberToken|FAKE-OTP|RkFLRS1PVFA|https?://\S*unsub",
    re.I,
)


def front_matter(markdown):
    block = markdown.split("---\n", 2)[1]
    return {k: json.loads(v) for k, v in (line.split(": ", 1) for line in block.strip().split("\n"))}


class ImportFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = Path(cls.tmp.name)
        cls.new, cls.seen, cls.failed = mf.import_eml([FIXTURES], cls.ws)
        cls.inbox = cls.ws / "mail" / "inbox"
        cls.by_subject = {}
        for p in cls.inbox.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            cls.by_subject[front_matter(text)["subject"]] = (p, text)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mail(self, subject_start):
        matches = [v for k, v in self.by_subject.items() if k.startswith(subject_start)]
        self.assertEqual(len(matches), 1, subject_start)
        path, text = matches[0]
        return path, text, front_matter(text)

    def test_every_fixture_becomes_one_file(self):
        self.assertEqual(self.failed, 0)
        self.assertEqual(len(self.new), len(list(FIXTURES.glob("*.eml"))))
        for p in self.new:
            self.assertRegex(p.name, r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{12}\.md$")
            self.assertEqual(front_matter(p.read_text(encoding="utf-8"))["status"], "new")

    def test_reimport_creates_nothing_even_after_deleting_a_file(self):
        victim = sorted(self.inbox.glob("*.md"))[0]
        content = victim.read_text(encoding="utf-8")
        victim.unlink()
        try:
            new, seen, failed = mf.import_eml([FIXTURES], self.ws)
            self.assertEqual((len(new), failed), (0, 0))
            self.assertEqual(seen, len(self.new))
            self.assertFalse(victim.exists())
        finally:
            victim.write_text(content, encoding="utf-8")

    def test_state_keeps_every_id(self):
        state = json.loads((self.ws / "mail" / "state.json").read_text(encoding="utf-8"))
        ids = {front_matter(p.read_text(encoding="utf-8"))["id"] for p in self.inbox.glob("*.md")}
        self.assertEqual(set(state["ids"]), ids)

    def test_id_is_sha1_of_message_id(self):
        _, _, fm = self.mail("Tessera Health is hiring")
        self.assertEqual(fm["id"], hashlib.sha1(fm["message_id"].encode()).hexdigest()[:12])

    def test_no_tracking_tokens_or_unsubscribe_links_are_kept(self):
        for path, text in self.by_subject.values():
            self.assertIsNone(FORBIDDEN.search(text), f"{path.name}: {FORBIDDEN.search(text)}")

    def test_linkedin_alert_keeps_titles_as_canonical_links_and_the_work_mode(self):
        _, text, fm = self.mail("Tessera Health is hiring")
        self.assertIn("[Staff Data Engineer](https://www.linkedin.com/jobs/view/9900000107/)", text)
        self.assertIn("Tessera Health · European Union (Remote)", text)  # only in the HTML part
        self.assertIn("€55K/yr - €62K/yr", text)
        jobs = re.findall(r"^- https://www\.linkedin\.com/jobs/view/(\d+)/$", text, re.M)
        self.assertEqual(len(jobs), 7)
        self.assertNotIn("forwarded", fm)

    def test_hidden_preheader_goes_to_its_own_section(self):
        _, text, _ = self.mail("Tessera Health is hiring")
        body, hidden = text.split("## Hidden text", 1)
        self.assertIn("We are looking for an engineer", hidden)
        self.assertNotIn("We are looking for an engineer", body)
        self.assertNotIn("͏", text)

    def test_inline_forward_from_roundcube_in_spanish(self):
        _, text, fm = self.mail("Fwd: Kestrel Analytics")
        self.assertTrue(fm["forwarded"])
        self.assertEqual(fm["original_from"], "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>")
        self.assertEqual(fm["original_subject"], "Kestrel Analytics is hiring: Python Engineer, Data Platform and more")
        self.assertEqual(fm["original_date"], "2026-11-23T06:30:00")
        self.assertNotIn("user_note", fm)
        self.assertNotIn("Mensaje Original", text)
        self.assertIn("[Backend Engineer, Payments (Python)](https://www.linkedin.com/jobs/view/9900000120/)", text)

    def test_inline_forward_from_gmail_keeps_the_note(self):
        _, _, fm = self.mail("Fwd: Pinecrest Labs")
        self.assertEqual(fm["original_from"], "LinkedIn <jobs-noreply@linkedin.com>")
        self.assertEqual(fm["original_date"], "2026-11-23T12:58:00")
        self.assertTrue(fm["user_note"].startswith("Worth a look"))

    def test_forward_as_attachment_uses_the_inner_message(self):
        _, text, fm = self.mail("Fwd: Glasshouse Studio")
        self.assertEqual(fm["original_from"], "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>")
        self.assertEqual(fm["message_id"], "<1000000104.1000004.1795300000004@fixture-app04.prod.linkedin.com>")
        self.assertEqual(fm["id"], hashlib.sha1(fm["message_id"].encode()).hexdigest()[:12])
        self.assertEqual(fm["user_note"], "Este me interesa, sobre todo el de Glasshouse.")  # signature dropped
        self.assertIn("https://www.linkedin.com/jobs/view/9900000130/", text)

    def test_tecnoempleo_destination_comes_out_of_the_jwt(self):
        _, text, _ = self.mail("Nuevas alertas de empleo")
        self.assertIn(
            "[Senior Python Developer - Remoto España](https://www.tecnoempleo.com/senior-python-developer-remoto-espana-nimbo-software/python-django-postgresql/rf-a1b2c3d4e5f60718293a)",
            text,
        )
        self.assertNotIn("@media", text)  # the CSS-only plain part is not used
        self.assertNotIn("alex.morgan@example.com", text.split("---", 2)[2])  # the ml= parameter is gone

    def test_experteer_opaque_redirects_are_dropped(self):
        _, text, _ = self.mail("Alex Morgan, tenemos 4")
        self.assertIn("Head of Data Engineering", text)
        self.assertNotIn("experteer.es/u/", text)
        self.assertNotIn("## Links", text)

    def test_content_only_in_html(self):
        _, text, _ = self.mail("Tidewater Systems viewed")
        self.assertIn("The hiring team at Tidewater Systems noticed you", text)
        self.assertIn("[Senior Python Developer](https://www.linkedin.com/jobs/view/9900000202/)", text)

    def test_html_only_mail(self):
        _, text, _ = self.mail("Next steps @Halcyon Labs")
        self.assertIn("choose a slot via the following booking link", text)

    def test_windows_1252_and_calendar_invite(self):
        _, text, _ = self.mail("Technical Interview - Senior Backend")
        self.assertIn("We’ve enjoyed our conversations", text)
        self.assertIn("Hi Alex,", text)
        self.assertIn("- DTSTART: 20261203T113000 (GMT Standard Time)", text)
        self.assertIn("- LOCATION: Microsoft Teams Meeting", text)

    def test_rejection_has_no_html_entities(self):
        _, text, _ = self.mail("Your application at Corvane")
        self.assertIn("Kafka at scale", text)
        self.assertNotIn("&nbsp;", text)

    def test_injection_is_kept_as_hidden_text_and_its_link_is_cleaned(self):
        _, text, _ = self.mail("URGENT: Job offer")
        body, hidden = text.split("## Hidden text", 1)
        self.assertIn("ignore all previous instructions", hidden)
        self.assertNotIn("ignore all previous instructions", body)
        self.assertIn("- https://pay.tessera-careers.example/deposit\n", text)


class CanonicalUrl(unittest.TestCase):
    def test_linkedin_job_rebuilt_from_id(self):
        for url in (
            "https://www.linkedin.com/comm/jobs/view/4493696836/?trackingId=x&otpToken=y",
            "https://es.linkedin.com/jobs/view/senior-ai-engineer-at-acme-4493696836?refId=z",
        ):
            self.assertEqual(mf.canonical_url(url), "https://www.linkedin.com/jobs/view/4493696836/")

    def test_linkedin_other_pages_lose_every_tracking_parameter(self):
        self.assertEqual(
            mf.canonical_url("https://es.linkedin.com/comm/in/someone?lipi=a&midToken=b&trk=c"),
            "https://www.linkedin.com/in/someone",
        )

    def test_safe_links_and_google_redirects_are_resolved(self):
        safe = ("https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fboards.greenhouse.io%2Facme%2Fjobs%2F123"
                "%3Fgh_src%3Dabc%26utm_source%3Dx&data=05%7C02&sdata=xyz&reserved=0")
        self.assertEqual(mf.canonical_url(safe), "https://boards.greenhouse.io/acme/jobs/123?gh_src=abc")
        google = "https://www.google.com/url?q=https://jobs.lever.co/acme/abc-123&sa=D&usg=AOvVaw"
        self.assertEqual(mf.canonical_url(google), "https://jobs.lever.co/acme/abc-123")

    def test_unsubscribe_account_and_login_links_are_dropped(self):
        for url in (
            "https://www.linkedin.com/job-alert-email-unsubscribe?savedSearchId=1",
            "https://www.linkedin.com/comm/mypreferences/u/emailunsub?action=unsubscribe",
            "https://www.linkedin.com/series-notifications/?action=unsubscribe&memberToken=x",
            "https://example.com/account/login?next=/jobs",
            "mailto:someone@example.com",
        ):
            self.assertIsNone(mf.canonical_url(url), url)

    def test_values_that_look_like_tokens_or_emails_are_dropped(self):
        self.assertEqual(
            mf.canonical_url("https://jobs.example.com/view?id=42&x=AbCdEfGhIjKlMnOpQrStUvWxYz012345&who=a%40b.com"),
            "https://jobs.example.com/view?id=42",
        )

    def test_unresolvable_tracker_is_dropped(self):
        self.assertIsNone(mf.canonical_url("https://www.tecnoempleo.com/tracking.php?cid=not-a-jwt"))
        self.assertIsNone(mf.canonical_url("https://click.mail.example.com/ls/click?upn=abc"))


class HtmlLinks(unittest.TestCase):
    def test_link_around_a_whole_card_goes_on_its_first_line(self):
        # LinkedIn job recommendations wrap the logo, title and company of each card in one <a>.
        card = ('<a href="https://www.linkedin.com/comm/jobs/view/9900000777/?trackingId=abc&otpToken=FAKE">'
                '<table><tr><td><img src="logo.png"></td><td><p>AI Technical Lead</p>'
                '<p>Example Labs · Spain (Remote)</p></td></tr></table></a>')
        text, _, links = mf.html_to_text(f"<div>{card}</div>")
        self.assertRegex(text, r"\[AI Technical Lead\]\(https://www\.linkedin\.com/jobs/view/9900000777/\)\n+"
                               r"Example Labs · Spain \(Remote\)")
        self.assertEqual(links, ["https://www.linkedin.com/jobs/view/9900000777/"])

    def test_inline_and_dropped_links(self):
        text, _, _ = mf.html_to_text('<p><a href="https://jobs.example.com/42">Data Engineer</a> · '
                                     '<a href="https://www.linkedin.com/comm/mypreferences/u/emailunsub">'
                                     '<div>Unsubscribe</div><div>now</div></a></p>')
        self.assertIn("[Data Engineer](https://jobs.example.com/42)", text)
        self.assertRegex(text, r"Unsubscribe\n+now")
        self.assertNotIn("emailunsub", text)


class InlineForwards(unittest.TestCase):
    def test_outlook_spanish_without_marker(self):
        text = "mirá esta\n\nDe: Ana Pérez <ana@acme.example>\nEnviado: lunes, 23 de noviembre de 2026 10:00\nPara: Alex\nAsunto: Puesto backend\n\nHola Alex, ..."
        note, headers, body = mf.split_forward(text, "RV: Puesto backend")
        self.assertEqual(note, "mirá esta")
        self.assertEqual(headers["from"], "Ana Pérez <ana@acme.example>")
        self.assertEqual(headers["subject"], "Puesto backend")
        self.assertEqual(body, "Hola Alex, ...")

    def test_underscore_line_alone_is_not_a_forward(self):
        text = "Best regards,\nSofia\n\n________________________________\n\nThis email may contain confidential information."
        self.assertIsNone(mf.split_forward(text, "Technical interview"))

    def test_mail_without_message_id_uses_its_bytes(self):
        raw = b"From: a@example.com\r\nSubject: hi\r\n\r\nbody\r\n"
        the_id, day, _ = mf.normalize(raw)
        self.assertEqual(the_id, hashlib.sha1(raw).hexdigest()[:12])
        self.assertEqual(day, "0000-00-00")


class FakeIMAP:
    """Just enough of imaplib.IMAP4 to serve the fixtures, recording every command."""

    def __init__(self, mails, uidvalidity=1, dates=None):
        self.mails = dict(mails)          # uid -> raw bytes
        self.uidvalidity = uidvalidity
        self.dates = dates or {}          # uid -> date, for SINCE
        self.commands = []
        self.pending_uidvalidity = None

    def select(self, mailbox, readonly=False):
        self.commands.append(("EXAMINE" if readonly else "SELECT", mailbox))
        self.pending_uidvalidity = str(self.uidvalidity).encode()
        return "OK", [str(len(self.mails)).encode()]

    def response(self, code):
        value, self.pending_uidvalidity = self.pending_uidvalidity, None
        return code, [value]

    def uid(self, command, *args):
        self.commands.append((command, *args))
        if command == "SEARCH":
            uids = sorted(self.mails)
            if args[0] == "UID":
                low = int(args[1].split(":")[0])
                hits = [u for u in uids if u >= low] or uids[-1:]  # n:* always matches the last mail
            elif args[0] == "SINCE":
                since = datetime.strptime(args[1], "%d-%b-%Y").date()
                hits = [u for u in uids if self.dates.get(u, since) >= since]
            else:
                hits = uids
            return "OK", [" ".join(map(str, hits)).encode()]
        if command == "FETCH":
            assert args[1] == "(UID BODY.PEEK[])", args
            data = []
            for u in map(int, args[0].split(",")):
                data += [(f"{u} (UID {u} BODY[] {{{len(self.mails[u])}}}".encode(), self.mails[u]), b")"]
            return "OK", data
        raise AssertionError(command)

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent Items"']

    def logout(self):
        self.commands.append(("LOGOUT",))


CONFIG = {"host": "imap.example.com", "port": 993, "user": "u", "password": "p", "folder": "INBOX"}


class Imap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.raws = [p.read_bytes() for p in sorted(FIXTURES.glob("*.eml"))]
        self.server = FakeIMAP({i + 1: raw for i, raw in enumerate(self.raws)})
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, **kw):
        return mf.fetch_imap(CONFIG, self.ws, connect_fn=lambda c: self.server, log=self.logs.append, **kw)

    def files(self, ws):
        return {p.name: p.read_text(encoding="utf-8") for p in (Path(ws) / "mail" / "inbox").glob("*.md")}

    def state(self):
        return json.loads((self.ws / "mail" / "state.json").read_text(encoding="utf-8"))

    def test_imap_produces_the_same_files_as_import(self):
        new, seen, failed = self.fetch()
        self.assertEqual((len(new), seen, failed), (len(self.raws), 0, 0))
        with tempfile.TemporaryDirectory() as other:
            mf.import_eml([FIXTURES], other)
            self.assertEqual(self.files(self.ws), self.files(other))

    def test_read_only(self):
        self.fetch()
        names = {c[0] for c in self.server.commands}
        self.assertIn("EXAMINE", names)
        self.assertTrue(names <= {"EXAMINE", "SEARCH", "FETCH", "LOGOUT"}, names)

    def test_second_run_downloads_nothing(self):
        self.fetch()
        fetches = sum(c[0] == "FETCH" for c in self.server.commands)
        new, seen, failed = self.fetch()
        self.assertEqual((len(new), seen, failed), (0, 0, 0))
        self.assertEqual(sum(c[0] == "FETCH" for c in self.server.commands), fetches)  # n:* returned only the last UID
        self.assertEqual(self.state()["last_uid"], len(self.raws))
        self.assertEqual(self.state()["uidvalidity"], 1)

    def test_only_new_mail_is_downloaded(self):
        self.server.mails = {1: self.raws[0], 2: self.raws[1]}
        self.fetch()
        self.server.mails[3] = self.raws[2]
        new, seen, _ = self.fetch()
        self.assertEqual((len(new), seen), (1, 0))
        self.assertEqual(self.server.commands[-2], ("FETCH", "3", "(UID BODY.PEEK[])"))

    def test_uidvalidity_change_rescans_without_duplicates(self):
        self.fetch()
        before = self.files(self.ws)
        self.server.uidvalidity = 2
        self.server.mails = {i + 10: raw for i, raw in enumerate(self.raws)}
        new, seen, failed = self.fetch()
        self.assertEqual((len(new), seen, failed), (0, len(self.raws), 0))
        self.assertEqual(self.files(self.ws), before)
        self.assertEqual((self.state()["uidvalidity"], self.state()["last_uid"]), (2, len(self.raws) + 9))

    def test_imported_mail_is_not_downloaded_again(self):
        mf.import_eml([FIXTURES], self.ws)
        new, seen, _ = self.fetch()
        self.assertEqual((len(new), seen), (0, len(self.raws)))

    def test_since_searches_by_date(self):
        from datetime import date
        self.server.dates = {1: date(2026, 10, 1), 2: date(2026, 11, 2), 3: date(2026, 11, 3)}
        self.server.mails = {1: self.raws[0], 2: self.raws[1], 3: self.raws[2]}
        new, _, _ = self.fetch(since="2026-11-01")
        self.assertEqual(len(new), 2)
        self.assertIn(("SEARCH", "SINCE", "01-Nov-2026"), self.server.commands)

    def test_server_order_body_before_uid(self):
        raw = self.raws[0]
        data = [(f"1 (BODY[] {{{len(raw)}}}".encode(), raw), b" UID 7)"]
        server = types.SimpleNamespace(uid=lambda *a: ("OK", data))
        self.assertEqual(mf.fetch_raw(server, [7]), {7: raw})

    def test_test_connection_lists_folders(self):
        mf.test_connection(CONFIG, self.ws, connect_fn=lambda c: self.server, log=self.logs.append)
        self.assertIn("  Sent Items", self.logs)
        self.assertIn(f"INBOX: {len(self.raws)} mails, none downloaded yet", self.logs)

    def test_quoted_mailbox(self):
        self.assertEqual(mf._quote_mailbox("INBOX"), "INBOX")
        self.assertEqual(mf._quote_mailbox("[Gmail]/All Mail"), '"[Gmail]/All Mail"')


class Config(unittest.TestCase):
    def test_env_file_and_environment_override(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / ".env").write_text(
                "# comment\nIMAP_HOST=imap.example.com\nIMAP_USER=a@example.com\nIMAP_PASSWORD=\"abcd efgh\"\n",
                encoding="utf-8",
            )
            config = mf.load_config(ws, environ={"IMAP_USER": "b@example.com"})
            self.assertEqual(config, {"host": "imap.example.com", "port": 993, "user": "b@example.com",
                                      "password": "abcd efgh", "folder": "INBOX"})

    def test_missing_settings_do_not_show_the_password(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / ".env").write_text("IMAP_PASSWORD=secret\n", encoding="utf-8")
            with self.assertRaises(mf.ConfigError) as ctx:
                mf.load_config(ws, environ={})
            self.assertIn("IMAP_HOST", str(ctx.exception))
            self.assertNotIn("secret", str(ctx.exception))

    def test_imap_date_uses_english_months(self):
        self.assertEqual(mf.imap_date("2026-03-05"), "05-Mar-2026")


if __name__ == "__main__":
    unittest.main()
