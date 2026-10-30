import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from engine import ROOT, build, funnel, generation_cost, report, validate_draft


class RevenueTests(unittest.TestCase):
    def test_unknown_is_not_zero(self):
        self.assertIsNone(report({})["actual_net_profit_jpy"])
        self.assertTrue(all(v is None for v in funnel({}).values()))

    def actual(self):
        data = json.loads((ROOT / "ledger.blank.json").read_text())
        for key in data:
            if key.endswith("_jpy") or key in ("labor_minutes", "labor_rate_jpy_hour"):
                data[key] = 0
        data.update(evidence_type="actual", reconciled=True, payment_evidence="private:payment",
                    expense_evidence="private:cost", tax_evidence="private:tax",
                    gross_sales_jpy=9800, refunds_jpy=980, fees_jpy=353,
                    production_jpy=1000, labor_minutes=60, labor_rate_jpy_hour=1000)
        return data

    def test_accounting_refunds_fees_and_labor(self):
        got = report(self.actual())
        self.assertEqual(got["actual_net_profit_jpy"], 7467)
        self.assertEqual(got["labor_adjusted_profit_jpy"], 6467)

    def test_mock_and_missing_evidence_cannot_be_actual(self):
        for key, value in (("evidence_type", "synthetic"), ("reconciled", False),
                           ("taxes_jpy", None), ("payment_evidence", "")):
            data = self.actual()
            data[key] = value
            self.assertEqual(report(data)["status"], "UNKNOWN")

    def test_invalid_amounts(self):
        for value in (-1, True, 1.1, "100", float("nan")):
            data = self.actual()
            data["fees_jpy"] = value
            with self.assertRaises(ValueError):
                report(data)

    def test_previous_period_refunds_allow_negative_profit(self):
        data = self.actual()
        data["gross_sales_jpy"] = 0
        self.assertLess(report(data)["actual_net_profit_jpy"], 0)

    def test_ratios_zero_missing_and_valid(self):
        self.assertIsNone(funnel({"views": 0, "profile_visits": 0})["profile_visits_per_views"])
        self.assertEqual(funnel({"views": 100, "profile_visits": 10})["profile_visits_per_views"], .1)

    def test_cost_retries_and_invalid_values(self):
        self.assertEqual(generation_cost(5, 2), {"credits": 50, "api_usd": .5})
        self.assertEqual(generation_cost(10, 30)["credits"], 1500)
        for seconds, attempts in ((-5, 1), (30, 1), (5, 0), (5, True)):
            with self.assertRaises(ValueError):
                generation_cost(seconds, attempts)

    def test_draft_gates_fail_closed(self):
        base = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        validate_draft(base)
        for key in ("publish_allowed", "billing_allowed", "autopost_allowed", "merge_allowed", "real_submit_allowed"):
            for value in (True, "false", None):
                with self.assertRaises(ValueError):
                    validate_draft(dict(base, **{key: value}))
        with self.assertRaises(ValueError):
            validate_draft(dict(base, approved_spend_jpy=100))

    def test_package_no_checkout_no_tracking_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review"
            build(path, dt.date(2026, 11, 1))
            calendar = json.loads((path / "calendar.json").read_text(encoding="utf-8"))
            self.assertEqual(len({x["content_id"] for x in calendar}), 30)
            self.assertEqual(calendar[-1]["date_jst"], "2026-11-30")
            page = (path / "index.html").read_text(encoding="utf-8")
            for forbidden in ("<script", "<form", "https://", "fetch("):
                self.assertNotIn(forbidden, page)
            self.assertEqual(page.count("<button disabled>"), 3)
            self.assertTrue((path / "free-sheet.md").exists())
            self.assertEqual(len(list((path / "images").glob("*.jpg"))), 4)
            with self.assertRaises(FileExistsError):
                build(path, dt.date(2026, 11, 1))


if __name__ == "__main__":
    unittest.main()
