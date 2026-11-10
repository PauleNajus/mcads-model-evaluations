import pickle, sys, io, numpy as np
class SafeUnpickler(pickle.Unpickler):
    ALLOWED = {("numpy.core.multiarray","scalar"),("numpy","dtype"),("numpy._core.multiarray","scalar")}
    def find_class(self, module, name):
        if (module, name) in self.ALLOWED:
            import importlib
            if module.startswith("numpy.core"):
                module = module.replace("numpy.core", "numpy._core")
            return getattr(importlib.import_module(module), name)
        raise pickle.UnpicklingError(f"blocked {module}.{name}")
def load(path):
    with open(path, "rb") as f:
        return SafeUnpickler(f).load()
if __name__ == "__main__":
    d = load(sys.argv[1])
    print(type(d), len(d))
    k = list(d)[:3]
    for kk in k: print(kk, {a: (b if not isinstance(b,(bytes,)) else b[:20]) for a,b in d[kk].items()})
    import collections
    keys = collections.Counter(tuple(sorted(v.keys())) for v in d.values()); print(keys)
    mses = np.array([float(v.get("mse", np.inf)) for v in d.values()])
    print("mse<10:", (mses<10).sum(), " finite:", np.isfinite(mses).sum(), " median mse:", np.median(mses[np.isfinite(mses)]))
