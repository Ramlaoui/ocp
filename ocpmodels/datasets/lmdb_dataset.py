"""lmdb_dataset.py
Copyright (c) Facebook, Inc. and its affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import bisect
import logging
import pickle
import time
import warnings
from pathlib import Path

import lmdb
import numpy as np
import torch
from torch.utils.data import Dataset
from torch_geometric.data import Batch

from ocpmodels.common.registry import registry
from ocpmodels.common.utils import pyg2_data_transform


@registry.register_dataset("lmdb")
@registry.register_dataset("single_point_lmdb")
@registry.register_dataset("trajectory_lmdb")
class LmdbDataset(Dataset):
    r"""Dataset class to load from LMDB files containing relaxation
    trajectories or single point computations.

    Useful for Structure to Energy & Force (S2EF), Initial State to
    Relaxed State (IS2RS), and Initial State to Relaxed Energy (IS2RE) tasks.

    Args:
            config (dict): Dataset configuration
            transform (callable, optional): Data transform function.
                    (default: :obj:`None`)
    """

    def __init__(self, config, transform=None, fa_frames=None, lmdb_glob=None):
        super().__init__()
        self.config = config

        self.path = Path(self.config["src"])
        if not self.path.is_file():
            db_paths = sorted(self.path.glob("*.lmdb"))
            if lmdb_glob:
                db_paths = [
                    p for p in db_paths if any(lg in p.stem for lg in lmdb_glob)
                ]
            assert len(db_paths) > 0, f"No LMDBs found in '{self.path}'"

            self.metadata_path = self.path / "metadata.npz"

            self._keys, self.envs = [], []
            for db_path in db_paths:
                self.envs.append(self.connect_db(db_path))
                length = self.envs[-1].begin().get("length".encode("ascii"))
                if length is not None:
                    length = pickle.loads(length)
                else:
                    length = self.envs[-1].stat()["entries"]
                assert length is not None, f"Could not find length of LMDB {db_path}"
                self._keys.append(list(range(length)))

            keylens = [len(k) for k in self._keys]
            self._keylen_cumulative = np.cumsum(keylens).tolist()
            self.num_samples = sum(keylens)
        else:
            self.metadata_path = self.path.parent / "metadata.npz"
            self.env = self.connect_db(self.path)
            self._keys = [
                f"{j}".encode("ascii") for j in range(self.env.stat()["entries"])
            ]
            self.num_samples = len(self._keys)

        self.transform = transform
        self.fa_method = fa_frames

    def __len__(self):
        return self.num_samples

    def get_pickled_from_db(self, idx):
        if not self.path.is_file():
            # Figure out which db this should be indexed from.
            db_idx = bisect.bisect(self._keylen_cumulative, idx)
            # Extract index of element within that db.
            el_idx = idx
            if db_idx != 0:
                el_idx = idx - self._keylen_cumulative[db_idx - 1]
            assert el_idx >= 0

            # Return features.
            return (
                f"{db_idx}_{el_idx}",
                self.envs[db_idx]
                .begin()
                .get(f"{self._keys[db_idx][el_idx]}".encode("ascii")),
            )

        return None, self.env.begin().get(self._keys[idx])

    def __getitem__(self, idx):
        t0 = time.time_ns()

        el_id, datapoint_pickled = self.get_pickled_from_db(idx)
        data_object = pyg2_data_transform(pickle.loads(datapoint_pickled))
        if el_id:
            data_object.id = el_id

        t1 = time.time_ns()
        if self.transform is not None:
            data_object = self.transform(data_object)
        t2 = time.time_ns()

        load_time = (t1 - t0) * 1e-9  # time in s
        transform_time = (t2 - t1) * 1e-9  # time in s
        total_get_time = (t2 - t0) * 1e-9  # time in s

        data_object.load_time = load_time
        data_object.transform_time = transform_time
        data_object.total_get_time = total_get_time
        data_object.idx_in_dataset = idx

        return data_object

    def connect_db(self, lmdb_path=None):
        # https://lmdb.readthedocs.io/en/release/#environment-class
        env = lmdb.open(
            str(lmdb_path),
            subdir=False,
            readonly=True,
            lock=False,
            readahead=False,
            meminit=False,
            max_readers=1,
        )
        return env

    def close_db(self):
        print("Closing", str(self.path))
        if not self.path.is_file():
            for env in self.envs:
                env.close()
        else:
            self.env.close()


@registry.register_dataset("deup_lmdb")
class DeupDataset(LmdbDataset):
    def __init__(self, all_datasets_configs, deup_split, transform=None):
        super().__init__(
            all_datasets_configs[deup_split],
            lmdb_glob=deup_split.replace("deup-", "").split("-"),
        )
        ocp_splits = deup_split.split("-")[1:]
        self.ocp_datasets = {
            d: LmdbDataset(all_datasets_configs[d], transform) for d in ocp_splits
        }

    def __getitem__(self, idx):
        _, datapoint_pickled = self.get_pickled_from_db(idx)
        deup_sample = pickle.loads(datapoint_pickled)
        ocp_sample = self.ocp_datasets[deup_sample["ds"]][deup_sample["idx_in_dataset"]]
        for k, v in deup_sample.items():
            setattr(ocp_sample, f"deup_{k}", v)
        return ocp_sample


class SinglePointLmdbDataset(LmdbDataset):
    def __init__(self, config, transform=None):
        super(SinglePointLmdbDataset, self).__init__(config, transform)
        warnings.warn(
            "SinglePointLmdbDataset is deprecated and will be removed in the future."
            "Please use 'LmdbDataset' instead.",
            stacklevel=3,
        )


class TrajectoryLmdbDataset(LmdbDataset):
    def __init__(self, config, transform=None):
        super(TrajectoryLmdbDataset, self).__init__(config, transform)
        warnings.warn(
            "TrajectoryLmdbDataset is deprecated and will be removed in the future."
            "Please use 'LmdbDataset' instead.",
            stacklevel=3,
        )


def data_list_collater(data_list, otf_graph=False):
    batch = Batch.from_data_list(data_list)

    if (
        not otf_graph
        and hasattr(data_list[0], "edge_index")
        and data_list[0].edge_index is not None
    ):
        try:
            n_neighbors = []
            for i, data in enumerate(data_list):
                n_index = data.edge_index[1, :]
                n_neighbors.append(n_index.shape[0])
            batch.neighbors = torch.tensor(n_neighbors)
        except NotImplementedError:
            logging.warning(
                "LMDB does not contain edge index information, set otf_graph=True"
            )

    return batch
