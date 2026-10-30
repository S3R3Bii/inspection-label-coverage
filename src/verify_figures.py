import hashlib, json, re, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
read = lambda p: json.loads((ROOT / p).read_text(encoding="utf-8"))


def main():
    import csv

    with (ROOT / "results/group_counts.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    expected = {}
    overall = next(
        r for r in rows if r["window"] == "2021-2025" and r["group"] == "all"
    )
    panels = [
        ["any_on", "off_only", "no_evaluation", "unknown_eval_only"],
        [
            "stack_none",
            "stack_pass_only",
            "stack_fail_any",
            "stack_pass_unresolved",
            "stack_unresolved_only",
        ],
    ]
    for j, fields in enumerate(panels):
        for i, f in enumerate(fields):
            expected[f"coverage-{j}-{i}"] = (
                100 * int(overall[f]) / int(overall["facilities"])
            )
    classes = sorted(
        [r for r in rows if r["window"] == "2021-2025" and r["group"] == "class"],
        key=lambda r: r["level"],
    )
    for j, f in enumerate(["any_on", "stack_observed_result"]):
        for i, r in enumerate(classes):
            expected[f"class-{j}-{i}"] = 100 * int(r[f]) / int(r["facilities"])
    for j, f in enumerate(["full_on", "any_on", "stack_observed_result"]):
        for i, y in enumerate(range(2021, 2026)):
            r = next(r for r in rows if r["window"] == str(y) and r["group"] == "all")
            expected[f"annual-{j}-{i}"] = 100 * int(r[f]) / int(r["facilities"])
    geometry = read("figures/artist_geometry.json")
    assert len(geometry) == len(expected) == 38
    checks = 0
    trees = {}
    for record in geometry:
        assert record["value"] == expected[record["gid"]]
        checks += 1
        name = record["figure"]
        if name not in trees:
            trees[name] = ET.parse(ROOT / "figures" / (name + ".svg"))
        group = trees[name].find('.//*[@id="' + record["gid"] + '"]')
        assert group is not None
        path = group.find("{http://www.w3.org/2000/svg}path")
        values = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.attrib["d"]
            )
        ]
        for a, b in zip(values[:8], [v for point in record["points"] for v in point]):
            assert abs(a - b) < 1e-5
            checks += 1
    for name, digest in read("figures/manifest.json").items():
        assert (
            hashlib.sha256((ROOT / "figures" / name).read_bytes()).hexdigest() == digest
        )
        checks += 1
    result = dict(
        status="PASS",
        checks=checks,
        source_values=38,
        svg_coordinates=304,
        hashes=9,
        scope="Source values,actual rendered bar geometry and exact hashes;not completeness,compliance or risk validation",
    )
    (ROOT / "results/figure_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
