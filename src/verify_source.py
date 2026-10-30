"""Verify hashes/schema; optionally reconcile every selected source cell via Pandas."""

from pathlib import Path
import argparse, gzip, hashlib, json, re, zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "facilities": [
        "PGM_SYS_ID",
        "STATE",
        "EPA_REGION",
        "AIR_POLLUTANT_CLASS_CODE",
        "AIR_OPERATING_STATUS_CODE",
    ],
    "evaluations": [
        "PGM_SYS_ID",
        "ACTIVITY_ID",
        "STATE_EPA_FLAG",
        "COMP_MONITOR_TYPE_CODE",
        "ACTUAL_END_DATE",
    ],
    "stack_tests": [
        "PGM_SYS_ID",
        "ACTIVITY_ID",
        "STATE_EPA_FLAG",
        "COMP_MONITOR_TYPE_CODE",
        "ACTUAL_END_DATE",
        "AIR_STACK_TEST_STATUS_CODE",
    ],
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--private-dir", type=Path)
    a = p.parse_args()
    manifest = json.loads(
        (ROOT / "data/source_manifest.json").read_text(encoding="utf-8")
    )
    checks = 0
    counts = {}
    z = None

    def check(condition, message):
        nonlocal checks
        assert condition, message
        checks += 1

    check(manifest["request"]["http_status"] == 200, "HTTP")
    if a.private_dir:
        raw = a.private_dir / "ICIS-AIR_downloads.zip"
        check(
            hashlib.sha256(raw.read_bytes()).hexdigest()
            == manifest["request"]["sha256"],
            "Original archive",
        )
        z = zipfile.ZipFile(raw)
    for table, fields in FIELDS.items():
        shards = [s for s in manifest["shards"] if s["table"] == table]
        original_chunks = None
        if z:
            member = manifest["tables"][table]["member"]
            check(
                hashlib.sha256(z.read(member)).hexdigest()
                == manifest["tables"][table]["member_sha256"],
                "Member hash",
            )
            original_chunks = iter(
                pd.read_csv(
                    z.open(member),
                    dtype=str,
                    keep_default_na=False,
                    encoding="utf-8-sig",
                    chunksize=100000,
                )
            )
        n = 0
        for shard in shards:
            data = (ROOT / shard["file"]).read_bytes()
            check(hashlib.sha256(data).hexdigest() == shard["sha256"], "Shard hash")
            rows = json.loads(gzip.decompress(data))
            check(len(rows) == shard["rows"], "Shard count")
            original = next(original_chunks) if original_chunks is not None else None
            if original is not None:
                check(len(original) == len(rows), "Independent parser rows")
                original = original[fields]
                original_rows = original.to_dict("records")
            for j, row in enumerate(rows):
                n += 1
                check(row["source_row"] == n, "Source ordinal")
                expected_fields = {"source_row"} | {
                    f + "_KEY" if f in ["PGM_SYS_ID", "ACTIVITY_ID"] else f
                    for f in fields
                }
                check(set(row) == expected_fields, "Minimal schema")
                for field in fields:
                    key = (
                        field + "_KEY"
                        if field in ["PGM_SYS_ID", "ACTIVITY_ID"]
                        else field
                    )
                    value = row[key]
                    check(isinstance(value, str), "String token")
                    if field in ["PGM_SYS_ID", "ACTIVITY_ID"]:
                        check(
                            value == ""
                            or re.fullmatch("[a-f0-9]{64}", value) is not None,
                            "Full hash key",
                        )
                    if original is not None:
                        expected = original_rows[j][field]
                        if field in ["PGM_SYS_ID", "ACTIVITY_ID"]:
                            expected = (
                                hashlib.sha256(expected.strip().encode()).hexdigest()
                                if expected.strip()
                                else ""
                            )
                        check(value == expected, "Independent source cell")
            if original_chunks is not None and shard == shards[-1]:
                check(next(original_chunks, None) is None, "No omitted source tail")
        check(n == manifest["tables"][table]["source_rows"], "Complete source table")
        counts[table] = n
    if z:
        z.close()
    result = dict(
        status="PASS",
        mode=(
            "PRIVATE_ORIGINALS_INDEPENDENT_PANDAS_PASS"
            if a.private_dir
            else "PUBLIC_HASH_SCHEMA_ONLY"
        ),
        checks=checks,
        table_rows=counts,
        limits="Current snapshot; no historical publication vintages or independent engineering/compliance labels",
    )
    if a.private_dir:
        (ROOT / "data/source_verification.json").write_bytes(
            (json.dumps(result, indent=2) + "\n").encode()
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
