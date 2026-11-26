"""Tests for job_filter.py: the demo postings of examples/alex-morgan/jobs/extracted/ and edge cases.

Run from the repo root: python -m unittest discover -s tools/job-filter -v  (needs PyYAML)
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import job_filter as jf  # noqa: E402

DEMO = HERE.parents[1] / "examples" / "alex-morgan"
EXTRACTED = DEMO / "jobs" / "extracted"
# Mail IDs of the demo alerts, oldest mail first: 04, 03, 01, 02, 05, 06.
ORDER = ["8a546b3012a3", "407fbddfa9d9", "d02af533b6b7", "bd6a1c2978cf", "c42ac909f0dc", "eecd5fdd45fd"]
TODAY = "2026-11-25"

CRITERIA_MD = """---
filter:
  role_families:
    include: [backend, data]
    exclude: [sales]
    definitions:
      backend: "Backend Engineer"
      data: "Data Engineer"
  title_exclude: [junior, prácticas, sales engineer]
  seniority:
    exclude: [intern, junior]
  remote:
    countries: [ES, EU]
  onsite:
    cities: [Madrid, A Coruña]
  salary_floor:
    annualize: {month: 14, day: 220, hour: 1760}
    remote: {EUR: 60000}
    hybrid: {EUR: 65000}
    onsite: {EUR: 70000, USD: 90000}
  company_blocklist: [Evil Corp S.L.]
max_detailed: 15
---

# Job search criteria
"""


def posting(**fields):
    """A posting that passes CRITERIA_MD; override fields to test a rule."""
    base = {"source": "linkedin", "job_id": "9900000999", "url": "https://www.linkedin.com/jobs/view/9900000999/",
            "title": "Senior Backend Engineer", "company": "Acme Software", "location": "Spain (Remote)",
            "title_en": "Senior Backend Engineer", "role_family": "backend", "seniority": "senior",
            "modality": "remote", "country": "ES", "city": None, "contract": None, "salary_min": None,
            "salary_max": None, "salary_currency": None, "salary_period": None}
    base.update(fields)
    return base


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = jf.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class Workspace(unittest.TestCase):
    """A temporary workspace with CRITERIA_MD and an empty applications.md."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        (self.ws / "jobs").mkdir()
        (self.ws / "jobs" / "criteria.md").write_text(CRITERIA_MD, encoding="utf-8")
        self.criteria = jf.load_criteria(self.ws / "jobs" / "criteria.md")
        self.applications = []
        self.seen = {"version": 1, "postings": {}}

    def tearDown(self):
        self.tmp.cleanup()

    def run_filter(self, *postings, recheck=False, mail_id="m1"):
        return jf.filter_postings([(mail_id, list(postings))], self.criteria, self.seen, self.applications, TODAY,
                                  recheck=recheck)

    def one(self, **fields):
        self.seen = {"version": 1, "postings": {}}
        return self.run_filter(posting(**fields))[0]


class DemoAlerts(unittest.TestCase):
    """The expected outcomes in examples/alex-morgan/eml/README.md."""

    @classmethod
    def setUpClass(cls):
        cls.criteria = jf.load_criteria(DEMO / "jobs" / "criteria.md")
        cls.applications = jf.read_applications(DEMO / "applications.md")
        cls.batches = jf.read_batches([EXTRACTED / f"{m}.json" for m in ORDER])
        cls.results = jf.filter_postings(cls.batches, cls.criteria, {"version": 1, "postings": {}},
                                         cls.applications, TODAY)

    def find(self, company, title=None, mail=None):
        found = [r for r in self.results if r["company"] == company and (title is None or r["title"] == title)
                 and (mail is None or r["mail_id"] == mail)]
        self.assertEqual(len(found), 1, (company, title, mail))
        return found[0]

    def assertOutcome(self, result, decision, rule_id=None):
        self.assertEqual((result["decision"], result["rule_id"]), (decision, rule_id), result)

    def test_every_extracted_file_is_filtered(self):
        self.assertEqual(len(self.results), sum(len(b) for _, b in self.batches))
        self.assertEqual(sorted(p.stem for p in EXTRACTED.glob("*.json")), sorted(ORDER))

    def test_already_applied_is_duplicate(self):
        result = self.find("Tessera Health", "Senior Data Platform Engineer")
        self.assertOutcome(result, "duplicate")
        self.assertIn("applications.md", result["duplicate_of"])

    def test_same_company_as_an_application_is_repost(self):
        result = self.find("Tessera Health", "Staff Data Engineer")
        self.assertOutcome(result, "repost")
        self.assertEqual(result["repost_of"][0]["application"]["role"], "Senior Data Platform Engineer")
        self.assertEqual(result["repost_of"][0]["application"]["status"], "sent")

    def test_rejections_cite_their_rule(self):
        self.assertOutcome(self.find("Ardent Robotics"), "reject", "title_exclude")
        self.assertOutcome(self.find("Saltmarsh Mobility"), "reject", "location")
        self.assertOutcome(self.find("Veridian Ledger"), "reject", "salary_floor")
        self.assertOutcome(self.find("Moonrise Data"), "reject", "role_family")
        self.assertOutcome(self.find("Brindle Retail"), "reject", "role_family")
        self.assertOutcome(self.find("Ostrava Freight"), "reject", "location")
        for r in self.results:
            if r["decision"] == "reject":
                self.assertIn(r["rule_id"], jf.RULES)
                self.assertTrue(r["reason"])

    def test_passing_postings(self):
        self.assertOutcome(self.find("Northwind Grid"), "pass")
        for company in ("Kestrel Analytics", "Copperline Pay", "Glasshouse Studio"):
            result = self.find(company, mail=None if company != "Kestrel Analytics" else "d02af533b6b7")
            self.assertOutcome(result, "maybe")
            self.assertEqual(result["missing"], ["seniority"])

    def test_same_posting_in_a_later_mail_is_duplicate(self):
        self.assertOutcome(self.find("Kestrel Analytics", mail="bd6a1c2978cf"), "duplicate")

    def test_no_work_mode_is_maybe(self):
        for company in ("Lumen & Hale Consulting", "Pinecrest Labs", "Harbor & Vine"):
            result = self.find(company)
            self.assertOutcome(result, "maybe")
            self.assertIn("modality", result["missing"])

    def test_tecnoempleo(self):
        self.assertOutcome(self.find("Nimbo Software"), "reject", "location")
        self.assertOutcome(self.find("Grupo Arcadia IT"), "reject", "location")
        self.assertOutcome(self.find("Ébano Consultores"), "reject", "title_exclude")
        self.assertOutcome(self.find("Teleférico Cloud"), "reject", "location")

    def test_experteer_postings_have_no_id_and_no_salary(self):
        experteer = [r for r in self.results if r["mail_id"] == "eecd5fdd45fd"]
        self.assertEqual(len(experteer), 4)
        self.assertEqual(len({r["key"] for r in experteer}), 4)
        for r in experteer:
            self.assertTrue(r["key"].startswith("experteer-"))
            self.assertOutcome(r, "maybe")

    def test_output_is_deterministic(self):
        again = jf.filter_postings(jf.read_batches([EXTRACTED / f"{m}.json" for m in ORDER]), self.criteria,
                                   {"version": 1, "postings": {}}, jf.read_applications(DEMO / "applications.md"),
                                   TODAY)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.results, sort_keys=True))


class Rules(Workspace):
    def test_baseline_passes(self):
        result = self.one()
        self.assertEqual(result["decision"], "pass", result)
        self.assertEqual(result["missing"], [])

    def test_role_family(self):
        self.assertEqual(self.one(role_family="sales")["rule_id"], "role_family")
        self.assertEqual(self.one(role_family="sales")["decision"], "reject")
        # defined but neither included nor excluded: not wanted
        self.criteria["definitions"].append("ops")
        self.criteria["families"].add("ops")
        self.assertEqual(self.one(role_family="ops")["rule_id"], "role_family")
        self.assertEqual(self.one(role_family="other")["decision"], "maybe")
        self.assertEqual(self.one(role_family="other")["missing"], ["role_family"])

    def test_title_exclude_whole_words_without_case_or_accents(self):
        self.assertEqual(self.one(title="JUNIOR Backend Engineer")["rule_id"], "title_exclude")
        self.assertEqual(self.one(title="Prácticas: Backend", title_en="Backend internship")["rule_id"],
                         "title_exclude")
        self.assertEqual(self.one(title="Practicas Backend", title_en=None)["rule_id"], "title_exclude")
        self.assertEqual(self.one(title="Backend Engineer", title_en="Junior Backend Engineer")["rule_id"],
                         "title_exclude")
        self.assertEqual(self.one(title="Sales Engineer", title_en=None)["rule_id"], "title_exclude")  # phrase
        self.assertEqual(self.one(title="Juniors Backend Engineer", title_en=None)["decision"], "pass")
        self.assertEqual(self.one(title="Engineer, Sales Platform", title_en=None)["decision"], "pass")

    def test_seniority(self):
        self.assertEqual(self.one(seniority="junior")["rule_id"], "seniority")
        self.assertEqual(self.one(seniority="lead")["decision"], "pass")
        self.assertEqual(self.one(seniority=None)["decision"], "maybe")

    def test_remote_country_is_literal(self):
        self.assertEqual(self.one(country="EU")["decision"], "pass")
        self.assertEqual(self.one(country="es")["decision"], "pass")
        result = self.one(country="PT")
        self.assertEqual((result["decision"], result["rule_id"]), ("reject", "location"))
        self.assertEqual(self.one(country="WORLD")["rule_id"], "location")  # regions are listed explicitly
        # the city is ignored for remote roles: portals sometimes put the user's own city there
        self.assertEqual(self.one(country="ES", city="Valencia")["decision"], "pass")

    def test_hybrid_and_onsite_cities(self):
        self.assertEqual(self.one(modality="hybrid", city="madrid", country="ES")["decision"], "pass")
        self.assertEqual(self.one(modality="onsite", city="A Coruna", country="ES")["decision"], "pass")
        self.assertEqual(self.one(modality="onsite", city="Barcelona", country="ES")["rule_id"], "location")
        result = self.one(modality="hybrid", city=None, country="ES")
        self.assertEqual((result["decision"], result["missing"]), ("maybe", ["city"]))

    def test_salary_floor_and_annualization(self):
        def salary(amount, period, currency="EUR", **kw):
            return self.one(salary_max=amount, salary_currency=currency, salary_period=period, **kw)

        self.assertEqual(salary(59000, "year")["rule_id"], "salary_floor")
        self.assertEqual(salary(60000, "year")["decision"], "pass")
        self.assertEqual(salary(4200, "month")["rule_id"], "salary_floor")       # 58,800
        self.assertEqual(salary(4300, "month")["decision"], "pass")              # 60,200
        self.assertEqual(salary(270, "day")["rule_id"], "salary_floor")          # 59,400
        self.assertEqual(salary(35, "hour")["decision"], "pass")                 # 61,600
        self.assertEqual(salary(64000, "year", modality="hybrid", city="Madrid")["rule_id"], "salary_floor")
        self.assertEqual(salary(69000, "year", modality="onsite", city="Madrid")["rule_id"], "salary_floor")
        # salary_min is used when there is no maximum
        result = self.one(salary_min=50000, salary_currency="EUR", salary_period="year")
        self.assertEqual(result["rule_id"], "salary_floor")

    def test_salary_floor_does_not_apply(self):
        cases = [
            dict(salary_max=100, salary_currency="EUR", salary_period="day", contract="freelance"),
            dict(salary_max=100, salary_currency="EUR", salary_period="day", contract="contractor"),
            dict(salary_max=30000, salary_currency="GBP", salary_period="year"),     # no floor in GBP
            dict(salary_max=30000, salary_currency="USD", salary_period="year"),     # USD floor only on-site
            dict(salary_max=3000, salary_currency="EUR", salary_period=None),        # period unknown
            dict(salary_max=3000, salary_currency=None, salary_period="month"),      # currency unknown
            dict(salary_text="Competitive"),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(self.one(**case)["decision"], "pass")

    def test_unknown_work_mode_uses_the_lowest_floor(self):
        result = self.one(modality=None, salary_max=62000, salary_currency="EUR", salary_period="year")
        self.assertEqual(result["decision"], "maybe")  # 62,000 meets the remote floor, the lowest
        result = self.one(modality=None, salary_max=58000, salary_currency="EUR", salary_period="year")
        self.assertEqual(result["rule_id"], "salary_floor")
        result = self.one(modality=None, salary_max=80000, salary_currency="USD", salary_period="year")
        self.assertEqual(result["rule_id"], "salary_floor")  # USD has a single floor (on-site)

    def test_company_blocklist_normalizes_names(self):
        self.assertEqual(self.one(company="EVIL CORP")["rule_id"], "company_blocklist")
        self.assertEqual(self.one(company="Evil Corp, S.L.U. España")["rule_id"], "company_blocklist")
        self.assertEqual(self.one(company="Evil Corporation Labs")["decision"], "pass")

    def test_first_rejecting_rule_wins(self):
        result = self.one(role_family="sales", title="Junior Sales", seniority="junior")
        self.assertEqual(result["rule_id"], "role_family")

    def test_unconfigured_rules_are_skipped(self):
        (self.ws / "jobs" / "criteria.md").write_text("---\nfilter: {}\n---\n", encoding="utf-8")
        self.criteria = jf.load_criteria(self.ws / "jobs" / "criteria.md")
        result = self.one(role_family=None, seniority=None, modality=None, country=None)
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(self.one(role_family=None, seniority="junior", country="US")["decision"], "pass")


class NullNeverRejects(Workspace):
    REJECTS = {  # a posting rejected by each rule, and the fields whose absence must stop the rejection
        "role_family": (dict(role_family="sales"), ["role_family"]),
        "seniority": (dict(seniority="junior"), ["seniority"]),
        "location": (dict(country="PT"), ["country", "modality"]),
        "salary_floor": (dict(salary_max=40000, salary_currency="EUR", salary_period="year"),
                         ["salary_max", "salary_currency", "salary_period"]),
    }

    def test_nulling_the_deciding_field_never_rejects(self):
        for rule, (fields, deciding) in self.REJECTS.items():
            self.assertEqual(self.one(**fields)["rule_id"], rule)
            for field in deciding:
                with self.subTest(rule=rule, field=field):
                    result = self.one(**{**fields, field: None})
                    self.assertNotEqual(result["decision"], "reject", result)

    def test_all_normalized_fields_null(self):
        result = self.one(**{f: None for f in jf.NORMALIZED})
        self.assertEqual(result["decision"], "maybe")
        self.assertEqual(set(result["missing"]), {"role_family", "seniority", "modality"})

    def test_invalid_values_become_null(self):
        invalid = {
            "role_family": "Sales & Marketing", "seniority": "mid-senior", "modality": "remote-first",
            "country": "Spain", "contract": "permanent", "salary_min": "60K", "salary_max": True,
            "salary_currency": "€", "salary_period": "annual", "city": 28001,
        }
        result = self.one(**invalid)
        self.assertNotEqual(result["decision"], "reject")
        self.assertEqual(set(result["invalid"]), set(invalid))
        self.assertTrue(set(invalid) <= set(result["missing"]))
        # each one alone, on a posting that some rule would reject with the bad value read literally
        for field, value in invalid.items():
            with self.subTest(field=field):
                result = self.one(**{field: value})
                self.assertNotEqual(result["decision"], "reject", result)
                self.assertIn(field, result["missing"])

    def test_implausible_salary_for_its_period_is_invalid(self):
        # LinkedIn showed "30 €-45 € / año": an hourly rate labelled as yearly
        result = self.one(salary_min=30, salary_max=45, salary_currency="EUR", salary_period="year")
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(set(result["invalid"]), {"salary_min", "salary_max"})
        # the same amount as an hourly rate is plausible and judged: 30 × 1,760 = 52,800 < 60,000
        self.assertEqual(self.one(salary_max=30, salary_currency="EUR", salary_period="hour")["rule_id"],
                         "salary_floor")

    def test_salary_min_above_max_is_invalid(self):
        result = self.one(salary_min=90000, salary_max=40000, salary_currency="EUR", salary_period="year")
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(set(result["invalid"]), {"salary_min", "salary_max"})


class Deduplication(Workspace):
    def test_duplicate_by_id_and_by_name(self):
        first = self.run_filter(posting())[0]
        self.assertEqual(first["decision"], "pass")
        again = self.run_filter(posting(title="Renamed"), mail_id="m2")[0]
        self.assertEqual((again["decision"], again["duplicate_of"]), ("duplicate", "linkedin-9900000999"))
        # no ID: company + title, normalized
        self.run_filter(posting(source="infojobs", job_id=None, url=None, company="Beta Datos S.L.",
                                title="Ingeniero de Datos", role_family="data"))
        dup = self.run_filter(posting(source="tecnoempleo", job_id=None, url=None, company="BETA DATOS, S.L.U.",
                                      title="Ingeniero de datos", role_family="data"))[0]
        self.assertEqual(dup["decision"], "duplicate")

    def test_duplicate_records_the_date_and_mail(self):
        self.run_filter(posting())
        jf.filter_postings([("m2", [posting()])], self.criteria, self.seen, self.applications, "2026-11-30")
        entry = self.seen["postings"]["linkedin-9900000999"]
        self.assertEqual(entry["seen"], [TODAY, "2026-11-30"])
        self.assertEqual(entry["mail_ids"], ["m1", "m2"])
        self.assertEqual(entry["filter"]["decision"], "pass")

    def test_repost_needs_same_company_and_role_family(self):
        self.run_filter(posting())
        repost = self.run_filter(posting(job_id="9900000998", url=None, title="Backend Engineer II"))[0]
        self.assertEqual(repost["decision"], "repost")
        self.assertEqual(repost["repost_of"][0]["seen"]["key"], "linkedin-9900000999")
        other_role = self.run_filter(posting(job_id="9900000997", url=None, title="Data Engineer",
                                             title_en="Data Engineer", role_family="data"))[0]
        self.assertEqual(other_role["decision"], "pass")

    def test_repost_that_breaks_a_rule_is_rejected(self):
        self.run_filter(posting())
        result = self.run_filter(posting(job_id="9900000998", url=None, seniority="junior"))[0]
        self.assertEqual((result["decision"], result["rule_id"]), ("reject", "seniority"))
        self.assertTrue(result["repost_of"])

    def test_job_id_is_taken_from_the_url(self):
        result = self.run_filter(posting(source=None, job_id=None,
                                         url="https://www.linkedin.com/jobs/view/senior-backend-9900000555/"))[0]
        self.assertEqual(result["key"], "linkedin-9900000555")
        self.assertEqual(jf.id_from_url("https://www.tecnoempleo.com/x/y/rf-a1b2c3d4e5f60718293a"),
                         ("tecnoempleo", "a1b2c3d4e5f60718293a"))
        self.assertEqual(jf.id_from_url("https://boards.greenhouse.io/acme/jobs/4012345"), ("greenhouse", "4012345"))
        self.assertEqual(jf.id_from_url("https://jobs.example.com/acme/backend"), (None, None))


class Applications(Workspace):
    LOG = """# Postulaciones

Estados: `?` · `enviada` · `entrevista` · `rechazada`

| Fecha | Empresa | Puesto | Carpeta | Aviso | Estado | Notas |
|---|---|---|---|---|---|---|
| 2026-11-20 | Acme Software | Senior Backend Engineer | `output/acme/` | [aviso](https://www.linkedin.com/jobs/view/9900000999/) | enviada | |
| 2026-11-10 | Gamma Labs S.A. | Ingeniero/a de Datos | `output/gamma/` | | rechazada | AWS |
| 2026-11-01 | Delta Cloud | Backend Engineer | `output/delta/` | https://delta.example/careers/42 | entrevista | |
"""

    def setUp(self):
        super().setUp()
        path = self.ws / "applications.md"
        path.write_text(self.LOG, encoding="utf-8")
        self.applications = jf.read_applications(path)

    def test_rows_are_read_by_position(self):
        self.assertEqual(len(self.applications), 3)
        first = self.applications[0]
        self.assertEqual((first["company"], first["source"], first["job_id"], first["status"]),
                         ("Acme Software", "linkedin", "9900000999", "enviada"))
        self.assertEqual(first["folder"], "output/acme/")
        self.assertIsNone(self.applications[1]["url"])

    def test_applied_by_link_id(self):
        result = self.run_filter(posting(title="Something else"))[0]
        self.assertEqual(result["decision"], "duplicate")
        self.assertIn("enviada", result["reason"])
        self.assertEqual(self.seen["postings"]["linkedin-9900000999"]["application"]["status"], "enviada")

    def test_applied_by_name_when_the_row_has_no_usable_link(self):
        result = self.run_filter(posting(job_id="9900000111", url=None, company="Gamma Labs",
                                         title="Ingeniero/a de datos", role_family="data"))[0]
        self.assertEqual(result["decision"], "duplicate")
        result = self.run_filter(posting(job_id="9900000112", url=None, company="Delta Cloud",
                                         title="Backend Engineer"))[0]
        self.assertEqual(result["decision"], "duplicate")

    def test_same_company_other_role_is_repost(self):
        result = self.run_filter(posting(job_id="9900000113", url=None, company="Gamma Labs",
                                         title="Senior Data Engineer", title_en=None, role_family="data"))[0]
        self.assertEqual(result["decision"], "repost")
        self.assertEqual(result["repost_of"][0]["application"]["status"], "rechazada")
        self.assertEqual(result["repost_of"][0]["application"]["notes"], "AWS")


class Recheck(Workspace):
    def test_second_pass_with_the_full_posting(self):
        first = self.run_filter(posting(modality=None, country=None))[0]
        self.assertEqual(first["decision"], "maybe")
        second = self.run_filter({"source": "linkedin", "job_id": "9900000999", "modality": "onsite",
                                  "city": "Barcelona", "country": "ES"}, recheck=True)[0]
        self.assertEqual((second["decision"], second["rule_id"]), ("reject", "location"))
        entry = self.seen["postings"]["linkedin-9900000999"]
        self.assertEqual(entry["filter"]["pass"], 2)
        self.assertEqual(entry["title"], "Senior Backend Engineer")  # kept from the first pass
        self.assertEqual(entry["city"], "Barcelona")
        self.assertEqual(len(self.seen["postings"]), 1)

    def test_second_pass_is_not_recorded_as_a_mail(self):
        self.run_filter(posting(modality=None), mail_id="mail1")
        self.run_filter(posting(modality="remote"), recheck=True, mail_id="recheck-linkedin-9900000999")
        self.assertEqual(self.seen["postings"]["linkedin-9900000999"]["mail_ids"], ["mail1"])

    def test_without_recheck_it_is_a_duplicate(self):
        self.run_filter(posting())
        self.assertEqual(self.run_filter(posting(), recheck=False)[0]["decision"], "duplicate")


class Criteria(Workspace):
    def write(self, text):
        path = self.ws / "jobs" / "criteria.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_templates_load(self):
        empty = jf.load_criteria(HERE.parents[1] / "workspace.example" / "jobs" / "criteria.md")
        self.assertEqual(empty["include"], [])
        self.assertEqual(empty["annualize"], {"month": 14, "day": 220, "hour": 1760})
        alex = jf.load_criteria(DEMO / "jobs" / "criteria.md")
        self.assertEqual(alex["floors"]["remote"], {"EUR": 65000})

    def test_bad_criteria_fail_loudly(self):
        bad = [
            "# no front matter\n",
            "---\nmax_detailed: 3\n---\n",
            "---\nfilter:\n  seniority:\n    exclude: [mid-senior]\n---\n",
            "---\nfilter:\n  title_exclude: junior\n---\n",
            "---\nfilter:\n  salary_floor:\n    remote: {EUR: lots}\n---\n",
            "---\nfilter:\n  salary_floor:\n    annualize: {week: 52}\n---\n",
            "---\nfilter: [\n---\n",
        ]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(jf.ConfigError):
                jf.load_criteria(self.write(text))

    def test_crlf_and_bom(self):
        path = self.ws / "jobs" / "criteria.md"
        path.write_bytes(("﻿" + CRITERIA_MD).replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(jf.load_criteria(path)["onsite_cities"], ["Madrid", "A Coruña"])


class Normalization(unittest.TestCase):
    def test_company(self):
        same = ["Acme Software", "ACME Software S.L.", "Acme Software, S.L.U.", "Acme Software España",
                "Ácme Software GmbH", "Acme Software Inc."]
        self.assertEqual({jf.normalize_company(c) for c in same}, {"acme software"})
        self.assertEqual(jf.normalize_company("Spain"), "spain")  # never empties a name
        self.assertEqual(jf.normalize_company("Lumen & Hale Consulting"), "lumen hale consulting")

    def test_title(self):
        self.assertEqual(jf.normalize_title("Ingeniero/a de Datos (Python)"), "ingeniero a de datos python")


class Cli(Workspace):
    def write_extracted(self, name, postings):
        path = self.ws / "jobs" / "extracted" / f"{name}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(postings), encoding="utf-8")
        return path

    def test_update_seen_and_explain_after_the_mail_is_gone(self):
        path = self.write_extracted("abc123def456", [posting(salary_max=50000, salary_currency="EUR",
                                                             salary_period="year")])
        code, out, err = run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["counts"]["reject"], 1)
        self.assertEqual(data["results"][0]["rule_id"], "salary_floor")
        seen = json.loads((self.ws / "jobs" / "seen.json").read_text(encoding="utf-8"))
        entry = seen["postings"]["linkedin-9900000999"]
        self.assertEqual(entry["mail_ids"], ["abc123def456"])
        self.assertEqual(entry["salary_max"], 50000)
        self.assertNotIn("description", entry)

        path.unlink()  # the mail and its extracted file are deleted (retention)
        code, out, err = run_cli("--explain", "LinkedIn-9900000999", "--workspace", self.ws)
        self.assertEqual(code, 0, err)
        self.assertIn("Recorded decision: reject (salary_floor)", out)
        for rule in jf.RULES:
            self.assertIn(rule, out)
        self.assertIn("50000 EUR/year is below the remote floor of 60000 EUR", out)

    def test_without_update_seen_nothing_is_written(self):
        path = self.write_extracted("m", [posting(), posting()])
        code, out, _ = run_cli(path, "--workspace", self.ws)
        self.assertEqual(code, 0)
        self.assertEqual([r["decision"] for r in json.loads(out)["results"]], ["pass", "duplicate"])
        self.assertFalse((self.ws / "jobs" / "seen.json").exists())

    def test_rerunning_is_idempotent(self):
        path = self.write_extracted("m", [posting(), posting(job_id="9900000123", url=None, company="Other")])
        run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        first = (self.ws / "jobs" / "seen.json").read_text(encoding="utf-8")
        code, out, _ = run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        self.assertEqual(json.loads(out)["counts"]["duplicate"], 2)
        self.assertEqual((self.ws / "jobs" / "seen.json").read_text(encoding="utf-8"), first)

    def test_errors(self):
        code, _, err = run_cli("--explain", "linkedin-1", "--workspace", self.ws)
        self.assertEqual(code, 2)
        self.assertIn("not in seen.json", err)
        bad = self.write_extracted("bad", {"not": "a list"})
        code, _, err = run_cli(bad, "--workspace", self.ws)
        self.assertEqual(code, 2)
        (self.ws / "jobs" / "criteria.md").unlink()
        code, _, err = run_cli(bad, "--workspace", self.ws)
        self.assertEqual(code, 2)
        self.assertIn("criteria.md not found", err)


class Report(Workspace):
    """--report: what the inbox shows, from seen.json alone."""

    def record(self, *postings, day=TODAY, mail_id="m1"):
        jf.filter_postings([(mail_id, list(postings))], self.criteria, self.seen, self.applications, day)

    def test_open_postings_in_queue_order_and_recent_rejections(self):
        self.applications = [{"date": "2026-10-01", "company": "Repost Co", "title": "Backend Engineer",
                              "folder": None, "url": None, "source": None, "job_id": None, "status": "sent",
                              "notes": None}]
        self.record(posting(job_id="1000001", url=None, company="Old Pass"), day="2026-11-20")
        self.record(posting(job_id="1000002", url=None, company="Maybe Co", seniority=None),
                    posting(job_id="1000003", url=None, company="Repost Co"),
                    posting(job_id="1000004", url=None, company="Busy Pass", applicants=200),
                    posting(job_id="1000005", url=None, company="Quiet Pass", applicants=12),
                    posting(job_id="1000006", url=None, company="Junior Co", title="Junior Backend Engineer"))
        self.record(posting(job_id="1000007", url=None, company="Old Reject", modality="onsite", city="Berlin"),
                    day="2026-11-10")
        data = jf.report(self.seen, TODAY)
        self.assertEqual([e["company"] for e in data["open"]],
                         ["Quiet Pass", "Busy Pass", "Old Pass", "Repost Co", "Maybe Co"])
        self.assertEqual(data["open"][3]["decision"], "repost")
        self.assertEqual(data["open"][3]["repost_of"][0]["application"]["company"], "Repost Co")
        self.assertEqual(data["open"][4]["missing"], ["seniority"])
        self.assertEqual([(e["company"], e["rule_id"]) for e in data["filtered"]], [("Junior Co", "title_exclude")])
        self.assertEqual(data["counts"], {"pass": 3, "repost": 1, "maybe": 1, "reject": 1, "to_decide": 0,
                                          "pending_text": 0})
        self.assertEqual(len(jf.report(self.seen, TODAY, days=30)["filtered"]), 2)

    def test_decided_expired_and_duplicate_postings_leave_the_inbox(self):
        self.applications = [{"date": "2026-10-01", "company": "Applied Co", "title": "Senior Backend Engineer",
                              "folder": None, "url": "https://www.linkedin.com/jobs/view/1000013/",
                              "source": "linkedin", "job_id": "1000013", "status": "sent", "notes": None}]
        self.record(posting(job_id="1000011", url=None, company="Decided"),
                    posting(job_id="1000012", url=None, company="Expired"),
                    posting(job_id="1000013", url=None, company="Applied Co"),
                    posting(job_id="1000014", url=None, company="Still Open"))
        self.seen["postings"]["linkedin-1000011"]["user_decision"] = "discard"
        self.seen["postings"]["linkedin-1000012"]["stage"] = "expired"
        self.assertEqual([e["company"] for e in jf.report(self.seen, TODAY)["open"]], ["Still Open"])

    def analyse(self, key, **fields):
        _, entry = jf.set_fields(key, [f"{k}={v}" for k, v in fields.items()], self.seen, self.ws, TODAY)
        return entry

    def test_analysed_postings_to_decide_in_card_order(self):
        companies = ["Reserved", "Discarded", "Apply Low", "Apply High", "Apply Knockout", "Queued"]
        self.record(*[posting(job_id=f"200000{i}", url=None, company=c) for i, c in enumerate(companies)])
        self.analyse("linkedin-2000000", stage="analysed", recommendation="apply_with_reservations")
        self.analyse("linkedin-2000001", stage="analysed", recommendation="discard", knockouts=1)
        self.analyse("linkedin-2000002", stage="analysed", recommendation="apply", knockouts=0, must_covered=0.5,
                     fit="high")
        self.analyse("linkedin-2000003", stage="analysed", recommendation="apply", knockouts=0, must_covered=0.9,
                     fit="medium")
        self.analyse("linkedin-2000004", stage="analysed", recommendation="apply", knockouts=1, must_covered=1)
        data = jf.report(self.seen, TODAY)
        self.assertEqual([e["company"] for e in data["to_decide"]],
                         ["Apply High", "Apply Low", "Apply Knockout", "Reserved", "Discarded"])
        self.assertEqual([e["company"] for e in data["open"]], ["Queued"])
        self.assertEqual(data["counts"]["to_decide"], 5)
        self.assertEqual(data["to_decide"][0]["stage_date"], TODAY)

    def test_second_pass_rejection_stays_to_decide(self):
        self.record(posting(modality=None))
        jf.filter_postings([("recheck", [posting(modality="onsite", city="Berlin")])], self.criteria, self.seen,
                           self.applications, TODAY, recheck=True)
        self.analyse("linkedin-9900000999", stage="analysed", recommendation="discard")
        data = jf.report(self.seen, TODAY)
        self.assertEqual([(e["key"], e["rule_id"]) for e in data["to_decide"]], [("linkedin-9900000999", "location")])
        self.assertEqual(data["filtered"], [])

    def test_pending_text_and_user_decisions(self):
        self.record(posting(job_id="3000001", url=None, company="No Text"),
                    posting(job_id="3000002", url=None, company="Decided"))
        self.analyse("linkedin-3000001", stage="pending_text")
        self.analyse("linkedin-3000002", stage="analysed", recommendation="apply")
        self.analyse("linkedin-3000002", user_decision="later", user_reason="after the Mercanis process")
        data = jf.report(self.seen, TODAY)
        self.assertEqual([e["company"] for e in data["pending_text"]], ["No Text"])
        self.assertEqual(data["open"] + data["to_decide"], [])
        entry = self.seen["postings"]["linkedin-3000002"]
        self.assertEqual((entry["user_decision"], entry["user_decision_date"]), ("later", TODAY))
        self.analyse("linkedin-3000002", recommendation="null")
        self.assertIsNone(entry["recommendation"])

    def test_set_validates(self):
        self.record(posting(), posting(job_id="4000001", url=None, company="Other"))
        (self.ws / "jobs" / "postings").mkdir()
        (self.ws / "jobs" / "postings" / "linkedin-9900000999.md").write_text("x", encoding="utf-8")
        entry = self.analyse("LinkedIn-9900000999", posting_path="jobs/postings/linkedin-9900000999.md",
                             same_as="linkedin-4000001", must_covered="0.6667")
        self.assertEqual((entry["posting_path"], entry["same_as"], entry["must_covered"]),
                         ("jobs/postings/linkedin-9900000999.md", "linkedin-4000001", 0.667))
        bad = [("linkedin-1", ["stage=analysed"]), ("linkedin-9900000999", ["description=hi"]),
               ("linkedin-9900000999", ["stage"]), ("linkedin-9900000999", ["stage=done"]),
               ("linkedin-9900000999", ["stage=null"]), ("linkedin-9900000999", ["recommendation=maybe"]),
               ("linkedin-9900000999", ["knockouts=-1"]), ("linkedin-9900000999", ["must_covered=1.5"]),
               ("linkedin-9900000999", ["fit=great"]), ("linkedin-9900000999", ["posting_path=jobs/nope.md"]),
               ("linkedin-9900000999", ["same_as=linkedin-9900000999"]), ("linkedin-9900000999", ["user_decision=yes"])]
        for key, assignments in bad:
            with self.subTest(assignments=assignments), self.assertRaises(jf.ConfigError):
                jf.set_fields(key, assignments, self.seen, self.ws, TODAY)

    def test_set_cli(self):
        path = self.ws / "jobs" / "extracted" / "m.json"
        path.parent.mkdir()
        path.write_text(json.dumps([posting()]), encoding="utf-8")
        run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        code, out, err = run_cli("--set", "linkedin-9900000999", "stage=analysed", "recommendation=apply", "fit=high",
                                 "--workspace", self.ws, "--date", TODAY)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["recommendation"], "apply")
        seen = json.loads((self.ws / "jobs" / "seen.json").read_text(encoding="utf-8"))
        self.assertEqual(seen["postings"]["linkedin-9900000999"]["fit"], "high")
        code, out, _ = run_cli("--explain", "linkedin-9900000999", "--workspace", self.ws)
        self.assertIn("Stage: analysed on 2026-11-25", out)
        code, _, err = run_cli("--set", "linkedin-9900000999", "fit=great", "--workspace", self.ws)
        self.assertEqual(code, 2)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            jf.main(["--set", "linkedin-9900000999", "--workspace", str(self.ws)])

    def test_cli(self):
        path = self.ws / "jobs" / "extracted" / "m.json"
        path.parent.mkdir()
        path.write_text(json.dumps([posting(), posting(job_id="9900000123", url=None, seniority="junior")]),
                        encoding="utf-8")
        run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        path.unlink()
        code, out, err = run_cli("--report", "--workspace", self.ws, "--date", TODAY)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["counts"], {"pass": 1, "repost": 0, "maybe": 0, "reject": 1, "to_decide": 0,
                                          "pending_text": 0})
        self.assertEqual(data["open"][0]["url"], "https://www.linkedin.com/jobs/view/9900000999/")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            jf.main(["--report", str(path), "--workspace", str(self.ws)])
        code, out, _ = run_cli("--report", "--workspace", self.ws / "nowhere")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
