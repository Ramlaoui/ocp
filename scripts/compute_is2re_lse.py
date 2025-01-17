import json
from pathlib import Path
import h5py
from tqdm import tqdm
import numpy as np
from sklearn.feature_extraction import DictVectorizer
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ocpmodels.datasets.lmdb_dataset import LmdbDataset


def count_fn(y):
    return dict(zip(*np.unique(y, return_counts=True)))


if __name__ == "__main__":
    # from  SO3Krates
    # https://github.com/thorben-frank/mlff/blob/v0.1/mlff/src/data/preprocessing.py#L297
    ds = LmdbDataset({"src": "/network/projects/ocp/oc20/is2re/all/train/"})
    data = [(d["y"], d["atomic_numbers"]) for d in tqdm(ds, total=len(ds))]

    q = np.array([d[0].item() for d in data])
    max_n_atoms = max([len(d[1]) for d in data])
    z = np.array([np.pad(d[1], (0, max_n_atoms - len(d[1]))) for d in data])
    u = np.unique(z)
    idx_ = u != 0  # remove padding with 0
    lhs_counts = list(map(count_fn, z))
    v = DictVectorizer(sparse=False)
    X = v.fit_transform(lhs_counts)
    X = X[..., idx_]

    sol = np.linalg.lstsq(X, q, rcond=None)
    shifts = np.zeros(np.max(u) + 1)
    for k, v in dict(zip(u[idx_], sol[0])).items():
        shifts[k] = v

    (
        Path("/home/mila/s/schmidtv/ocp-project/ocp-drlab")
        / "configs"
        / "models"
        / "is2re-metadata"
        / "lse-shifts.json"
    ).write_text(json.dumps(shifts.tolist()))

    q_shifts = shifts[z].sum(-1)
