"""Original coverage figures; absence is never encoded as a passing result."""

import csv, hashlib, json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "svg.fonttype": "none",
        "svg.hashsalt": "inspection-label-coverage-v1",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def main():
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    geometry = []
    hashes = {}
    with (ROOT / "results/group_counts.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))

    def save(fig, name, artists):
        fig.canvas.draw()
        height = fig.get_figheight() * fig.dpi
        for gid, value, patch in artists:
            points = patch.get_transform().transform(patch.get_path().vertices[:4])
            geometry.append(
                dict(
                    figure=name,
                    gid=gid,
                    value=float(value),
                    points=[
                        [float(x * 72 / fig.dpi), float((height - y) * 72 / fig.dpi)]
                        for x, y in points
                    ],
                )
            )
        for ext in ["pdf", "svg", "png"]:
            path = out / (name + "." + ext)
            fig.savefig(
                path,
                dpi=160,
                metadata=(
                    {"Creator": "Inspection label coverage,study15"}
                    if ext == "pdf"
                    else None
                ),
            )
            if ext == "svg":
                path.write_bytes(
                    (
                        "\n".join(
                            line.rstrip()
                            for line in path.read_text(encoding="utf-8").splitlines()
                        )
                        + "\n"
                    ).encode()
                )
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        plt.close(fig)

    overall = next(
        r for r in rows if r["window"] == "2021-2025" and r["group"] == "all"
    )
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.3))
    fig.subplots_adjust(left=0.20, right=0.98, top=0.79, bottom=0.17, wspace=1.05)
    artists = []
    panels = [
        (
            ["any_on", "off_only", "no_evaluation", "unknown_eval_only"],
            [
                "On-site (any)",
                "Off-site only",
                "No dated evaluation",
                "Unknown code only",
            ],
            "Evaluation records",
        ),
        (
            [
                "stack_none",
                "stack_pass_only",
                "stack_fail_any",
                "stack_pass_unresolved",
                "stack_unresolved_only",
            ],
            [
                "No dated stack record",
                "PSS only",
                "At least one FAI",
                "PSS + unresolved / NA",
                "No PSS or FAI",
            ],
            "Stack-test records",
        ),
    ]
    for j, (fields, labels, title) in enumerate(panels):
        ax = axes[j]
        values = [100 * int(overall[f]) / int(overall["facilities"]) for f in fields]
        bars = ax.barh(
            range(len(fields)),
            values,
            color=[
                "#326b65" if (j == 0 and i == 0) or (j == 1 and i == 1) else "#adb4bb"
                for i in range(len(fields))
            ],
            height=0.63,
        )
        for i, (field, v, p) in enumerate(zip(fields, values, bars)):
            gid = f"coverage-{j}-{i}"
            p.set_gid(gid)
            artists.append((gid, v, p))
            ax.text(
                min(v + 1, 94), i, f"{int(overall[field]):,}", va="center", fontsize=8
            )
        ax.set_yticks(range(len(fields)), labels)
        ax.invert_yaxis()
        ax.set_xlim(0, 115)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel("Share of current cohort (%)")
        ax.set_title(title, loc="left", pad=12)
    fig.suptitle(
        "Recorded observations cover only part of the current cohort",
        x=0.20,
        ha="left",
        fontsize=11,
    )
    fig.text(
        0.20,
        0.035,
        "2021–2025 records; same 183,500 current operating sources. Labels are counts.",
        fontsize=8,
    )
    save(fig, "recorded_coverage", artists)
    classes = sorted(
        [r for r in rows if r["window"] == "2021-2025" and r["group"] == "class"],
        key=lambda r: r["level"],
    )
    fig, ax = plt.subplots(figsize=(8, 4.7))
    fig.subplots_adjust(left=0.30, right=0.97, top=0.82, bottom=0.19)
    artists = []
    for j, (field, color, label) in enumerate(
        [
            ("any_on", "#326b65", "Any on-site evaluation"),
            ("stack_observed_result", "#b36a37", "Observed PSS or FAI"),
        ]
    ):
        values = [100 * int(r[field]) / int(r["facilities"]) for r in classes]
        bars = ax.barh(
            [i + (j - 0.5) * 0.34 for i in range(len(classes))],
            values,
            height=0.31,
            color=color,
            label=label,
        )
        for i, (v, p) in enumerate(zip(values, bars)):
            gid = f"class-{j}-{i}"
            p.set_gid(gid)
            artists.append((gid, v, p))
    names = {
        "MAJ": "Major",
        "MIN": "Minor",
        "SMI": "Synthetic minor",
        "NAP": "Not applicable",
        "OTH": "Other",
        "UNK": "Unknown",
        "<MISSING>": "Missing class",
    }
    ax.set_yticks(
        range(len(classes)),
        [
            names.get(r["level"], r["level"])
            + "  (n="
            + format(int(r["facilities"]), ",")
            + ")"
            for r in classes
        ],
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Within-class recorded coverage (%)")
    ax.set_title(
        "Current source classes have different observation coverage", loc="left", pad=18
    )
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=2,
        fontsize=8,
    )
    save(fig, "class_coverage", artists)
    annual = [
        next(r for r in rows if r["window"] == str(y) and r["group"] == "all")
        for y in range(2021, 2026)
    ]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    fig.subplots_adjust(left=0.12, right=0.98, top=0.81, bottom=0.28)
    artists = []
    for j, (field, color, label) in enumerate(
        [
            ("full_on", "#326b65", "Full on-site"),
            ("any_on", "#82aaa4", "Any on-site"),
            ("stack_observed_result", "#b36a37", "Stack PSS or FAI"),
        ]
    ):
        values = [100 * int(r[field]) / int(r["facilities"]) for r in annual]
        bars = ax.bar(
            [i + (j - 1) * 0.24 for i in range(5)],
            values,
            width=0.22,
            color=color,
            label=label,
        )
        for i, (v, p) in enumerate(zip(values, bars)):
            gid = f"annual-{j}-{i}"
            p.set_gid(gid)
            artists.append((gid, v, p))
    ax.set_xticks(range(5), [r["window"] for r in annual])
    ax.set_ylim(0, 12)
    ax.set_ylabel("Share of current cohort (%)")
    ax.set_title("Annual records in the same current cohort", loc="left", pad=16)
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.17),
        ncol=3,
        fontsize=8,
    )
    save(fig, "annual_coverage", artists)
    (out / "artist_geometry.json").write_bytes(
        (json.dumps(geometry, indent=2) + "\n").encode()
    )
    (out / "manifest.json").write_bytes(
        (json.dumps(hashes, indent=2, sort_keys=True) + "\n").encode()
    )
    print("FIGURES_CREATED", len(geometry), "SOURCE_VALUES")


if __name__ == "__main__":
    main()
