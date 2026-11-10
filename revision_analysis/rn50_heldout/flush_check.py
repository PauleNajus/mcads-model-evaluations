#!/usr/bin/env python3
"""Check that flushing denormal numbers to zero does not change the scores.

Usage: flush_check.py <workdir> <part> <n images>   (runs the same images with RN50_FLUSH=1 and RN50_FLUSH=0)
"""
import json, os, subprocess, sys
import numpy as np

work, part, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
if len(sys.argv) > 4:                                  # child process: one setting
    import torch
    torch.set_num_threads(1)
    torch.set_flush_denormal(os.environ["RN50_FLUSH"] == "1")
    import torchxrayvision as xrv
    model = xrv.models.ResNet(weights="resnet50-res512-all", cache_dir=f"{work}/weights").eval()
    arr = np.load(f"{work}/pre/part{part:03d}.npy", mmap_mode="r")
    xb = np.stack([xrv.datasets.normalize(np.asarray(arr[r]), maxval=255, reshape=True) for r in range(n)])
    with torch.no_grad():
        o = model(torch.from_numpy(xb).float().to(memory_format=torch.channels_last)).numpy()
    np.save(sys.argv[4], np.clip(o.astype(np.float32), 0, 1))
    sys.exit(0)
outs = []
for flag in ("1", "0"):
    f = f"{work}/flush_check_{flag}.npy"
    subprocess.run([sys.executable, __file__, work, str(part), str(n), f], env=dict(os.environ, RN50_FLUSH=flag), check=True)
    outs.append(np.load(f))
d = np.abs(outs[0] - outs[1])
res = {"part": part, "images": n, "max_abs_difference": float(d.max()), "identical": bool((outs[0] == outs[1]).all())}
json.dump(res, open(f"{work}/flush_check.json", "w"), indent=1)
print(res)
