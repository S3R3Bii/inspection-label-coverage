"""Offline count replay in an owned temporary folder; preserve published originals."""

from pathlib import Path
import csv, gzip, hashlib, json, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "facility_windows.csv.gz",
    "group_counts.csv",
    "data_review_groups.csv",
    "source_audit.json",
]


def main():
    originals = {
        name: hashlib.sha256((ROOT / "results" / name).read_bytes()).hexdigest()
        for name in FILES
    }
    csv_fields = 0
    documents = 0
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run(
            [sys.executable, str(ROOT / "src/run_analysis.py"), "--output-dir", folder],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for name in FILES:
            expected = ROOT / "results" / name
            actual = Path(folder) / name
            if name.endswith(".json"):
                assert json.loads(expected.read_text(encoding="utf-8")) == json.loads(
                    actual.read_text(encoding="utf-8")
                )
                documents += 1
            else:
                opener = gzip.open if name.endswith(".gz") else open
                with opener(expected, "rt", encoding="utf-8", newline="") as a, opener(
                    actual, "rt", encoding="utf-8", newline=""
                ) as b:
                    left = csv.reader(a)
                    right = csv.reader(b)
                    while True:
                        r1 = next(left, None)
                        r2 = next(right, None)
                        assert r1 == r2, (name, csv_fields)
                        if r1 is None:
                            break
                        csv_fields += len(r1)
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Ran 17 tests" in tests.stderr and "OK" in tests.stderr
    assert originals == {
        name: hashlib.sha256((ROOT / "results" / name).read_bytes()).hexdigest()
        for name in FILES
    }
    result = dict(
        status="PASS",
        exact_csv_fields=csv_fields,
        json_documents=documents,
        tests=17,
        original_files_unchanged=True,
        network_during_replay=False,
        scope="Exact descriptive replay; finite tests do not establish complete coverage or valid enforcement outcomes",
    )
    (ROOT / "results/reproduction.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
