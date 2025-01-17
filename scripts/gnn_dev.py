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
from ocpmodels.trainers import SingleTrainer

if __name__ == "__main__":
    config = {}
    # Customize args
    # config["optim"]["eval_every"] = 1
    # config["grad_fine_tune"] = True
    # config["model"]["cosine_sim"] = 3
    # config["optim"]["epoch_fine_tune"] = 3
    config["fa_frames"] = "random"  # "random"
    config["fa_method"] = "random"  # "random"
    config["frame_averaging"] = "2D"
    config["graph_rewiring"] = "remove-tag-0"
    config["model"] = {"use_pbc": True}
    config["model"]["complex_mp"] = True
    config["model"]["edge_embed_type"] = "all_rij"
    config["model"]["graph_norm"] = True
    config["model"]["mp_type"] = "base"
    config["model"]["regress_forces"] = "direct_with_gradient_target"
    config["model"]["skip_co"] = "concat"  # add, concat,
    config["optim"] = {"max_epochs": 1}
    config["optim"]["batch_size"] = 6
    config["optim"]["eval_batch_size"] = 6
    config["test_ri"] = True

    checkpoint_path = None
    # "checkpoints/2022-04-28-11-42-56-dimenetplusplus/" + "best_checkpoint.pt"

    str_args = sys.argv[1:]
    if all("config" not in arg for arg in str_args):
        str_args.append("--is_debug")
        # str_args.append("--config=faenet-is2re-all")
        str_args.append("--config=faenet-is2re-10k")
        # str_args.append("--silent=0")
        warnings.warn(
            "No model / mode is given; chosen as default" + f"Using: {str_args[-1]}"
        )

    trainer: SingleTrainer = make_script_trainer(str_args=str_args, overrides=config)

    trainer.train()

    if checkpoint_path:
        trainer.load_checkpoint(
            checkpoint_path="checkpoints/2022-04-28-11-42-56-dimenetplusplus/"
            + "best_checkpoint.pt"
        )

        predictions = trainer.predict(
            trainer.val_loader, results_file="is2re_results", disable_tqdm=False
        )
