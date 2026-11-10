import os
import sys, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xrv_legacy_split import legacy_split_unique_pa
root = sys.argv[1]
NIH14 = ["Atelectasis","Cardiomegaly","Consolidation","Edema","Effusion","Emphysema","Fibrosis","Hernia","Infiltration","Mass","Nodule","Pleural_Thickening","Pneumonia","Pneumothorax"]
dfs = {m: pd.read_csv(f"{root}/results_id/{m}/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str}) for m in ["densenet121-res224-all","densenet121-res224-nih"]}
df = dfs["densenet121-res224-nih"]
tr_rows, te_rows, tr_p, te_p = legacy_split_unique_pa(df)
print("unique PA patients:", len(tr_rows)+len(te_rows), "train:", len(tr_rows), "test:", len(te_rows))
def macro(d, rows):
    v=[]
    for l in NIH14:
        y=d[l].values[rows]; p=d["pred__"+l].values[rows]
        if 0<y.sum()<len(y): v.append(roc_auc_score(y,p))
    return np.mean(v)
for m,d in dfs.items():
    a=macro(d,tr_rows); b=macro(d,te_rows)
    print(f"{m}: first-PA train-half {a:.4f} vs test-half {b:.4f} gap {a-b:+.4f}")
# null: random halves of the same first-PA set
allrows = np.concatenate([tr_rows, te_rows]); rng=np.random.default_rng(0)
for m,d in dfs.items():
    null=[]
    for b in range(200):
        perm=rng.permutation(allrows); h=len(tr_rows)
        null.append(macro(d,perm[:h])-macro(d,perm[h:]))
    null=np.array(null)
    print(f"  null {m}: mean {null.mean():+.4f}, 2.5-97.5% [{np.percentile(null,2.5):+.4f}, {np.percentile(null,97.5):+.4f}]")
