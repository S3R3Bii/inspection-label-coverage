"""Rebuild paper numbers from observation exports and inspect actual PDF text/hashes."""

from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
import csv, gzip, hashlib, json, re, unicodedata
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    groups = defaultdict(Counter)
    with gzip.open(
        ROOT / "results/facility_windows.csv.gz", "rt", encoding="utf-8", newline=""
    ) as stream:
        for r in csv.DictReader(stream):
            count = lambda key: int(r[key])
            on = count("full_on") + count("partial_on")
            off = count("full_off") + count("partial_off")
            unknown = count("unknown_eval")
            passed = count("pass")
            failed = count("fail")
            rest = sum(
                count(f)
                for f in ["pending", "incomplete", "not_applicable", "blank", "other"]
            )
            stack = passed + failed + rest
            d = {
                "facilities": 1,
                "full_on": int(count("full_on") > 0),
                "any_on": int(on > 0),
                "off_only": int(on == 0 and off > 0),
                "no_evaluation": int(on + off + unknown == 0),
                "unknown_eval_only": int(on + off == 0 and unknown > 0),
                "stack_none": int(stack == 0),
                "stack_fail_any": int(failed > 0),
                "stack_pass_only": int(failed == 0 and passed > 0 and rest == 0),
                "stack_pass_unresolved": int(failed == 0 and passed > 0 and rest > 0),
                "stack_unresolved_only": int(stack > 0 and passed + failed == 0),
                "stack_observed_result": int(passed + failed > 0),
                "stack_mixed_pass_fail": int(passed > 0 and failed > 0),
            }
            for g, level in [("all", "ALL"), ("class", r["class"])]:
                groups[(r["window"], g, level)].update(d)
    checks = 0

    def check(ok, message):
        nonlocal checks
        assert ok, message
        checks += 1

    ledger = read("paper/TABLE_VALUES.json")
    check(len(ledger) == 81, "Display ledger")
    reader = PdfReader(ROOT / "paper/manuscript.pdf")
    check(len(reader.pages) == 6, "Six pages")
    texts = [
        " ".join(
            re.sub(
                r"(?<=\w)-\s*\n\s*(?=\w)",
                "",
                unicodedata.normalize("NFKC", p.extract_text()),
            ).split()
        )
        for p in reader.pages
    ]
    for item in ledger:
        if item["kind"] == "source":
            total = sum(
                s["rows"]
                for s in read("data/source_manifest.json")["shards"]
                if s["table"] == item["table"]
            )
            display = format(total, ",")
        else:
            r = groups[(item["window"], item["group"], item["level"])]
            number = r[item["field"]]
            display = (
                str(
                    (Decimal(number) * 100 / Decimal(r["facilities"])).quantize(
                        Decimal(".1"), rounding=ROUND_HALF_EVEN
                    )
                )
                if item["percent"]
                else format(number, ",")
            )
        check(item["display"] == display, ("Arithmetic", item))
        check(display in texts[item["page"] - 1], ("Actual PDF page", item))
    joined = " ".join(texts)
    for phrase in [
        "current operating air sources",
        "13,613 (7.4%)",
        "169,698",
        "required to have a stack test",
        "not historical national inspection rates",
        "corrected retrospective descriptive audit",
        "initial parser rejected every evaluation date",
        "Four stack-test source dates",
        "149 conflicting identities",
        "384 source rows",
        "398 duplicate excess",
        "current legal status",
        "No risk model",
        "propensity correction",
        "missing-at-random assumption",
        "39,720,857",
        "1,101,000",
        "17,616,000",
        "354 group rows",
        "17,622,640",
        "Seventeen finite",
        "no network requests",
        "universal correctness",
        "Separate formal-publication projects",
        "No deployment",
    ]:
        # Extracted line wraps can remove a genuine compound-word hyphen.
        compact = lambda text: re.sub(r"(?<=\w)-(?=\w)", "", text.casefold())
        check(compact(phrase) in compact(joined), phrase)
    scope = read("paper/PUBLICATION_SCOPE.json")
    check(
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
        and len(scope["public_files"]) == 5,
        "Approved paper scope",
    )
    for name, digest in scope["public_files"].items():
        check(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
            ("Approved hash", name),
        )
    check(
        all(len(t) > 800 for t in texts) and not reader.get_fields(),
        "Nonempty pages and no forms",
    )
    pdfroot = reader.trailer["/Root"]
    check(
        "/AA" not in pdfroot and "/JavaScript" not in str(pdfroot.get("/Names", "")),
        "No automatic scripts",
    )
    if pdfroot.get("/OpenAction"):
        action = pdfroot["/OpenAction"].get_object()
        check(
            isinstance(action, list) and str(action[1]) == "/Fit", "Bounded open action"
        )
    for page in reader.pages:
        check("/AA" not in page, "Page automatic action")
        box = page.mediabox
        for ref in page.get("/Annots", []):
            annotation = ref.get_object()
            check("/AA" not in annotation, "Annotation automatic action")
            action = annotation.get("/A")
            if action:
                check(action.get_object().get("/S") == "/URI", "URI only")
            rect = annotation.get("/Rect")
            if rect:
                check(
                    float(rect[0]) >= float(box.left) - 1
                    and float(rect[1]) >= float(box.bottom) - 1
                    and float(rect[2]) <= float(box.right) + 1
                    and float(rect[3]) <= float(box.top) + 1,
                    "Annotation bounds",
                )
    result = dict(
        status="PASS",
        checks=checks,
        pages=6,
        numeric_display_values=81,
        manuscript_sha256=hashlib.sha256(
            (ROOT / "paper/manuscript.pdf").read_bytes()
        ).hexdigest(),
        scope="Observation-export arithmetic,actual page text,qualifications,approved hashes and bounded PDF actions;visual inspection recorded separately",
    )
    (ROOT / "results/paper_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
