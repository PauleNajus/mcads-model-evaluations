import sys, numpy as np, pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score
root = sys.argv[1]
NIH14 = ["Atelectasis","Cardiomegaly","Consolidation","Edema","Effusion","Emphysema","Fibrosis","Hernia","Infiltration","Mass","Nodule","Pleural_Thickening","Pneumonia","Pneumothorax"]
dfs = {}
for m in ["densenet121-res224-all","densenet121-res224-nih"]:
    dfs[m] = pd.read_csv(f"{root}/results_id/{m}/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str})
a, b = dfs["densenet121-res224-all"], dfs["densenet121-res224-nih"]
print(len(a), len(b), (a.PatientID.values == b.PatientID.values).all(), a.PatientID.nunique())
def split(pids, as_int):
    g = pids.astype(int) if as_int else pids.astype(str)
    gss = GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0)
    tr, te = next(gss.split(X=np.arange(len(g)), groups=g))
    return tr, te
def macro(df, idx, m):
    vals = []
    for l in NIH14:
        y = df[l].values[idx]; p = df["pred__"+l].values[idx]
        vals.append(roc_auc_score(y, p))
    return np.mean(vals), vals
for as_int in [False, True]:
    tr, te = split(a.PatientID.values, as_int)
    print("as_int", as_int, "n_train", len(tr), "n_test", len(te), "test patients", a.PatientID.values[te].astype(str).__len__())
    for m, df in dfs.items():
        mt, _ = macro(df, tr, m); ms, v = macro(df, te, m)
        print(f"  {m}: train macro {mt:.4f}  test macro {ms:.4f}  gap {mt-ms:+.4f}")
# random splits for reference
rng = np.random.default_rng(1)
for r in range(5):
    gss = GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=100+r)
    tr, te = next(gss.split(X=np.arange(len(a)), groups=a.PatientID.values))
    out = []
    for m, df in dfs.items():
        mt, _ = macro(df, tr, m); ms, v = macro(df, te, m)
        out.append(f"{m[-3:]} gap {mt-ms:+.4f}")
    print("random split", r, "; ".join(out))
