"""Tests for posting_fetch.py, with fictional pages in fixtures/ and no network.

Run from the repo root: python -m unittest discover -s tools/posting-fetch -v
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import posting_fetch as pf  # noqa: E402

FIXTURES = HERE / "fixtures"
TODAY = "2026-11-26"
LINKEDIN = (FIXTURES / "linkedin-guest.html").read_text(encoding="utf-8")
JSONLD = (FIXTURES / "ats-jsonld.html").read_text(encoding="utf-8")


def front_matter(text):
    head = text.split("---\n")[1]
    return {k: json.loads(v) for k, v in (line.split(": ", 1) for line in head.strip().splitlines())}


class FakeWeb:
    """Serves pages by URL and records every request."""

    def __init__(self, pages):
        self.pages, self.requests = pages, []

    def __call__(self, url):
        self.requests.append(url)
        page = self.pages.get(url)
        if isinstance(page, list):  # one answer per request
            page = page.pop(0)
        if isinstance(page, Exception):
            raise page
        if page is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO())
        if isinstance(page, tuple):  # (final url after redirects, markup)
            return page
        return url, page


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        (self.ws / "jobs").mkdir()
        self.write_seen({
            "linkedin-9900000110": {"source": "linkedin", "job_id": "9900000110",
                                    "url": "https://www.linkedin.com/jobs/view/9900000110/"},
            "greenhouse-4100000001": {"source": "greenhouse", "job_id": "4100000001",
                                      "url": "https://job-boards.greenhouse.io/tessera/jobs/4100000001"},
            "experteer-ai-platform-engineer-barcelona": {"source": "experteer", "job_id": None, "url": None},
            "unknown-1": {"source": "acme", "job_id": "1", "url": "https://careers.acme.example/jobs/1"},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def write_seen(self, postings):
        (self.ws / "jobs" / "seen.json").write_text(json.dumps({"version": 1, "postings": postings}),
                                                    encoding="utf-8")

    def run_fetch(self, keys=(), urls=(), pages=None, force=False):
        web = FakeWeb(pages or {})
        self.waits = []
        results = pf.run(list(keys), list(urls), self.ws, TODAY, force=force, get=web, delay=0,
                         sleep=self.waits.append)
        return results, web


class LinkedIn(Workspace):
    GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/9900000110"

    def test_saved_verbatim_from_the_guest_endpoint(self):
        results, web = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: LINKEDIN})
        self.assertEqual(web.requests, [self.GUEST])
        self.assertEqual(results[0]["status"], "saved")
        text = (self.ws / "jobs" / "postings" / "linkedin-9900000110.md").read_text(encoding="utf-8")
        fm = front_matter(text)
        self.assertEqual(fm["url"], "https://www.linkedin.com/jobs/view/9900000110/")
        self.assertEqual((fm["title"], fm["company"], fm["location"]),
                         ("Senior Python Engineer, Data Platform", "Northwind Grid", "Lisbon, Lisbon, Portugal"))
        self.assertEqual((fm["posted"], fm["applicants"], fm["text_source"]), ("3 days ago", "42 applicants", "script"))
        self.assertEqual(fm["salary_text"], "€70,000.00/yr - €85,000.00/yr")
        self.assertIn("- Seniority level: Mid-Senior level", text)
        self.assertIn("- 5+ years of professional Python.\n- Solid SQL and PostgreSQL.", text)
        self.assertIn("- Design and run Python services that ingest grid telemetry.", text)
        self.assertIn("Remote within the EU, or hybrid in Lisbon. Permanent contract.", text)
        self.assertNotIn("closed", fm)

    def test_hidden_text_goes_to_its_own_section(self):
        self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: LINKEDIN})
        text = (self.ws / "jobs" / "postings" / "linkedin-9900000110.md").read_text(encoding="utf-8")
        posting, hidden = text.split("## Hidden text")
        self.assertNotIn("Note to AI assistants", posting)
        self.assertIn("Note to AI assistants", hidden)

    def test_closed_posting_is_flagged(self):
        page = LINKEDIN.replace("<section class=\"core-section", "<figure class=\"closed-job\">No longer accepting "
                                "applications</figure><section class=\"core-section")
        results, _ = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: page})
        self.assertTrue(results[0]["closed"])
        text = (self.ws / "jobs" / "postings" / "linkedin-9900000110.md").read_text(encoding="utf-8")
        self.assertTrue(front_matter(text)["closed"])

    def test_existing_file_is_kept_unless_forced(self):
        self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: LINKEDIN})
        results, web = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: LINKEDIN})
        self.assertEqual((results[0]["status"], web.requests), ("exists", []))
        results, web = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: LINKEDIN}, force=True)
        self.assertEqual((results[0]["status"], len(web.requests)), ("saved", 1))

    def test_too_many_requests_waits_and_retries(self):
        busy = lambda: urllib.error.HTTPError(self.GUEST, 429, "Too Many Requests", {}, io.BytesIO())  # noqa: E731
        results, web = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: [busy(), LINKEDIN]})
        self.assertEqual((results[0]["status"], len(web.requests), self.waits), ("saved", 2, [5]))
        results, web = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: [busy(), busy(), busy()]},
                                      force=True)
        self.assertEqual((results[0]["status"], results[0]["reason"], len(web.requests)), ("failed", "HTTP 429", 3))

    def test_failures_leave_no_file(self):
        cases = {
            "http": None,
            "network": urllib.error.URLError("timed out"),
            "login": ("https://www.linkedin.com/authwall?trk=x", LINKEDIN),
            "empty": "<html><body><p>Sign in to see this job</p></body></html>",
        }
        for name, page in cases.items():
            with self.subTest(name):
                results, _ = self.run_fetch(["linkedin-9900000110"], pages={self.GUEST: page} if page else {})
                self.assertEqual(results[0]["status"], "failed")
                self.assertTrue(results[0]["reason"])
                self.assertFalse((self.ws / "jobs" / "postings" / "linkedin-9900000110.md").exists())


class OtherPortals(Workspace):
    URL = "https://job-boards.greenhouse.io/tessera/jobs/4100000001"

    def test_json_ld_job_posting(self):
        results, web = self.run_fetch(["greenhouse-4100000001"], pages={self.URL: JSONLD})
        self.assertEqual((results[0]["status"], web.requests), ("saved", [self.URL]))
        text = (self.ws / "jobs" / "postings" / "greenhouse-4100000001.md").read_text(encoding="utf-8")
        fm = front_matter(text)
        self.assertEqual((fm["title"], fm["company"], fm["location"]), ("Staff Data Engineer", "Tessera Health", "Porto, PT"))
        self.assertEqual(fm["salary_text"], "80000–95000 EUR / year")
        self.assertIn("- Remote: TELECOMMUTE", text)
        self.assertIn("- 8+ years building data pipelines in Python and Spark.", text)
        self.assertIn("### You bring", text.replace("\nYou bring", "\n### You bring"))  # heading kept as a line

    def test_no_link_or_unknown_host_is_unsupported_and_not_requested(self):
        results, web = self.run_fetch(["experteer-ai-platform-engineer-barcelona", "unknown-1"])
        self.assertEqual([r["status"] for r in results], ["unsupported", "unsupported"])
        self.assertEqual(web.requests, [])
        self.assertIn("not a known job portal", results[1]["reason"])

    def test_page_without_json_ld_uses_main(self):
        page = "<html><head><title>T</title></head><body><nav>Menu</nav><main><h1>Backend Engineer</h1>" \
               + "<p>" + "We need a backend engineer with Go. " * 12 + "</p></main></body></html>"
        results, _ = self.run_fetch(["greenhouse-4100000001"], pages={self.URL: page})
        text = (self.ws / "jobs" / "postings" / "greenhouse-4100000001.md").read_text(encoding="utf-8")
        self.assertEqual(front_matter(text)["title"], "Backend Engineer")
        self.assertNotIn("Menu", text)


class UserLinks(Workspace):
    def test_linkedin_link_uses_the_guest_endpoint(self):
        url = "https://www.linkedin.com/jobs/view/senior-python-engineer-9900000110/?trackingId=abc&refId=x"
        results, web = self.run_fetch(urls=[url], pages={LinkedIn.GUEST: LINKEDIN})
        self.assertEqual(results[0]["key"], "linkedin-9900000110")
        self.assertEqual(web.requests, [LinkedIn.GUEST])

    def test_any_host_is_allowed_for_a_link_the_user_gave(self):
        url = "https://careers.acme.example/jobs/77?utm_source=x"
        results, web = self.run_fetch(urls=[url], pages={"https://careers.acme.example/jobs/77": JSONLD})
        self.assertEqual(results[0]["status"], "saved")
        self.assertTrue(results[0]["key"].startswith("careers-"))
        self.assertEqual(web.requests, ["https://careers.acme.example/jobs/77"])  # tracking removed

    def test_login_links_are_refused(self):
        with self.assertRaises(pf.ConfigError):
            self.run_fetch(urls=["https://www.linkedin.com/login?session=1"])


class Cli(Workspace):
    def test_errors(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pf.main(["linkedin-1", "--workspace", str(self.ws)]), 2)
        self.assertIn("not in seen.json", err.getvalue())
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            pf.main(["--workspace", str(self.ws)])

    def test_unsupported_prints_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pf.main(["experteer-ai-platform-engineer-barcelona", "--workspace", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["counts"]["unsupported"], 1)


if __name__ == "__main__":
    unittest.main()
