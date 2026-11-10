"""Shared data loading and metric code for the revision analyses (diagnostics-4648688).

Inputs are the per-study prediction files released in
https://github.com/PauleNajus/mcads-model-evaluations (predictions_raw.csv), which contain the
default (operating-point-normalized) TorchXRayVision 1.4.0 outputs, labels, and metadata.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = os.environ.get("EVAL_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # repository root with results_id/ and results_ood/
OPTH = json.load(open(os.path.join(os.path.dirname(__file__), "..", "xrv140_opthreshs.json")))

MODELS: List[Tuple[str, str]] = [
    ("densenet121-res224-pc", "DN121-PadChest"),
    ("densenet121-res224-all", "DN121-All"),
    ("resnet50-res512-all", "RN50-All"),
    ("densenet121-res224-chex", "DN121-CheXpert"),
    ("densenet121-res224-mimic_ch", "DN121-MIMIC-CH"),
    ("densenet121-res224-nih", "DN121-NIH"),
    ("densenet121-res224-mimic_nb", "DN121-MIMIC-NB"),
]
MODEL_KEYS = [m for m, _ in MODELS]
SHORT = dict(MODELS)
OPKEY = {
    "densenet121-res224-all": "all", "densenet121-res224-nih": "nih", "densenet121-res224-pc": "pc",
    "densenet121-res224-chex": "chex", "densenet121-res224-mimic_ch": "mimic_ch",
    "densenet121-res224-mimic_nb": "mimic_nb", "resnet50-res512-all": "resnet50-res512-all",
}

COMMON7 = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Pleural Effusion", "Pneumonia", "Pneumothorax"]
FIVE = ["Atelectasis", "Cardiomegaly", "Consolidation", "Pleural Effusion", "Pneumonia"]
NIH14 = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Emphysema", "Fibrosis", "Hernia",
         "Infiltration", "Mass", "Nodule", "Pleural_Thickening", "Pneumonia", "Pneumothorax"]
BRAX_TO_NIH = {"Pleural Effusion": "Effusion"}

AGE_BANDS = ["0-4", "5-14", "15-24", "25-64", "65-84", ">=85"]


def age_band_brax(a: str) -> str:
    s = str(a).strip().lower()
    if "85" in s and "more" in s:
        return ">=85"
    v = float(s)
    if v < 5:
        return "0-4"
    if v < 15:
        return "5-14"
    if v < 25:
        return "15-24"
    if v < 65:
        return "25-64"
    if v < 85:
        return "65-84"
    return ">=85"


def load_label_map(model: str, cohort: str = "ood") -> Dict[str, str]:
    """BRAX label -> prediction column name for this model (OOD)."""
    lm = json.load(open(f"{ROOT}/results_{cohort}/{model}/full_frontal_all/label_map.json"))
    paths = lm["model_pathologies"]
    key = "brax_to_model_index" if cohort == "ood" else "id_to_model_index"
    return {lab: "pred__" + paths[idx] for lab, idx in lm[key].items()}


def load_ood() -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, Dict[str, str]]]:
    preds = {}
    maps = {}
    meta = None
    for m in MODEL_KEYS:
        d = pd.read_csv(f"{ROOT}/results_ood/{m}/full_frontal_all/predictions_raw.csv",
                        dtype={"PatientID": str, "AccessionNumber": str, "PatientAge": str})
        if meta is None:
            meta = d[["PatientID", "PatientSex", "PatientAge", "Manufacturer", "ViewPosition", "AccessionNumber",
                      "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Lesion", "Lung Opacity",
                      "Edema", "Consolidation", "Pneumonia", "Atelectasis", "Pneumothorax", "Pleural Effusion",
                      "Pleural Other", "Fracture", "Support Devices"]].copy()
        else:
            assert (d.AccessionNumber.values == meta.AccessionNumber.values).all(), m
        preds[m] = d
        maps[m] = load_label_map(m, "ood")
    meta["AgeBand"] = meta.PatientAge.map(age_band_brax)
    meta["pid_code"] = pd.factorize(meta.PatientID)[0]
    return meta, preds, maps


def threshold_vector(model: str, colname: str) -> float:
    """Operating threshold t_k used by the library for this output (nan if none)."""
    info = OPTH[OPKEY[model]]
    name = colname.replace("pred__", "")
    labs = info["labels"]
    if name not in labs:
        return float("nan")
    t = info["op_threshs"][labs.index(name)]
    return float("nan") if t is None else float(t)


def inverse_opnorm(s_norm: np.ndarray, t: float) -> np.ndarray:
    """Invert the TorchXRayVision operating-point normalization to recover the sigmoid output."""
    s_norm = np.asarray(s_norm, dtype=np.float64)
    out = np.where(s_norm < 0.5, 2.0 * t * s_norm, 1.0 - 2.0 * (1.0 - t) * (1.0 - s_norm))
    return np.clip(out, 0.0, 1.0)


def opnorm(s: np.ndarray, t: float) -> np.ndarray:
    s = np.asarray(s, dtype=np.float64)
    return np.where(s < t, s / (2 * t), 1.0 - (1.0 - s) / (2 * (1.0 - t)))


# ---------------------------------------------------------------------------------------------
# Metrics (point estimates)
# ---------------------------------------------------------------------------------------------

def ece_equal_width(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error with equal-width bins (identical to the original analysis)."""
    y = y.astype(np.int64)
    p = np.clip(p.astype(np.float64), 0.0, 1.0)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            ece += m.sum() / y.size * abs(y[m].mean() - p[m].mean())
    return float(ece)


def ece_equal_mass(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Adaptive (equal-mass) ECE: studies sorted by score and split into bins of (near) equal size."""
    order = np.argsort(p, kind="mergesort")
    ys, ps = y[order].astype(np.float64), p[order].astype(np.float64)
    ece = 0.0
    for chunk_y, chunk_p in zip(np.array_split(ys, n_bins), np.array_split(ps, n_bins)):
        if chunk_y.size:
            ece += chunk_y.size / ys.size * abs(chunk_y.mean() - chunk_p.mean())
    return float(ece)


def _logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(p.astype(np.float64), eps, 1 - eps)
    return np.log(p / (1 - p))


def calibration_intercept_slope(y: np.ndarray, p: np.ndarray) -> Tuple[float, float]:
    """Calibration-in-the-large (intercept with logit(p) as offset) and calibration slope
    (coefficient of logit(p) in a logistic recalibration model)."""
    import statsmodels.api as sm
    lp = _logit(p)
    y = y.astype(np.float64)
    try:
        m0 = sm.GLM(y, np.ones((y.size, 1)), family=sm.families.Binomial(), offset=lp).fit()
        a = float(m0.params[0])
    except Exception:
        a = float("nan")
    try:
        m1 = sm.GLM(y, sm.add_constant(lp), family=sm.families.Binomial()).fit()
        b = float(m1.params[1])
    except Exception:
        b = float("nan")
    return a, b


def sens_spec(y: np.ndarray, p: np.ndarray, thr: float = 0.5) -> Tuple[float, float]:
    yp = p >= thr
    pos = y == 1
    neg = ~pos
    se = float((yp & pos).sum() / max(1, pos.sum()))
    sp = float((~yp & neg).sum() / max(1, neg.sum()))
    return se, sp


# ---------------------------------------------------------------------------------------------
# Weighted (bootstrap) AUROC / AP, vectorised over replicates
# ---------------------------------------------------------------------------------------------

class RankPrep:
    """Pre-sorted structure for fast weighted AUROC/AP over many weight vectors."""

    def __init__(self, y: np.ndarray, s: np.ndarray):
        order = np.argsort(s, kind="mergesort")
        self.order = order
        ss = s[order]
        self.y = y[order].astype(np.float64)
        starts = np.r_[0, np.flatnonzero(np.diff(ss) != 0) + 1]
        self.starts = starts

    def auroc(self, W: np.ndarray) -> np.ndarray:
        """W: (b, n) nonnegative weights in the ORIGINAL row order. Returns (b,) AUROC."""
        Ws = W[:, self.order].astype(np.float64)
        wp = Ws * self.y
        wn = Ws - wp
        pg = np.add.reduceat(wp, self.starts, axis=1)
        ng = np.add.reduceat(wn, self.starts, axis=1)
        nb = np.cumsum(ng, axis=1) - ng
        num = np.sum(pg * (nb + 0.5 * ng), axis=1)
        den = pg.sum(axis=1) * ng.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return num / den

    def ap(self, W: np.ndarray) -> np.ndarray:
        """Weighted average precision (sklearn definition, ties grouped), descending thresholds."""
        Ws = W[:, self.order].astype(np.float64)
        wp = Ws * self.y
        wn = Ws - wp
        pg = np.add.reduceat(wp, self.starts, axis=1)[:, ::-1]
        ng = np.add.reduceat(wn, self.starts, axis=1)[:, ::-1]
        tp = np.cumsum(pg, axis=1)
        fp = np.cumsum(ng, axis=1)
        P = tp[:, -1:]
        with np.errstate(invalid="ignore", divide="ignore"):
            prec = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
            return np.sum((pg / P) * prec, axis=1)


def cluster_bootstrap_weights(groups: np.ndarray, B: int, seed: int) -> np.ndarray:
    """(B, n) integer weights: patients resampled with replacement; each study weighted by the
    number of times its patient was drawn."""
    rng = np.random.default_rng(seed)
    G = groups.max() + 1
    W = np.empty((B, groups.size), dtype=np.int16)
    for b in range(B):
        draw = rng.integers(0, G, size=G)
        cnt = np.bincount(draw, minlength=G)
        W[b] = cnt[groups]
    return W


def pct_ci(x: np.ndarray, lo: float = 2.5, hi: float = 97.5) -> Tuple[float, float]:
    x = x[np.isfinite(x)]
    return float(np.percentile(x, lo)), float(np.percentile(x, hi))


def holm(pvals: Sequence[float]) -> np.ndarray:
    p = np.asarray(pvals, dtype=float)
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj
