"""Regenerate Figures 2-5 for the revised manuscript (larger type, consistent order and colors)."""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import COMMON7, MODEL_KEYS, SHORT  # noqa: E402

OUT = os.environ.get("REV_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))
FIG = os.environ.get("REV_FIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures"))
import os  # noqa: E402

os.makedirs(FIG, exist_ok=True)
res = json.load(open(f"{OUT}/ood_results.json"))
plot = json.load(open(f"{OUT}/ood_plotdata.json"))

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 10.5, "axes.labelsize": 10,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9.5, "axes.linewidth": 0.8,
    "savefig.dpi": 400, "pdf.fonttype": 42,
})
# Okabe-Ito palette; solid = training data included PadChest, dashed = single-source models
STYLE = {
    "densenet121-res224-pc": ("#0072B2", "-"),
    "densenet121-res224-all": ("#E69F00", "-"),
    "resnet50-res512-all": ("#009E73", "-"),
    "densenet121-res224-chex": ("#D55E00", "--"),
    "densenet121-res224-mimic_ch": ("#CC79A7", "--"),
    "densenet121-res224-nih": ("#56B4E9", "--"),
    "densenet121-res224-mimic_nb": ("#000000", "--"),
}
LABEL_TITLE = {"Pleural Effusion": "Pleural effusion"}

# ---------------------------------------------------------------------------------------------
# Figure 2: macro AUROC with 95% CIs (seven labels; five labels as sensitivity analysis)
# ---------------------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.0, 3.6))
ypos = np.arange(len(MODEL_KEYS))[::-1]
for y, m in zip(ypos, MODEL_KEYS):
    d = res["discrimination"][m]
    c = STYLE[m][0]
    lo, hi = d["macro7_auroc_ci"]
    ax.errorbar(d["macro7_auroc"], y + 0.15, xerr=[[d["macro7_auroc"] - lo], [hi - d["macro7_auroc"]]], fmt="o",
                color=c, ms=7, capsize=3, lw=1.6, mfc=c)
    lo5, hi5 = d["macro5_auroc_ci"]
    ax.errorbar(d["macro5_auroc"], y - 0.15, xerr=[[d["macro5_auroc"] - lo5], [hi5 - d["macro5_auroc"]]], fmt="s",
                color=c, ms=6, capsize=3, lw=1.2, mfc="white", mew=1.4)
    ax.text(0.865, y + 0.15, f"{d['macro7_auroc']:.3f}", va="center", ha="left", fontsize=9)
    ax.text(0.865, y - 0.15, f"{d['macro5_auroc']:.3f}", va="center", ha="left", fontsize=9, color="#444444")
ax.set_yticks(ypos)
ax.set_yticklabels([SHORT[m] for m in MODEL_KEYS])
ax.set_xlim(0.58, 0.90)
ax.set_xticks([0.60, 0.65, 0.70, 0.75, 0.80, 0.85])
ax.set_xlabel("Macro AUROC (95% CI)")
ax.grid(axis="x", color="#dddddd", lw=0.6)
ax.set_axisbelow(True)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
h = [Line2D([], [], marker="o", color="#333333", ls="", ms=7, label="Seven common labels (primary)"),
     Line2D([], [], marker="s", color="#333333", mfc="white", ls="", ms=6, mew=1.4,
            label="Five labels, edema and pneumothorax excluded")]
ax.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False, ncol=2, fontsize=9)
fig.tight_layout()
fig.savefig(f"{FIG}/figure2_macro_auroc_ci.png")
plt.close(fig)

# ---------------------------------------------------------------------------------------------
# Figure 3: ROC curves, 3 x 3 grid, legend in the last two cells
# ---------------------------------------------------------------------------------------------
fig, axes = plt.subplots(3, 3, figsize=(7.0, 7.3))
axes = axes.ravel()
letters = "abcdefg"
for i, lab in enumerate(COMMON7):
    ax = axes[i]
    for m in MODEL_KEYS:
        f, t = plot["roc"][m][lab]
        c, ls = STYLE[m]
        ax.plot(f, t, color=c, ls=ls, lw=1.7)
    ax.plot([0, 1], [0, 1], color="#999999", ls=":", lw=1.0)
    npos = res["discrimination"][MODEL_KEYS[0]]["per_label"][lab]["pos"]
    ax.set_title(f"({letters[i]}) {LABEL_TITLE.get(lab, lab)}\n$n_+$ = {npos:,}", fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 0.5, 1])
    ax.set_yticks([0, 0.5, 1])
    ax.set_aspect("equal")
    if i % 3 == 0:
        ax.set_ylabel("True-positive rate")
    if i >= 4:
        ax.set_xlabel("False-positive rate")
for j in [7, 8]:
    axes[j].axis("off")
handles = [Line2D([], [], color=STYLE[m][0], ls=STYLE[m][1], lw=2.2, label=SHORT[m]) for m in MODEL_KEYS]
handles.append(Line2D([], [], color="#999999", ls=":", lw=1.2, label="Chance"))
fig.legend(handles=handles, loc="center", bbox_to_anchor=(0.69, 0.18), frameon=False, ncol=2, fontsize=10,
           handlelength=2.6, columnspacing=1.6, title="Model", title_fontsize=10.5)
fig.tight_layout(h_pad=1.2, w_pad=0.8)
fig.savefig(f"{FIG}/figure3_roc_curves.png")
plt.close(fig)

# ---------------------------------------------------------------------------------------------
# Figure 4: heatmaps (a) Brier, default outputs; (b) ECE, default outputs; (c) ECE, raw sigmoid outputs
# ---------------------------------------------------------------------------------------------
cal = res["calibration"]
mat = {k: np.array([[cal[m][lab][kind][metric] for m in MODEL_KEYS] for lab in COMMON7])
       for k, (kind, metric) in {"a": ("default", "brier"), "b": ("default", "ece"), "c": ("raw", "ece")}.items()}
titles = {"a": "(a) Brier score, default outputs", "b": "(b) ECE, default outputs",
          "c": "(c) ECE, raw sigmoid outputs (operating-point normalization removed)"}
fig, axes = plt.subplots(3, 1, figsize=(7.0, 8.4))
xt = [SHORT[m].replace("DN121-", "DN121-\n") for m in MODEL_KEYS]
yt = [LABEL_TITLE.get(lab, lab) for lab in COMMON7]
vmax_ece = max(mat["b"].max(), mat["c"].max())
for ax, k in zip(axes, ["a", "b", "c"]):
    M = mat[k]
    vmax = M.max() if k == "a" else vmax_ece
    im = ax.imshow(M, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")
    for r_ in range(M.shape[0]):
        for c_ in range(M.shape[1]):
            v = M[r_, c_]
            ax.text(c_, r_, f"{v:.3f}", ha="center", va="center", fontsize=9,
                    color="white" if v > 0.62 * vmax else "black")
    ax.set_xticks(range(len(MODEL_KEYS)))
    ax.set_xticklabels(xt, fontsize=9)
    ax.set_yticks(range(len(COMMON7)))
    ax.set_yticklabels(yt, fontsize=9.5)
    ax.set_title(titles[k], loc="left", fontsize=10.5)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
    cb.ax.tick_params(labelsize=8.5)
fig.tight_layout(h_pad=1.4)
fig.savefig(f"{FIG}/figure4_calibration_heatmaps.png")
plt.close(fig)

# ---------------------------------------------------------------------------------------------
# Figure 5: reliability diagrams of the default outputs, five labels with >= 240 positive studies
# ---------------------------------------------------------------------------------------------
sel = ["resnet50-res512-all", "densenet121-res224-all", "densenet121-res224-mimic_ch"]
labs5 = ["Atelectasis", "Cardiomegaly", "Consolidation", "Pleural Effusion", "Pneumonia"]
fig, axes = plt.subplots(2, 3, figsize=(7.0, 5.4))
axes = axes.ravel()
for i, lab in enumerate(labs5):
    ax = axes[i]
    ax.plot([0, 1], [0, 1], color="#999999", ls=":", lw=1.0)
    for m in sel:
        rows = np.array(plot["rel"][m][lab]["default"])
        c = STYLE[m][0]
        ax.plot(rows[:, 0], rows[:, 1], color=c, lw=1.6, zorder=2)
        ax.scatter(rows[:, 0], rows[:, 1], s=8 + 9 * np.log10(rows[:, 2]), color=c, zorder=3, edgecolor="white",
                   linewidth=0.5)
    npos = res["discrimination"][MODEL_KEYS[0]]["per_label"][lab]["pos"]
    ax.set_title(f"({'abcde'[i]}) {LABEL_TITLE.get(lab, lab)}\n$n_+$ = {npos:,}", fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 0.5, 1])
    ax.set_yticks([0, 0.5, 1])
    ax.set_aspect("equal")
    if i % 3 == 0:
        ax.set_ylabel("Observed positive fraction")
    if i >= 2:
        ax.set_xlabel("Mean predicted score")
axes[5].axis("off")
h = [Line2D([], [], color=STYLE[m][0], lw=2.2, marker="o", ms=6, label=SHORT[m]) for m in sel]
h.append(Line2D([], [], color="#999999", ls=":", lw=1.2, label="Perfect calibration"))
axes[5].legend(handles=h, loc="center", frameon=False, fontsize=10, title="Model", title_fontsize=10.5)
fig.tight_layout(h_pad=1.0, w_pad=0.6)
fig.savefig(f"{FIG}/figure5_reliability.png")
plt.close(fig)
print("figures written")
