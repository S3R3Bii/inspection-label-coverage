"""Independent SQLite reconstruction from source tokens, without analysis imports."""

from pathlib import Path
from datetime import date
import csv, gzip, json, re, sqlite3, tempfile

ROOT = Path(__file__).resolve().parents[1]
STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
WINDOWS = ["2021", "2022", "2023", "2024", "2025", "2021-2025"]
COUNTS = [
    "full_on",
    "partial_on",
    "full_off",
    "partial_off",
    "unknown_eval",
    "pass",
    "fail",
    "pending",
    "incomplete",
    "not_applicable",
    "blank",
    "other",
]
MEASURES = [
    "facilities",
    "full_on",
    "any_on",
    "off_only",
    "no_evaluation",
    "unknown_eval_only",
    "stack_none",
    "stack_fail_any",
    "stack_pass_only",
    "stack_pass_unresolved",
    "stack_unresolved_only",
    "stack_observed_result",
    "stack_mixed_pass_fail",
]


def independent_year(token):
    text = re.sub(r"[ T]00:00:00(?:\.000)?$", "", token.strip())
    m = re.fullmatch(r"(\d{1,2})([-/])(\d{1,2})\2(\d{4})", text)
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    try:
        if m:
            return date(int(m[4]), int(m[1]), int(m[3])).year
        if iso:
            return date(int(iso[1]), int(iso[2]), int(iso[3])).year
    except ValueError:
        pass
    return None


def main():
    checks = 0

    def check(ok, message):
        nonlocal checks
        assert ok, message
        checks += 1

    manifest = json.loads(
        (ROOT / "data/source_manifest.json").read_text(encoding="utf-8")
    )
    audit = json.loads((ROOT / "results/source_audit.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temp:
        db = sqlite3.connect(str(Path(temp) / "independent.sqlite"))
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA temp_store=FILE")
        db.create_function("YEAR_TOKEN", 1, independent_year, deterministic=True)
        table_info = {
            "facilities": (
                "f",
                ["k", "state", "region", "cls", "status"],
                [
                    "PGM_SYS_ID_KEY",
                    "STATE",
                    "EPA_REGION",
                    "AIR_POLLUTANT_CLASS_CODE",
                    "AIR_OPERATING_STATUS_CODE",
                ],
            ),
            "evaluations": (
                "v",
                ["k", "a", "flag", "code", "dt"],
                [
                    "PGM_SYS_ID_KEY",
                    "ACTIVITY_ID_KEY",
                    "STATE_EPA_FLAG",
                    "COMP_MONITOR_TYPE_CODE",
                    "ACTUAL_END_DATE",
                ],
            ),
            "stack_tests": (
                "s",
                ["k", "a", "flag", "code", "dt", "st"],
                [
                    "PGM_SYS_ID_KEY",
                    "ACTIVITY_ID_KEY",
                    "STATE_EPA_FLAG",
                    "COMP_MONITOR_TYPE_CODE",
                    "ACTUAL_END_DATE",
                    "AIR_STACK_TEST_STATUS_CODE",
                ],
            ),
        }
        for table, (short, cols, source) in table_info.items():
            db.execute(
                "CREATE TABLE "
                + short
                + "(n INTEGER,"
                + ",".join(c + " TEXT" for c in cols)
                + ")"
            )
            for shard in manifest["shards"]:
                if shard["table"] != table:
                    continue
                rows = json.loads(gzip.decompress((ROOT / shard["file"]).read_bytes()))
                db.executemany(
                    "INSERT INTO "
                    + short
                    + " VALUES("
                    + ",".join("?" for _ in range(len(cols) + 1))
                    + ")",
                    ((r["source_row"], *(r[c] for c in source)) for r in rows),
                )
            keys = ["k"] if table == "facilities" else ["k", "a"]
            keytext = ",".join(keys)
            fields = ",".join(cols)
            eligible = " AND ".join(c + "<>''" for c in keys)
            db.execute(
                "CREATE INDEX " + short + "_id ON " + short + "(" + keytext + ",n)"
            )
            db.execute(
                "CREATE TABLE "
                + short
                + "_d AS SELECT DISTINCT "
                + fields
                + " FROM "
                + short
                + " WHERE "
                + eligible
            )
            db.execute(
                "CREATE INDEX " + short + "_d_id ON " + short + "_d(" + keytext + ")"
            )
            db.execute(
                "CREATE TABLE "
                + short
                + "_conflict AS SELECT "
                + keytext
                + " FROM "
                + short
                + "_d GROUP BY "
                + keytext
                + " HAVING COUNT(*)>1"
            )
            db.execute(
                "CREATE TABLE "
                + short
                + "_clean AS SELECT d.* FROM "
                + short
                + "_d d JOIN (SELECT "
                + keytext
                + " FROM "
                + short
                + "_d GROUP BY "
                + keytext
                + " HAVING COUNT(*)=1) u USING("
                + keytext
                + ")"
            )
            db.execute(
                "CREATE INDEX "
                + short
                + "_c_id ON "
                + short
                + "_clean("
                + keytext
                + ")"
            )
            get = lambda sql: db.execute(sql).fetchone()[0]
            expected = dict(
                source_rows=get("SELECT COUNT(*) FROM " + short),
                missing_identity_rows=get(
                    "SELECT COUNT(*) FROM " + short + " WHERE NOT(" + eligible + ")"
                ),
                conflicting_identities=get(
                    "SELECT COUNT(*) FROM " + short + "_conflict"
                ),
                conflicting_source_rows=get(
                    "SELECT COUNT(*) FROM "
                    + short
                    + " JOIN "
                    + short
                    + "_conflict USING("
                    + keytext
                    + ")"
                ),
                unique_nonconflicting_rows=get(
                    "SELECT COUNT(*) FROM " + short + "_clean"
                ),
            )
            expected["exact_duplicate_excess_nonconflicting"] = (
                get(
                    "SELECT COUNT(*) FROM "
                    + short
                    + " JOIN "
                    + short
                    + "_clean USING("
                    + fields
                    + ")"
                )
                - expected["unique_nonconflicting_rows"]
            )
            db.execute(
                "CREATE TABLE "
                + short
                + "_first AS SELECT r.* FROM "
                + short
                + " r JOIN (SELECT "
                + keytext
                + ",MIN(n) AS n FROM "
                + short
                + " WHERE "
                + eligible
                + " GROUP BY "
                + keytext
                + ") first USING("
                + keytext
                + ",n)"
            )
            expected["repeated_first_selected_row"] = get(
                "SELECT COUNT(*) FROM "
                + short
                + " JOIN "
                + short
                + "_first USING("
                + fields
                + ")"
            ) - get("SELECT COUNT(*) FROM " + short + "_first")
            actual = (
                audit["facilities"]
                if table == "facilities"
                else audit["events"][table]["identity"]
            )
            for key, value in expected.items():
                check(actual.get(key, 0) == value, (table, key, actual.get(key), value))
        db.execute("CREATE TABLE states(code TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO states VALUES(?)", [(s,) for s in STATES])
        db.execute(
            "CREATE TABLE cohort AS SELECT k,UPPER(TRIM(state)) state,COALESCE(NULLIF(UPPER(TRIM(cls)),''),'<MISSING>') cls FROM f_clean JOIN states ON states.code=UPPER(TRIM(f_clean.state)) WHERE UPPER(TRIM(status))='OPR'"
        )
        db.execute("CREATE UNIQUE INDEX cohort_k ON cohort(k)")
        n = db.execute("SELECT COUNT(*) FROM cohort").fetchone()[0]
        check(n == audit["cohort_facilities"], "Cohort")
        for key, sql in [
            (
                "not_current_OPR",
                "SELECT COUNT(*) FROM f_clean WHERE UPPER(TRIM(status))<>'OPR'",
            ),
            (
                "outside_50_states_DC",
                "SELECT COUNT(*) FROM f_clean WHERE UPPER(TRIM(state)) NOT IN (SELECT code FROM states)",
            ),
        ]:
            check(
                db.execute(sql).fetchone()[0]
                == audit["facility_exclusion_reasons_overlap"].get(key, 0),
                key,
            )
        for table, short in [("evaluations", "v"), ("stack_tests", "s")]:
            st = "''" if table == "evaluations" else "UPPER(TRIM(st))"
            db.execute(
                "CREATE TABLE "
                + short
                + "_normal AS SELECT k,a,UPPER(TRIM(code)) code,dt,YEAR_TOKEN(dt) y,"
                + st
                + " st FROM "
                + short
                + "_clean"
            )
            actual = audit["events"][table]
            queries = {
                "no_nonconflicting_source_facility": "k NOT IN(SELECT k FROM f_clean)",
                "outside_current_cohort": "k NOT IN(SELECT k FROM cohort)",
                "invalid_or_missing_date": "y IS NULL",
                "outside_2021_2025": "y IS NOT NULL AND y NOT BETWEEN 2021 AND 2025",
                "included_window_events": "k IN(SELECT k FROM cohort) AND y BETWEEN 2021 AND 2025",
            }
            for key, where in queries.items():
                check(
                    db.execute(
                        "SELECT COUNT(*) FROM " + short + "_normal WHERE " + where
                    ).fetchone()[0]
                    == actual["quality_counts_overlap"].get(key, 0),
                    (table, key),
                )
            token = "code" if table == "evaluations" else "st"
            tokens = dict(
                db.execute(
                    "SELECT CASE WHEN "
                    + token
                    + "='' THEN '<BLANK>' ELSE "
                    + token
                    + " END,COUNT(*) FROM "
                    + short
                    + "_normal GROUP BY 1"
                )
            )
            check(tokens == actual["all_unique_code_counts"], (table, "code counts"))
            formats = dict(
                db.execute(
                    "SELECT CASE WHEN INSTR(dt,'/')>0 THEN 'MM/DD/YYYY' WHEN SUBSTR(dt,5,1)='-' THEN 'ISO' ELSE 'MM-DD-YYYY' END,COUNT(*) FROM "
                    + short
                    + "_normal WHERE y IS NOT NULL GROUP BY 1"
                )
            )
            check(
                formats == actual["valid_date_format_counts"], (table, "date formats")
            )
        eval_case = "CASE WHEN code='FOO' THEN 0 WHEN code IN('PCE','POC','POI','POM','POR') THEN 1 WHEN code='FFO' THEN 2 WHEN code='PFF' THEN 3 ELSE 4 END"
        stack_case = "CASE st WHEN 'PSS' THEN 5 WHEN 'FAI' THEN 6 WHEN 'PEN' THEN 7 WHEN 'INC' THEN 8 WHEN 'NA' THEN 9 WHEN '' THEN 10 ELSE 11 END"
        db.execute(
            "CREATE TABLE included AS SELECT k,y,"
            + eval_case
            + " idx FROM v_normal JOIN cohort USING(k) WHERE y BETWEEN 2021 AND 2025 UNION ALL SELECT k,y,"
            + stack_case
            + " idx FROM s_normal JOIN cohort USING(k) WHERE y BETWEEN 2021 AND 2025"
        )
        sums = ",".join(
            "SUM(idx=" + str(i) + ') AS "' + c + '"' for i, c in enumerate(COUNTS)
        )
        db.execute(
            "CREATE TABLE agg AS SELECT k,CAST(y AS TEXT) w,"
            + sums
            + " FROM included GROUP BY k,y UNION ALL SELECT k,'2021-2025' w,"
            + sums
            + " FROM included GROUP BY k"
        )
        db.execute("CREATE UNIQUE INDEX agg_k ON agg(k,w)")
        db.execute("CREATE TABLE windows(w TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO windows VALUES(?)", [(w,) for w in WINDOWS])
        values = ",".join('COALESCE(agg."' + c + '",0) AS "' + c + '"' for c in COUNTS)
        db.execute(
            "CREATE TABLE expected AS SELECT windows.w,cohort.k,cohort.state,cohort.cls,"
            + values
            + " FROM cohort CROSS JOIN windows LEFT JOIN agg ON agg.k=cohort.k AND agg.w=windows.w"
        )
        db.execute(
            "CREATE TABLE actual(w TEXT,k TEXT,state TEXT,cls TEXT,"
            + ",".join('"' + c + '" INTEGER' for c in COUNTS)
            + ")"
        )
        with gzip.open(
            ROOT / "results/facility_windows.csv.gz", "rt", encoding="utf-8", newline=""
        ) as stream:
            reader = csv.reader(stream)
            header = next(reader)
            check(
                header == ["window", "facility_key", "state", "class", *COUNTS],
                "Observation columns",
            )
            batch = []
            for row in reader:
                batch.append((*row[:4], *(int(x) for x in row[4:])))
                if len(batch) == 20000:
                    db.executemany(
                        "INSERT INTO actual VALUES("
                        + ",".join("?" for _ in header)
                        + ")",
                        batch,
                    )
                    batch = []
            if batch:
                db.executemany(
                    "INSERT INTO actual VALUES(" + ",".join("?" for _ in header) + ")",
                    batch,
                )
        row_count = db.execute("SELECT COUNT(*) FROM actual").fetchone()[0]
        check(row_count == n * 6, "Every facility in every window")
        for left, right in [("actual", "expected"), ("expected", "actual")]:
            mismatch = db.execute(
                "SELECT * FROM " + left + " EXCEPT SELECT * FROM " + right + " LIMIT 1"
            ).fetchone()
            check(mismatch is None, ("Observation mismatch", mismatch))
        on = "(full_on+partial_on)"
        off = "(full_off+partial_off)"
        total_eval = "(full_on+partial_on+full_off+partial_off+unknown_eval)"
        stack = '("pass"+fail+pending+incomplete+not_applicable+blank+other)'
        unresolved = "(pending+incomplete+not_applicable+blank+other)"
        expr = [
            "COUNT(*)",
            "SUM(full_on>0)",
            "SUM(" + on + ">0)",
            "SUM(" + on + "=0 AND " + off + ">0)",
            "SUM(" + total_eval + "=0)",
            "SUM(" + on + "+" + off + "=0 AND unknown_eval>0)",
            "SUM(" + stack + "=0)",
            "SUM(fail>0)",
            'SUM(fail=0 AND "pass">0 AND ' + unresolved + "=0)",
            'SUM(fail=0 AND "pass">0 AND ' + unresolved + ">0)",
            "SUM(" + stack + '>0 AND "pass"=0 AND fail=0)',
            'SUM("pass"+fail>0)',
            'SUM("pass">0 AND fail>0)',
        ]
        classes = [r[0] for r in db.execute("SELECT DISTINCT cls FROM cohort")]
        groups = {
            (w, g, level): [0] * len(MEASURES)
            for w in WINDOWS
            for g, levels in [("all", ["ALL"]), ("class", classes), ("state", STATES)]
            for level in levels
        }
        for group, level in [("all", "'ALL'"), ("class", "cls"), ("state", "state")]:
            for row in db.execute(
                "SELECT w,"
                + level
                + ","
                + ",".join(expr)
                + " FROM expected GROUP BY w,"
                + level
            ):
                groups[(row[0], group, row[1])] = list(row[2:])
        with (ROOT / "results/group_counts.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            actual = list(reader)
        check(len(actual) == len(groups), "Complete groups")
        for row in actual:
            key = (row["window"], row["group"], row["level"])
            check([int(row[m]) for m in MEASURES] == groups[key], ("Group", key))
            check(
                sum(
                    int(row[m])
                    for m in [
                        "stack_none",
                        "stack_fail_any",
                        "stack_pass_only",
                        "stack_pass_unresolved",
                        "stack_unresolved_only",
                    ]
                )
                == int(row["facilities"]),
                ("Stack denominator", key),
            )
            check(
                sum(
                    int(row[m])
                    for m in [
                        "any_on",
                        "off_only",
                        "no_evaluation",
                        "unknown_eval_only",
                    ]
                )
                == int(row["facilities"]),
                ("Evaluation denominator", key),
            )
        expected_review = sorted(
            [
                r
                for r in actual
                if r["window"] == "2021-2025" and r["group"] in ["state", "class"]
            ],
            key=lambda r: (-int(r["stack_none"]), r["group"], r["level"]),
        )
        with (ROOT / "results/data_review_groups.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            check(
                list(csv.DictReader(stream)) == expected_review,
                "Full data-review group list",
            )
        db.close()
    result = dict(
        status="PASS",
        assertions=checks,
        facility_window_rows=row_count,
        exact_observation_fields=row_count * len(header),
        group_rows=len(groups),
        independence="Separate SQLite identity/cohort/date/event joins and group aggregation; no analysis helper imports",
        limits="Descriptive current-cohort coverage; not complete national inspections,required-test universe or risk-label validity",
    )
    (ROOT / "results/independent_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
