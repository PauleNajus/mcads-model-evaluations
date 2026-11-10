import os
import sys, numpy as np, pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score
root = sys.argv[1]
NIH14 = ["Atelectasis","Cardiomegaly","Consolidation","Edema","Effusion","Emphysema","Fibrosis","Hernia","Infiltration","Mass","Nodule","Pleural_Thickening","Pneumonia","Pneumothorax"]
full = pd.read_csv(f"{root}/results_id/densenet121-res224-all/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str})
rn = pd.read_csv(f"{root}/results_id/resnet50-res512-all/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str})
gss = GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0)
tr, te = next(gss.split(X=np.arange(len(full)), groups=full.PatientID.values.astype(str)))
test_pids = set(full.PatientID.values[te])
rn["heldout"] = rn.PatientID.isin(test_pids)
print("RN50 subset:", len(rn), "held-out images:", rn.heldout.sum())
for part, d in [("train-partition", rn[~rn.heldout]), ("held-out", rn[rn.heldout])]:
    vals=[]; npos=[]
    for l in NIH14:
        y=d[l].values; p=d["pred__"+l].values
        npos.append(int(y.sum()))
        vals.append(roc_auc_score(y,p) if 0<y.sum()<len(y) else np.nan)
    print(part, "n", len(d), "macro", np.nanmean(vals).round(4), "pos per label", npos)
# bootstrap the gap by permuting membership at patient level (null distribution)
pids = rn.PatientID.values
up = np.unique(pids)
rng = np.random.default_rng(0)
obs=None
def macro(d):
    v=[]
    for l in NIH14:
        y=d[l].values; p=d["pred__"+l].values
        if 0<y.sum()<len(y): v.append(roc_auc_score(y,p))
    return np.mean(v)
obs = macro(rn[~rn.heldout]) - macro(rn[rn.heldout])
null=[]
ntest = len(set(pids) & test_pids)
for b in range(300):
    sel = set(rng.choice(up, size=ntest, replace=False))
    m = np.isin(pids, list(sel))
    null.append(macro(rn[~m]) - macro(rn[m]))
null=np.array(null)
print("observed gap (train - heldout):", round(obs,4), " null mean", null.mean().round(4), " null 2.5/97.5", np.percentile(null,[2.5,97.5]).round(4), " p(one-sided)", (np.sum(null>=obs)+1)/(len(null)+1))
