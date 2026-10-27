"""Render scientific figures from verified JSON, outside the experiment environment.

Example: uv tool run --from matplotlib==3.10.7 python scripts/plot_research.py OUTPUT_DIR
"""
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out = Path(sys.argv[1]).resolve()
data = json.loads((out / "results.json").read_text(encoding="utf-8"))
figures = out / "figures"
figures.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white", "savefig.facecolor": "white",
                     "axes.grid": True, "grid.alpha": 0.2, "svg.fonttype": "none"})
methods = [e["method_id"] for e in data["selection"]["baseline_selection"]] + ["ghj_coverage"]
labels = {g["method_id"]: g["label"] for g in data["groups"]}
colors = dict(zip(methods, ["#5b6670", "#357ca5", "#765b9b", "#4f886a", "#d18b28", "#bc6375", "#007f89"]))
primary = "natural_heterogeneous"
final = [e for e in data["evidence"] if e["record"]["stage"] == "test"]


def save(fig, name):
    fig.savefig(figures / (name + ".png"), dpi=180, bbox_inches="tight")
    fig.savefig(figures / (name + ".svg"), bbox_inches="tight")
    fig.savefig(figures / (name + ".pdf"), bbox_inches="tight")
    plt.close(fig)


fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
for ax, scenario in zip(axes.flat, data["config"]["scenarios"]):
    for method in methods:
        runs = [e for e in final if e["record"]["method_id"] == method and e["record"]["scenario"] == scenario]
        curves = np.array([[point["metrics"]["mean_client_macro_f1"] for point in e["summary"]["curve"]] for e in runs])
        mean, sd = curves.mean(axis=0), curves.std(axis=0, ddof=1)
        x = np.array([0.25, 0.5, 0.75, 1.0])
        ax.plot(x, mean, marker="o", ms=3, label=labels[method], color=colors[method], lw=2 if method == "ghj_coverage" else 1.3)
        ax.fill_between(x, mean-sd, mean+sd, color=colors[method], alpha=0.07)
    ax.set_title(scenario.replace("_", " ").title())
    ax.set_xlabel("Fraction of fixed simulated budget B")
    ax.set_ylabel("Mean client Macro-F1 (test)")
    ax.set_xticks([0.25, 0.5, 0.75, 1])
handles, legend_labels = axes[0,0].get_legend_handles_labels()
fig.legend(handles, legend_labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.015), frameon=False)
fig.suptitle("Quality at the last completed round before each fixed time point", fontsize=15)
fig.tight_layout(rect=[0, 0.06, 1, 0.96])
save(fig, "quality-curves")

comparison = data["primary_preregistered_comparison"]
fig, ax = plt.subplots(figsize=(9, 4.5))
seeds = list(comparison["differences_by_seed"])
y = list(comparison["differences_by_seed"].values())
ax.bar(seeds, y, color=["#007f89" if v >= 0 else "#bc6375" for v in y], width=0.55)
ax.axhline(0, color="#293b4c", lw=1)
ax.axhline(data["config"]["evaluation"]["minimum_meaningful_delta"], color="#d18b28", ls="--", label="Preregistered practical threshold")
ax.set_ylabel("Candidate minus baseline: Macro-F1")
ax.set_xlabel("Paired final seed")
strongest = data["selection"]["strongest_baseline"]["method_id"]
ax.set_title("ghj Coverage vs " + labels[strongest] + " (baseline chosen before test)")
ax.legend(frameon=False)
fig.text(0.12, 0.005, f"Mean difference {comparison['mean']:+.4f}; exact two-sided sign-flip p={comparison['exact_two_sided_sign_flip_p']:.4f}; n=5", fontsize=10)
fig.tight_layout(rect=[0, .035, 1, 1])
save(fig, "paired-differences")

fig, axes = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [1.1, 1]})
show = ["fedavg_u_uniform", "fedavg_u_round_robin", "fedavg_u_fast_random", "ghj_coverage"]
client_ids = sorted(int(c) for c in next(e["summary"] for e in final if e["record"]["method_id"] == "ghj_coverage")["participations"])
counts, quality = [], []
for method in show:
    runs = [e for e in final if e["record"]["method_id"] == method and e["record"]["scenario"] == primary]
    counts.append([np.mean([e["summary"]["participations"][str(c)] for e in runs]) for c in client_ids])
    values = [e["summary"]["tail_20_percent_macro_f1"] for e in runs]
    quality.append((np.mean(values), np.std(values, ddof=1)))
im = axes[0].imshow(counts, aspect="auto", cmap="YlGnBu")
axes[0].set_yticks(range(len(show)), [labels[m] for m in show])
axes[0].set_xticks(range(len(client_ids)), client_ids, fontsize=8)
axes[0].set_xlabel("Client identity")
axes[0].set_title("Mean paid participations across the five final speed mappings")
fig.colorbar(im, ax=axes[0], label="Participations", fraction=.03)
axes[1].bar([labels[m] for m in show], [v[0] for v in quality], yerr=[v[1] for v in quality], color=[colors[m] for m in show], capsize=4)
axes[1].set_ylabel("Worst 20% client Macro-F1")
axes[1].set_title("Tail quality: mean ± seed SD (descriptive, not causal identification)")
fig.tight_layout()
save(fig, "participation")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
matched = data["matched_100_rounds"]
for ax, kind in zip(axes, ("full", "matched")):
    if kind == "full":
        entries=[]
        for item in matched:
            config_hash = (data["selection"]["candidate"] if item["method_id"] == "ghj_coverage" else
                           next(e for e in data["selection"]["baseline_selection"] if e["method_id"] == item["method_id"]))
            scores = list(config_hash["scores_by_seed"].values())
            entries.append((item["label"], np.mean(scores), np.std(scores, ddof=1), item["method_id"]))
        ax.set_title("Fixed B: open validation, seeds 11/22/33")
    else:
        entries=[(e["label"], e["mean"], e["sd"], e["method_id"]) for e in matched]
        ax.set_title("Exactly 100 rounds: same open validation seeds")
    ax.bar([e[0] for e in entries], [e[1] for e in entries], yerr=[e[2] for e in entries], color=[colors[e[3]] for e in entries], capsize=4)
    ax.set_ylabel("Mean client Macro-F1 (validation)")
    ax.tick_params(axis="x", labelrotation=12)
fig.suptitle("Throughput and equal-update diagnostics use development data only")
fig.tight_layout()
save(fig, "matched-updates")

fig, ax = plt.subplots(figsize=(9, 4.8))
show = ["ghj_coverage", "ghj_coverage_no_wait", "ghj_coverage_no_speed", "fedavg_u_fast_random"]
entries = [next(g for g in data["groups"] if g["method_id"] == m and g["scenario"] == primary) for m in show]
ax.bar([e["label"] for e in entries], [e["mean"] for e in entries], yerr=[e["sd"] for e in entries], color=["#007f89", "#89a8a8", "#b3c5c5", "#d18b28"], capsize=4)
ax.set_ylabel("Mean client Macro-F1 (test)")
ax.set_title("Preregistered coverage ablations: five final seeds")
ax.tick_params(axis="x", labelrotation=10)
fig.text(.1, .01, "No-wait matches the reserved slot's speed tier per round; later selection trajectories can diverge.", fontsize=9)
fig.tight_layout(rect=[0, .05, 1, 1])
save(fig, "ablations")

fig, ax = plt.subplots(figsize=(11, 5))
scenarios = data["config"]["scenarios"]
x = np.arange(4)
for method in methods:
    entries=[next(g for g in data["groups"] if g["method_id"] == method and g["scenario"] == s) for s in scenarios]
    ax.errorbar(x, [g["mean"] for g in entries], yerr=[g["sd"] for g in entries], marker="o", capsize=3,
                color=colors[method], label=labels[method], lw=2 if method == "ghj_coverage" else 1)
ax.set_xticks(x, ["Near-IID / homo", "Near-IID / hetero", "Natural / homo", "Natural / hetero"])
ax.set_ylabel("Mean client Macro-F1 (test)")
ax.set_title("Sensitivity to data heterogeneity and independently assigned speed mappings")
ax.legend(loc="lower center", bbox_to_anchor=(.5, -0.3), ncol=4, frameon=False)
fig.tight_layout()
save(fig, "scenario-sensitivity")
print("Rendered six figure sets as PNG/SVG/PDF.")
