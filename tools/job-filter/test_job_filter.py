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
        self.assertEqual(data["counts"], {"pass": 3, "repost": 1, "maybe": 1, "reject": 1, "to_apply": 0, "to_decide": 0,
                                          "pending_text": 0, "applied": 0})
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
        _, entry, _ = jf.set_fields(key, [f"{k}={v}" for k, v in fields.items()], self.seen, self.ws, TODAY)
        return entry

    def test_postings_applied_outside_cv_tailor_leave_the_inbox(self):
        self.record(posting(job_id="5000001", url=None, company="By Link"),
                    posting(job_id="5000002", url=None, company="By Name", title="Platform Engineer"),
                    posting(job_id="5000003", url=None, company="To Apply"),
                    posting(job_id="5000004", url=None, company="Pending"),
                    posting(job_id="5000005", url=None, company="Still Open"))
        self.analyse("linkedin-5000001", stage="analysed", recommendation="apply")
        self.analyse("linkedin-5000003", user_decision="apply")
        self.analyse("linkedin-5000004", stage="pending_text")
        log = self.ws / "applications.md"
        log.write_text("""| Date | Company | Role | Folder | Link | Status | Notes |
|---|---|---|---|---|---|---|
| 2026-11-25 | By Link | Senior Backend Engineer | — | https://www.linkedin.com/jobs/view/5000001/ | sent | Easy Apply |
| 2026-11-25 | By Name S.L. | Platform engineer | — | — | ? | |
| 2026-11-25 | To Apply | Senior Backend Engineer | `output/to-apply/` | https://www.linkedin.com/jobs/view/5000003/ | sent | |
| 2026-11-25 | Pending | Senior Backend Engineer | — | https://www.linkedin.com/jobs/view/5000004/ | sent | |
""", encoding="utf-8")
        before = copy.deepcopy(self.seen)
        data = jf.report(self.seen, TODAY, applications=jf.read_applications(log))
        self.assertEqual(self.seen, before)  # read-only
        self.assertEqual([e["company"] for e in data["open"]], ["Still Open"])
        self.assertEqual(data["to_decide"] + data["to_apply"] + data["pending_text"], [])
        self.assertEqual([(e["company"], e["application"]["status"]) for e in data["applied"]],
                         [("By Link", "sent"), ("By Name", "?"), ("To Apply", "sent"), ("Pending", "sent")])
        self.assertEqual(data["applied"][2]["user_decision"], "apply")
        self.assertEqual(data["counts"]["applied"], 4)
        # without the log (or another company's row), everything is back
        data = jf.report(self.seen, TODAY)
        self.assertEqual((len(data["to_decide"]), len(data["to_apply"]), len(data["pending_text"]), len(data["open"])),
                         (1, 1, 1, 2))

    def test_report_cli_reads_applications(self):
        path = self.ws / "jobs" / "extracted" / "m.json"
        path.parent.mkdir()
        path.write_text(json.dumps([posting()]), encoding="utf-8")
        run_cli(path, "--workspace", self.ws, "--update-seen", "--date", TODAY)
        (self.ws / "applications.md").write_text(
            "| D | C | R | F | L | S | N |\n|---|---|---|---|---|---|---|\n"
            "| 2026-11-25 | Acme Software | x | — | https://www.linkedin.com/jobs/view/9900000999/ | sent | |\n",
            encoding="utf-8")
        code, out, err = run_cli("--report", "--workspace", self.ws, "--date", TODAY)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual((data["open"], [e["n"] for e in data["applied"]]), ([], [1]))

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
        self.assertEqual(data["counts"], {"pass": 1, "repost": 0, "maybe": 0, "reject": 1, "to_apply": 0, "to_decide": 0,
                                          "pending_text": 0, "applied": 0})
        self.assertEqual(data["open"][0]["url"], "https://www.linkedin.com/jobs/view/9900000999/")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            jf.main(["--report", str(path), "--workspace", str(self.ws)])
        code, out, _ = run_cli("--report", "--workspace", self.ws / "nowhere")
        self.assertEqual(code, 2)


class Decisions(Workspace):
    """Stage 7: permanent numbers, the user's decisions, same_as, to_apply and --release-later."""

    record = Report.record
    analyse = Report.analyse

    def test_numbers_are_permanent_and_in_order_of_arrival(self):
        self.record(posting(job_id="5000002", url=None, company="Second"),
                    posting(job_id="5000001", url=None, company="First"), day="2026-11-20")
        results = jf.filter_postings([("m2", [posting(job_id="5000003", url=None, company="Third"),
                                              posting(job_id="5000002", url=None, company="Second")])],
                                     self.criteria, self.seen, self.applications, TODAY)
        numbers = {k: e["n"] for k, e in self.seen["postings"].items()}
        self.assertEqual(numbers, {"linkedin-5000002": 1, "linkedin-5000001": 2, "linkedin-5000003": 3})
        self.assertEqual([(r["decision"], r["n"]) for r in results], [("pass", 3), ("duplicate", 1)])
        self.assertEqual(jf.assign_numbers(self.seen), 0)
        self.assertEqual({e["key"]: e["n"] for e in jf.report(self.seen, TODAY)["open"]}, numbers)

    def test_old_seen_files_are_numbered_once_by_first_seen(self):
        self.seen = {"version": 1, "postings": {
            "linkedin-b": {"first_seen": "2026-11-20"}, "linkedin-a": {"first_seen": "2026-11-21"},
            "linkedin-c": {"first_seen": "2026-11-20"}, "linkedin-d": {"first_seen": "2026-11-01", "n": 7}}}
        self.assertEqual(jf.assign_numbers(self.seen), 3)
        self.assertEqual({k: e["n"] for k, e in self.seen["postings"].items()},
                         {"linkedin-b": 8, "linkedin-a": 10, "linkedin-c": 9, "linkedin-d": 7})

    def test_set_by_number(self):
        self.record(posting(job_id="5100001", url=None, company="One"), posting(job_id="5100002", url=None,
                                                                                company="Two"))
        key, entry, _ = jf.set_fields("#2", ["user_decision=discard", "user_reason=on-site"], self.seen, self.ws,
                                      TODAY)
        self.assertEqual((key, entry["user_decision"], entry["user_reason"]), ("linkedin-5100002", "discard",
                                                                                 "on-site"))
        for ref in ("#3", "#x", "2"):
            with self.subTest(ref=ref), self.assertRaises(jf.ConfigError):
                jf.set_fields(ref, ["user_decision=apply"], self.seen, self.ws, TODAY)
        self.assertIn("#1 linkedin-5100001", jf.explain("#1", self.criteria, self.seen))

    def test_a_new_decision_drops_the_old_reason(self):
        self.record(posting())
        jf.set_fields("#1", ["user_decision=later", "user_reason=after Mercanis"], self.seen, self.ws, TODAY)
        _, entry, _ = jf.set_fields("#1", ["user_decision=apply"], self.seen, self.ws, TODAY)
        self.assertIsNone(entry["user_reason"])

    def test_decision_is_shared_by_the_same_job(self):
        self.record(posting(job_id="5200001", url=None, company="Twice"),
                    posting(job_id="5200002", url=None, company="Twice"),
                    posting(job_id="5200003", url=None, company="Twice"))
        self.analyse("linkedin-5200001", stage="analysed", recommendation="apply")
        for alias in ("linkedin-5200002", "linkedin-5200003"):
            self.analyse(alias, stage="analysed", recommendation="apply", same_as="linkedin-5200001")
        _, _, others = jf.set_fields("linkedin-5200003", ["user_decision=apply", "user_reason=good fit"],
                                     self.seen, self.ws, TODAY)
        self.assertEqual(others, ["linkedin-5200001", "linkedin-5200002"])
        for k in ("linkedin-5200001", "linkedin-5200002"):
            e = self.seen["postings"][k]
            self.assertEqual((e["user_decision"], e["user_reason"], e["user_decision_date"]),
                             ("apply", "good fit", TODAY))
            self.assertEqual(e["recommendation"], "apply")  # only the shared fields are copied
        data = jf.report(self.seen, TODAY)
        self.assertEqual([e["key"] for e in data["to_apply"]], ["linkedin-5200001"])
        self.assertEqual(data["to_decide"], [])

    def test_to_apply_until_the_posting_is_in_an_application_folder(self):
        self.record(posting(job_id="5300001", url=None, company="Later Co"),
                    posting(job_id="5300002", url=None, company="Not Analysed"),
                    posting(job_id="5300003", url=None, company="Moved"), day="2026-11-24")
        jf.set_fields("#3", ["user_decision=apply"], self.seen, self.ws, "2026-11-24")
        jf.set_fields("#2", ["user_decision=apply"], self.seen, self.ws, TODAY)
        jf.set_fields("#1", ["user_decision=apply"], self.seen, self.ws, TODAY)
        self.assertEqual([e["n"] for e in jf.report(self.seen, TODAY)["to_apply"]], [3, 1, 2])
        folder = self.ws / "output" / "moved-backend-engineer"
        folder.mkdir(parents=True)
        (folder / "job-posting.md").write_text("x", encoding="utf-8")
        jf.set_fields("#3", ["posting_path=output/moved-backend-engineer/job-posting.md"], self.seen, self.ws, TODAY)
        data = jf.report(self.seen, TODAY)
        self.assertEqual([e["n"] for e in data["to_apply"]], [1, 2])
        self.assertEqual(data["counts"]["to_apply"], 2)
        self.assertEqual(data["open"] + data["to_decide"], [])

    def test_release_later(self):
        self.record(posting(job_id="5400001", url=None, company="Later"),
                    posting(job_id="5400002", url=None, company="Discarded"))
        self.analyse("linkedin-5400001", stage="analysed", recommendation="apply")
        jf.set_fields("#1", ["user_decision=later", "user_reason=busy"], self.seen, self.ws, TODAY)
        jf.set_fields("#2", ["user_decision=discard"], self.seen, self.ws, TODAY)
        self.assertEqual(jf.report(self.seen, TODAY)["to_decide"], [])
        self.assertEqual(jf.release_later(self.seen), ["linkedin-5400001"])
        entry = self.seen["postings"]["linkedin-5400001"]
        self.assertEqual((entry["user_decision"], entry["user_decision_date"], entry["user_reason"]),
                         (None, None, None))
        self.assertEqual([e["n"] for e in jf.report(self.seen, TODAY)["to_decide"]], [1])
        self.assertEqual(jf.release_later(self.seen), [])

    def test_cli(self):
        self.record(posting(job_id="6000001", url=None))
        del self.seen["postings"]["linkedin-6000001"]["n"]  # a seen.json written before the numbers
        (self.ws / "jobs" / "seen.json").write_text(json.dumps(self.seen), encoding="utf-8")
        code, out, err = run_cli("--set", "#1", "user_decision=later", "--workspace", self.ws, "--date", TODAY)
        self.assertEqual(code, 0, err)  # the seen.json from before the numbers got its numbers
        self.assertEqual((json.loads(out)["n"], json.loads(out)["also_set"]), (1, []))
        code, out, err = run_cli("--release-later", "--workspace", self.ws, "--date", TODAY)
        self.assertEqual((code, json.loads(out)), (0, {"released": ["linkedin-6000001"]}))
        seen = json.loads((self.ws / "jobs" / "seen.json").read_text(encoding="utf-8"))
        self.assertIsNone(seen["postings"]["linkedin-6000001"]["user_decision"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            jf.main(["--release-later", "--report", "--workspace", str(self.ws)])


class Retention(Workspace):
    """--prune: what is deleted and expired as time goes by, and seen.json never points to a missing file."""

    def setUp(self):
        super().setUp()
        for d in ("mail/inbox", "jobs/extracted", "jobs/postings"):
            (self.ws / d).mkdir(parents=True, exist_ok=True)

    def mail(self, day, mail_id, type_="alert", status="processed"):
        path = self.ws / "mail" / "inbox" / f"{day}-{mail_id}.md"
        path.write_text(f'---\nid: "{mail_id}"\nstatus: "{status}"\ntype: "{type_}"\n---\n\nbody\n', encoding="utf-8")
        return path

    def extracted(self, name):
        path = self.ws / "jobs" / "extracted" / name
        path.write_text("[]", encoding="utf-8")
        return path

    def record(self, mail_id, day, *postings):
        jf.filter_postings([(mail_id, list(postings))], self.criteria, self.seen, self.applications, day)

    def analyse(self, key, day, saved=True, **fields):
        if saved:
            (self.ws / "jobs" / "postings" / f"{key}.md").write_text("card", encoding="utf-8")
            fields.setdefault("posting_path", f"jobs/postings/{key}.md")
        jf.set_fields(key, [f"{k}={v}" for k, v in fields.items()], self.seen, self.ws, day)

    def entry(self, key):
        return self.seen["postings"][key]

    def test_alerts_and_saved_postings(self):
        old, busy, recent = (self.mail("2026-11-01", "aaaaaaaaaaaa"), self.mail("2026-11-01", "bbbbbbbbbbbb"),
                             self.mail("2026-11-15", "cccccccccccc"))
        message = self.mail("2026-11-01", "dddddddddddd", type_="message", status="waiting")
        self.record("aaaaaaaaaaaa", "2026-11-01",
                    posting(job_id="7000001", url=None, company="Rejected", title="Junior Backend Engineer"),
                    posting(job_id="7000002", url=None, company="Recommended Discard"),
                    posting(job_id="7000003", url=None, company="User Discard"),
                    posting(job_id="7000004", url=None, company="Discarded Today"))
        self.record("bbbbbbbbbbbb", "2026-11-01", posting(job_id="7000005", url=None, company="In Queue"))
        self.record("cccccccccccc", "2026-11-15", posting(job_id="7000006", url=None, company="Recent"))
        self.analyse("linkedin-7000002", "2026-11-02", stage="analysed", recommendation="discard")
        self.analyse("linkedin-7000003", "2026-11-02", stage="analysed", recommendation="apply")
        jf.set_fields("linkedin-7000003", ["user_decision=discard"], self.seen, self.ws, "2026-11-02")
        self.analyse("linkedin-7000004", "2026-11-02", stage="analysed", recommendation="apply")
        jf.set_fields("linkedin-7000004", ["user_decision=discard"], self.seen, self.ws, "2026-11-20")
        files = [self.extracted(n) for n in ("aaaaaaaaaaaa.json", "bbbbbbbbbbbb.json", "manual-2026-11-01-1.json",
                                             "message-eeeeeeeeeeee.json", "message-dddddddddddd.json",
                                             "recheck-linkedin-7000002.json")]

        before = json.dumps(self.seen, sort_keys=True)
        dry = jf.prune(self.seen, self.ws, "2026-11-20", dry_run=True)
        self.assertEqual(json.dumps(self.seen, sort_keys=True), before)
        self.assertTrue(all(p.exists() for p in files + [old]))

        done = jf.prune(self.seen, self.ws, "2026-11-20")
        self.assertEqual({k: v for k, v in done.items() if k != "dry_run"},
                         {k: v for k, v in dry.items() if k != "dry_run"})
        self.assertEqual([m["mail"] for m in done["mails_deleted"]], ["aaaaaaaaaaaa"])
        self.assertEqual((old.exists(), busy.exists(), recent.exists(), message.exists()), (False, True, True, True))
        self.assertEqual([(a["mail"], [b["company"] for b in a["blocked_by"]]) for a in done["alerts_waiting"]],
                         [("bbbbbbbbbbbb", ["In Queue"])])
        self.assertEqual(done["extracted_deleted"], ["manual-2026-11-01-1.json", "message-eeeeeeeeeeee.json",
                                                     "recheck-linkedin-7000002.json"])
        self.assertEqual([p.exists() for p in files], [False, True, False, False, True, False])
        self.assertEqual([e["company"] for e in done["expired"]], ["Recommended Discard"])
        self.assertEqual(sorted(e["company"] for e in done["postings_deleted"]), ["Recommended Discard", "User Discard"])
        for key in ("linkedin-7000002", "linkedin-7000003"):
            self.assertIsNone(self.entry(key)["posting_path"])
            self.assertFalse((self.ws / "jobs" / "postings" / f"{key}.md").exists())
        self.assertEqual(self.entry("linkedin-7000004")["posting_path"], "jobs/postings/linkedin-7000004.md")
        self.assertEqual(jf.report(self.seen, "2026-11-20")["to_decide"], [])
        # the second time there is nothing left to do
        self.assertEqual(sum(v for k, v in jf.prune(self.seen, self.ws, "2026-11-20")["counts"].items()
                             if k != "alerts_waiting"), 0)

    def test_postings_to_apply_expire_when_closed_or_unchecked(self):
        self.record("m1", "2026-11-01", *[posting(job_id=f"710000{i}", url=None, company=c) for i, c in
                                          enumerate(["Closes", "Alias", "Stays Open", "Unsupported", "No Text",
                                                     "To Apply"])])
        for key in ("linkedin-7100000", "linkedin-7100002", "linkedin-7100003"):
            self.analyse(key, "2026-11-01", stage="analysed", recommendation="apply")
        self.analyse("linkedin-7100001", "2026-11-01", saved=False, stage="analysed", recommendation="apply",
                     same_as="linkedin-7100000", posting_path="jobs/postings/linkedin-7100000.md")
        self.analyse("linkedin-7100004", "2026-11-01", saved=False, stage="pending_text")
        self.analyse("linkedin-7100005", "2026-11-01", stage="analysed", recommendation="apply_with_reservations")
        jf.set_fields("linkedin-7100005", ["user_decision=apply"], self.seen, self.ws, "2026-11-01")

        done = jf.prune(self.seen, self.ws, "2026-11-10")
        self.assertEqual(done["to_check"] + done["expired"], [])
        done = jf.prune(self.seen, self.ws, "2026-11-15")  # 14 days
        self.assertEqual([e["company"] for e in done["to_check"]], ["Closes", "Stays Open", "Unsupported"])
        jf.set_fields("linkedin-7100000", ["closed=true"], self.seen, self.ws, "2026-11-15")
        jf.set_fields("linkedin-7100002", ["closed=false"], self.seen, self.ws, "2026-11-15")
        done = jf.prune(self.seen, self.ws, "2026-11-15")
        self.assertEqual([(e["company"], e["why"]) for e in done["expired"]],
                         [("Closes", "the posting is closed"), ("Alias", "the posting is closed")])
        self.assertEqual([e["company"] for e in done["to_check"]], ["Unsupported"])  # the other two are checked today
        self.assertIsNone(self.entry("linkedin-7100001")["posting_path"])
        self.assertFalse((self.ws / "jobs" / "postings" / "linkedin-7100000.md").exists())

        done = jf.prune(self.seen, self.ws, "2026-11-25")  # 24 days: expiring soon (the open answer is 10 days old)
        self.assertEqual([(e["company"], e["expires"]) for e in done["expiring_soon"]],
                         [("Stays Open", "2026-12-01"), ("Unsupported", "2026-12-01"), ("No Text", "2026-12-01")])
        data = jf.report(self.seen, "2026-11-25")  # the inbox shows the same dates
        self.assertEqual({e["company"]: e["expires"] for e in data["to_decide"] + data["pending_text"]},
                         {"Stays Open": "2026-12-01", "Unsupported": "2026-12-01", "No Text": "2026-12-01"})
        jf.set_fields("linkedin-7100002", ["closed=false"], self.seen, self.ws, "2026-11-25")
        done = jf.prune(self.seen, self.ws, "2026-12-01")  # 30 days
        self.assertEqual([(e["company"], e["why"]) for e in done["expired"]],
                         [("Unsupported", "not decided in 30 days and could not be checked"),
                          ("No Text", "no text after 30 days")])
        self.assertEqual([e["company"] for e in done["to_check"]], ["Stays Open"])
        self.assertEqual(self.entry("linkedin-7100002")["stage"], "analysed")
        self.assertEqual(self.entry("linkedin-7100005")["posting_path"], "jobs/postings/linkedin-7100005.md")
        # an open posting whose checks keep failing falls back to the age rule a week after the last answer
        self.assertEqual(jf.prune(self.seen, self.ws, "2026-12-02")["expired"], [])
        done = jf.prune(self.seen, self.ws, "2026-12-03")
        self.assertEqual([e["company"] for e in done["expired"]], ["Stays Open"])

    def test_later_postings_are_undecided_after_release(self):
        self.record("m1", "2026-11-01", posting(job_id="7200001", url=None, company="Later"))
        self.analyse("linkedin-7200001", "2026-11-01", stage="analysed", recommendation="apply")
        jf.set_fields("#1", ["user_decision=later"], self.seen, self.ws, "2026-11-01")
        self.assertEqual(jf.prune(self.seen, self.ws, "2026-12-15")["expired"], [])
        jf.release_later(self.seen)
        self.assertEqual([e["company"] for e in jf.prune(self.seen, self.ws, "2026-12-15")["expired"]], ["Later"])

    def test_missing_and_unreferenced_files(self):
        self.record("m1", "2026-11-01", posting(job_id="7300001", url=None, company="Lost Card"),
                    posting(job_id="7300002", url=None, company="Applied"))
        self.analyse("linkedin-7300001", "2026-11-01", stage="analysed", recommendation="apply")
        folder = self.ws / "output" / "applied-backend"
        folder.mkdir(parents=True)
        (folder / "job-posting.md").write_text("x", encoding="utf-8")
        jf.set_fields("#2", ["user_decision=apply", "posting_path=output/applied-backend/job-posting.md"],
                      self.seen, self.ws, "2026-11-01")
        (self.ws / "jobs" / "postings" / "linkedin-7300001.md").unlink()
        (folder / "job-posting.md").unlink()
        (self.ws / "jobs" / "postings" / "stray.md").write_text("x", encoding="utf-8")
        done = jf.prune(self.seen, self.ws, "2026-11-02")
        self.assertEqual([e["company"] for e in done["missing_files"]], ["Lost Card", "Applied"])
        self.assertEqual([e["company"] for e in done["requeued"]], ["Lost Card"])
        self.assertEqual((self.entry("linkedin-7300001")["stage"], self.entry("linkedin-7300001")["posting_path"]),
                         ("filtered", None))
        self.assertEqual([e["company"] for e in jf.report(self.seen, "2026-11-02")["open"]], ["Lost Card"])
        self.assertEqual(self.entry("linkedin-7300002")["posting_path"], "output/applied-backend/job-posting.md")
        self.assertEqual(done["unreferenced_postings"], ["jobs/postings/stray.md"])
        self.assertTrue((self.ws / "jobs" / "postings" / "stray.md").exists())

    def test_text_of_a_posting_that_does_not_point_to_it(self):
        self.record("m1", "2026-11-01", *[posting(job_id=f"750000{i}", url=None, company=c) for i, c in
                                          enumerate(["Root", "Alias", "Discarded Unanalysed", "Being Analysed"])])
        self.analyse("linkedin-7500000", "2026-11-01", stage="analysed", recommendation="apply")
        for key in ("linkedin-7500001", "linkedin-7500002", "linkedin-7500003"):
            (self.ws / "jobs" / "postings" / f"{key}.md").write_text("text", encoding="utf-8")
        self.analyse("linkedin-7500001", "2026-11-01", saved=False, stage="analysed", recommendation="apply",
                     same_as="linkedin-7500000", posting_path="jobs/postings/linkedin-7500000.md")
        jf.set_fields("#3", ["user_decision=discard"], self.seen, self.ws, "2026-11-01")
        done = jf.prune(self.seen, self.ws, "2026-11-05")
        self.assertEqual([e["company"] for e in done["postings_deleted"]], ["Alias"])
        done = jf.prune(self.seen, self.ws, "2026-11-11")
        self.assertEqual([e["company"] for e in done["postings_deleted"]], ["Discarded Unanalysed"])
        self.assertEqual(sorted(p.name for p in (self.ws / "jobs" / "postings").iterdir()),
                         ["linkedin-7500000.md", "linkedin-7500003.md"])
        self.assertEqual(done["unreferenced_postings"], [])

    def test_cli(self):
        self.record("aaaaaaaaaaaa", "2026-11-01", posting(job_id="7400001", url=None, title="Junior Backend Engineer"))
        (self.ws / "jobs" / "seen.json").write_text(json.dumps(self.seen), encoding="utf-8")
        alert = self.mail("2026-11-01", "aaaaaaaaaaaa")
        code, out, err = run_cli("--prune", "--dry-run", "--workspace", self.ws, "--date", "2026-11-20")
        self.assertEqual((code, json.loads(out)["counts"]["mails_deleted"], alert.exists()), (0, 1, True), err)
        code, out, err = run_cli("--prune", "--workspace", self.ws, "--date", "2026-11-20")
        self.assertEqual((code, alert.exists()), (0, False), err)
        code, out, err = run_cli("--set", "#1", "closed=maybe", "--workspace", self.ws)
        self.assertEqual(code, 2)
        for argv in (["--dry-run", "--report"], ["--prune", "--calibration"]):
            with self.subTest(argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                jf.main(argv + ["--workspace", str(self.ws)])


class Calibration(Workspace):
    """--calibration: the data behind proposals to change criteria.md."""

    def test_decisions_other_family_and_rejections(self):
        record = Report.record
        record(self, posting(job_id="8000001", url=None, company="Presales One", title="Presales Engineer"),
               posting(job_id="8000002", url=None, company="Applied Anyway"),
               posting(job_id="8000003", url=None, company="Plain Discard"),
               posting(job_id="8000004", url=None, company="Odd", title="Solutions Architect", role_family="other"),
               posting(job_id="8000005", url=None, company="Junior", title="Junior Backend Engineer"),
               posting(job_id="8000006", url=None, company="Presales One", title="Presales Engineer"),
               posting(job_id="8000007", url=None, company="Old", title="Junior Data Engineer"), day=TODAY)
        self.seen["postings"]["linkedin-8000007"]["filter"]["date"] = "2026-01-01"
        jf.set_fields("#1", ["stage=analysed", "recommendation=apply", "user_decision=discard",
                             "user_reason=presales"], self.seen, self.ws, TODAY)
        jf.set_fields("#2", ["stage=analysed", "recommendation=discard", "user_decision=apply",
                             "user_reason=AWS is fine"], self.seen, self.ws, TODAY)
        jf.set_fields("#3", ["stage=analysed", "recommendation=discard", "user_decision=discard"], self.seen,
                      self.ws, TODAY)
        jf.set_fields("#6", ["same_as=linkedin-8000001"], self.seen, self.ws, TODAY)
        data = jf.calibration(self.seen, TODAY)
        self.assertEqual([(e["company"], e["user_decision"], e["user_reason"]) for e in data["against_recommendation"]],
                         [("Presales One", "discard", "presales"), ("Applied Anyway", "apply", "AWS is fine")])
        self.assertEqual([e["company"] for e in data["user_discards"]], ["Presales One", "Plain Discard"])
        self.assertEqual([(e["company"], e["decision"]) for e in data["other_family"]], [("Odd", "maybe")])
        self.assertEqual(data["rejections_by_rule"],
                         {"title_exclude": {"count": 1, "examples": [{"n": 5, "title": "Junior Backend Engineer",
                                                                      "company": "Junior", "reason": data[
                                                                          "rejections_by_rule"]["title_exclude"][
                                                                          "examples"][0]["reason"]}]}})
        self.assertEqual(jf.calibration(self.seen, TODAY, days=400)["rejections_by_rule"]["title_exclude"]["count"], 2)
        code, out, err = run_cli("--calibration", "--workspace", self.ws, "--date", TODAY)
        self.assertEqual((code, json.loads(out)["counts"]["user_discards"]), (0, 0), err)  # no seen.json on disk


if __name__ == "__main__":
    unittest.main()
