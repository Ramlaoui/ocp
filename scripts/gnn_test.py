"""
Copyright (c) Facebook, Inc. and its affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""
import sys
import warnings
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ocpmodels.common.utils import make_script_trainer
from ocpmodels.trainers import EnergyTrainer

if __name__ == "__main__":

    config = {}
    # Customize args
    # config["model"] = {"energy_head": "weighted-av-initial-embeds"}
    # config["model"] = {"graph_rewiring": "one-supernode-per-graph"}
    # config["model"]= {"phys_embeds": True}
    config["graph_rewiring"] = "remove-tag-0"
    config["frame_averaging"] = "2d"
    config["fa_frames"] = "random"
    config["test_ri"] = True
    config["optim"] = {"max_epochs": 0}
    config["model"] = {"use_pbc": True}

    checkpoint_path = None
    # "checkpoints/2022-04-28-11-42-56-dimenetplusplus/" + "best_checkpoint.pt"

    str_args = sys.argv[1:]
    if all("--config-yml" not in arg for arg in str_args):
        str_args.append("--is_debug")
        # str_args.append("--config-yml=configs/is2re/10k/dimenet_plus_plus/new_dpp.yml")
        # str_args.append("--config-yml=configs/is2re/10k/schnet/new_schnet.yml")
        # str_args.append("--config-yml=configs/is2re/10k/forcenet/new_forcenet.yml")
        str_args.append("--config-yml=configs/is2re/10k/sfarinet/sfarinet.yml")
        # str_args.append("--config-yml=configs/is2re/10k/fanet/fanet.yml")
        warnings.warn(
            "No model / mode is given; chosen as default" + f"Using: {str_args[-1]}"
        )

    trainer: EnergyTrainer = make_script_trainer(str_args=str_args, overrides=config)

    trainer.train()

    if checkpoint_path:

        trainer.load_checkpoint(
            checkpoint_path="checkpoints/2022-04-28-11-42-56-dimenetplusplus/"
            + "best_checkpoint.pt"
        )

        predictions = trainer.predict(
            trainer.val_loader, results_file="is2re_results", disable_tqdm=False
        )
