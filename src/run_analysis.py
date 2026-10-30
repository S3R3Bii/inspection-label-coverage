"""Count recorded observation coverage; never impute a missing compliance outcome."""

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from array import array
import argparse, csv, gzip, io, json

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


def records(table):
    manifest = json.loads(
        (ROOT / "data/source_manifest.json").read_text(encoding="utf-8")
    )
    for shard in manifest["shards"]:
        if shard["table"] == table:
            yield from json.loads(gzip.decompress((ROOT / shard["file"]).read_bytes()))


def parse_date(token):
    token = token.strip()
    for suffix in [" 00:00:00", "T00:00:00", "T00:00:00.000", " 00:00:00.000"]:
        if token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    for pattern in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
        try:
            return datetime.strptime(token, pattern).date()
        except ValueError:
            pass
    return None


def unique_rows(rows, kind):
    seen = {}
    conflicts = set()
    multiplicity = Counter()
    counts = Counter()
    keys = (
        ["PGM_SYS_ID_KEY"]
        if kind == "facilities"
        else ["PGM_SYS_ID_KEY", "ACTIVITY_ID_KEY"]
    )
    fields = None
    for row in rows:
        counts["source_rows"] += 1
        if fields is None:
            fields = sorted(k for k in row if k != "source_row")
        key = tuple(row[k] for k in keys)
        if not all(key):
            counts["missing_identity_rows"] += 1
            continue
        value = tuple(row[k] for k in fields)
        multiplicity[key] += 1
        if key not in seen:
            seen[key] = value
        elif value != seen[key]:
            conflicts.add(key)
        else:
            counts["repeated_first_selected_row"] += 1
    counts["conflicting_identities"] = len(conflicts)
    counts["conflicting_source_rows"] = sum(multiplicity[k] for k in conflicts)
    valid = []
    for key, value in seen.items():
        if key not in conflicts:
            valid.append(dict(zip(fields, value)))
    counts["unique_nonconflicting_rows"] = len(valid)
    counts["exact_duplicate_excess_nonconflicting"] = sum(
        multiplicity[k] - 1 for k in seen if k not in conflicts
    )
    return valid, dict(sorted(counts.items()))


def observations(c):
    on = c[0] + c[1]
    off = c[2] + c[3]
    ev = on + off + c[4]
    stack = sum(c[5:])
    bad = c[7] + c[8] + c[9] + c[10] + c[11]
    if not stack:
        cat = "stack_none"
    elif c[6]:
        cat = "stack_fail_any"
    elif c[5] and not bad:
        cat = "stack_pass_only"
    elif c[5]:
        cat = "stack_pass_unresolved"
    else:
        cat = "stack_unresolved_only"
    return dict(
        facilities=1,
        full_on=int(c[0] > 0),
        any_on=int(on > 0),
        off_only=int(on == 0 and off > 0),
        no_evaluation=int(ev == 0),
        unknown_eval_only=int(on + off == 0 and c[4] > 0),
        stack_none=int(cat == "stack_none"),
        stack_fail_any=int(cat == "stack_fail_any"),
        stack_pass_only=int(cat == "stack_pass_only"),
        stack_pass_unresolved=int(cat == "stack_pass_unresolved"),
        stack_unresolved_only=int(cat == "stack_unresolved_only"),
        stack_observed_result=int(c[5] + c[6] > 0),
        stack_mixed_pass_fail=int(c[5] > 0 and c[6] > 0),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=ROOT / "results")
    a = p.parse_args()
    a.output_dir.mkdir(exist_ok=True)
    fs, faudit = unique_rows(records("facilities"), "facilities")
    all_facilities = {r["PGM_SYS_ID_KEY"] for r in fs}
    cohort = {}
    excluded = Counter()
    for r in fs:
        reasons = []
        if r["STATE"].strip().upper() not in STATES:
            reasons.append("outside_50_states_DC")
        if r["AIR_OPERATING_STATUS_CODE"].strip().upper() != "OPR":
            reasons.append("not_current_OPR")
        if reasons:
            for reason in reasons:
                excluded[reason] += 1
            continue
        cohort[r["PGM_SYS_ID_KEY"]] = {
            "state": r["STATE"].strip().upper(),
            "class": r["AIR_POLLUTANT_CLASS_CODE"].strip().upper() or "<MISSING>",
            "region": r["EPA_REGION"].strip().upper(),
        }
    del fs
    assert cohort, "No eligible current facilities"
    values = {k: array("I", [0]) * (len(WINDOWS) * len(COUNTS)) for k in cohort}
    audit = {
        "facilities": faudit,
        "cohort_facilities": len(cohort),
        "facility_exclusion_reasons_overlap": dict(sorted(excluded.items())),
        "events": {},
    }
    for table in ["evaluations", "stack_tests"]:
        rows, counts = unique_rows(records(table), table)
        quality = Counter()
        tokens = Counter()
        formats = Counter()
        for row in rows:
            key = row["PGM_SYS_ID_KEY"]
            rawdate = row["ACTUAL_END_DATE"]
            d = parse_date(rawdate)
            if key not in all_facilities:
                quality["no_nonconflicting_source_facility"] += 1
            if key not in cohort:
                quality["outside_current_cohort"] += 1
            if d is None:
                quality["invalid_or_missing_date"] += 1
            else:
                formats[
                    (
                        "MM/DD/YYYY"
                        if "/" in rawdate
                        else (
                            "ISO"
                            if len(rawdate) >= 10 and rawdate[4] == "-"
                            else "MM-DD-YYYY"
                        )
                    )
                ] += 1
                if not 2021 <= d.year <= 2025:
                    quality["outside_2021_2025"] += 1
            code = (
                (
                    row["COMP_MONITOR_TYPE_CODE"]
                    if table == "evaluations"
                    else row["AIR_STACK_TEST_STATUS_CODE"]
                )
                .strip()
                .upper()
            )
            tokens[code or "<BLANK>"] += 1
            if key not in cohort or d is None or not 2021 <= d.year <= 2025:
                continue
            if table == "evaluations":
                if code == "FOO":
                    index = 0
                elif code in ["PCE", "POC", "POI", "POM", "POR"]:
                    index = 1
                elif code == "FFO":
                    index = 2
                elif code == "PFF":
                    index = 3
                else:
                    index = 4
            else:
                index = {"PSS": 5, "FAI": 6, "PEN": 7, "INC": 8, "NA": 9, "": 10}.get(
                    code, 11
                )
            quality["included_window_events"] += 1
            for w in [d.year - 2021, 5]:
                values[key][w * len(COUNTS) + index] += 1
        audit["events"][table] = dict(
            identity=counts,
            quality_counts_overlap=dict(sorted(quality.items())),
            all_unique_code_counts=dict(sorted(tokens.items())),
            valid_date_format_counts=dict(sorted(formats.items())),
        )
        del rows
    groups = {}
    classes = sorted({r["class"] for r in cohort.values()})
    for w in WINDOWS:
        for group, levels in [("all", ["ALL"]), ("class", classes), ("state", STATES)]:
            for level in levels:
                groups[(w, group, level)] = Counter({m: 0 for m in MEASURES})
    dest = a.output_dir / "facility_windows.csv.gz"
    with dest.open("wb") as stream:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=stream, mtime=0
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as out:
                writer = csv.writer(out, lineterminator="\n")
                writer.writerow(["window", "facility_key", "state", "class", *COUNTS])
                for key in sorted(cohort):
                    meta = cohort[key]
                    for i, w in enumerate(WINDOWS):
                        c = values[key][i * len(COUNTS) : (i + 1) * len(COUNTS)]
                        writer.writerow([w, key, meta["state"], meta["class"], *c])
                        obs = observations(c)
                        for g, level in [
                            ("all", "ALL"),
                            ("class", meta["class"]),
                            ("state", meta["state"]),
                        ]:
                            groups[(w, g, level)].update(obs)
    group_rows = []
    for (w, g, level), count in sorted(groups.items()):
        group_rows.append(dict(window=w, group=g, level=level, **count))
    with (a.output_dir / "group_counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as out:
        writer = csv.DictWriter(
            out, fieldnames=["window", "group", "level", *MEASURES], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(group_rows)
    # This list directs data reconciliation, not facility inspections or enforcement.
    review = [
        r
        for r in group_rows
        if r["window"] == "2021-2025" and r["group"] in ["state", "class"]
    ]
    review.sort(key=lambda r: (-r["stack_none"], r["group"], r["level"]))
    with (a.output_dir / "data_review_groups.csv").open(
        "w", encoding="utf-8", newline=""
    ) as out:
        writer = csv.DictWriter(
            out, fieldnames=["window", "group", "level", *MEASURES], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(review)
    audit["windows"] = WINDOWS
    (a.output_dir / "source_audit.json").write_bytes(
        (json.dumps(audit, indent=2) + "\n").encode()
    )
    headline = [r for r in group_rows if r["group"] == "all"]
    print(
        json.dumps(
            dict(
                status="COUNTED_NOT_INDEPENDENTLY_VERIFIED",
                overall=headline,
                source_audit=audit,
            )
        )
    )


if __name__ == "__main__":
    main()
