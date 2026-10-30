import csv, gzip, importlib.util, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import run_analysis as a


def event(p="p", act="a", date="01/01/2021", code="FOO", status=None, n=1):
    r = dict(
        PGM_SYS_ID_KEY=p,
        ACTIVITY_ID_KEY=act,
        STATE_EPA_FLAG="S",
        COMP_MONITOR_TYPE_CODE=code,
        ACTUAL_END_DATE=date,
        source_row=n,
    )
    if status is not None:
        r["AIR_STACK_TEST_STATUS_CODE"] = status
    return r


def facility(k, state="CA", status="OPR", n=1):
    return dict(
        PGM_SYS_ID_KEY=k,
        STATE=state,
        EPA_REGION="09",
        AIR_POLLUTANT_CLASS_CODE="MAJ",
        AIR_OPERATING_STATUS_CODE=status,
        source_row=n,
    )


class CoverageTests(unittest.TestCase):
    def test_dash_date(self):
        self.assertEqual(a.parse_date("12-31-2025").isoformat(), "2025-12-31")

    def test_slash_iso(self):
        self.assertEqual(a.parse_date("01/01/2021"), a.parse_date("2021-01-01"))

    def test_bad_date(self):
        self.assertIsNone(a.parse_date("02/29/2021"))

    def test_unknown_date(self):
        self.assertIsNone(a.parse_date(""))

    def test_midnight_only(self):
        self.assertIsNotNone(a.parse_date("2021-01-01T00:00:00.000"))
        self.assertIsNone(a.parse_date("2021-01-01 01:00:00"))

    def test_exact_duplicate(self):
        rows, c = a.unique_rows([facility("p"), facility("p", n=2)], "facilities")
        self.assertEqual(len(rows), 1)
        self.assertEqual(c["exact_duplicate_excess_nonconflicting"], 1)

    def test_facility_conflict(self):
        rows, c = a.unique_rows(
            [facility("p"), facility("p", state="NY", n=2)], "facilities"
        )
        self.assertEqual(rows, [])
        self.assertEqual(c["conflicting_source_rows"], 2)

    def test_event_conflict(self):
        self.assertEqual(
            a.unique_rows([event(), event(date="01/02/2021", n=2)], "evaluations")[0],
            [],
        )

    def test_event_identity(self):
        self.assertEqual(
            len(a.unique_rows([event(), event(act="b", n=2)], "evaluations")[0]), 2
        )

    def test_missing_identity(self):
        self.assertEqual(
            a.unique_rows([event(act="")], "evaluations")[1]["missing_identity_rows"], 1
        )

    def test_absent_is_unknown(self):
        r = a.observations([0] * 12)
        self.assertEqual(r["stack_none"], 1)
        self.assertEqual(r["stack_pass_only"], 0)
        self.assertEqual(r["no_evaluation"], 1)

    def test_offsite_is_not_visit(self):
        r = a.observations([0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(r["off_only"], 1)
        self.assertEqual(r["any_on"], 0)

    def test_unknown_evaluation(self):
        self.assertEqual(
            a.observations([0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0])["unknown_eval_only"], 1
        )

    def test_mixed_results(self):
        r = a.observations([0, 0, 0, 0, 0, 2, 1, 0, 0, 0, 0, 0])
        self.assertEqual(r["stack_fail_any"], 1)
        self.assertEqual(r["stack_mixed_pass_fail"], 1)
        self.assertEqual(r["stack_pass_only"], 0)

    def test_pending_is_not_pass_only(self):
        self.assertEqual(
            a.observations([0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0])[
                "stack_pass_unresolved"
            ],
            1,
        )

    def test_na_is_not_result(self):
        self.assertEqual(
            a.observations([0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0])[
                "stack_observed_result"
            ],
            0,
        )

    def test_calendar_and_full_denominator(self):
        fixtures = {
            "facilities": [
                facility("p"),
                facility("q", state="NY", n=2),
                facility("closed", state="TX", status="CLS", n=3),
            ],
            "evaluations": [
                event(date="01-01-2021"),
                event(p="q", act="b", code="FFO"),
                event(p="q", act="c", date="12-31-2020", code="FOO"),
            ],
            "stack_tests": [
                event(act="s1", code="STA", status="PSS"),
                event(act="s2", date="12/31/2025", code="STA", status="FAI"),
                event(p="q", act="s3", date="06/01/2022", code="STA", status="PSS"),
                event(p="q", act="s4", date="06/02/2022", code="STA", status="PEN"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp, patch.object(
            a, "records", side_effect=lambda t: iter(fixtures[t])
        ), patch.object(sys, "argv", ["run_analysis", "--output-dir", temp]), patch(
            "builtins.print"
        ):
            a.main()
            with open(Path(temp) / "group_counts.csv", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            total = next(
                r for r in rows if r["window"] == "2021-2025" and r["group"] == "all"
            )
            for field, value in [
                ("facilities", "2"),
                ("any_on", "1"),
                ("off_only", "1"),
                ("stack_fail_any", "1"),
                ("stack_pass_unresolved", "1"),
                ("stack_mixed_pass_fail", "1"),
            ]:
                self.assertEqual(total[field], value)
            year = next(
                r for r in rows if r["window"] == "2024" and r["group"] == "all"
            )
            self.assertEqual(year["no_evaluation"], "2")
            self.assertEqual(year["stack_none"], "2")


if __name__ == "__main__":
    unittest.main()
