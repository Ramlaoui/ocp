"""
Copyright (c) Facebook, Inc. and its affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.



Utilities to interface OCP models/trainers with the Atomic Simulation
Environment (ASE)
"""
import copy
import logging

import torch
from ase import Atoms
from ase.calculators.calculator import Calculator
from ase.calculators.singlepoint import SinglePointCalculator as sp
from ase.constraints import FixAtoms

from ocpmodels.common.registry import registry
from ocpmodels.common.utils import setup_imports, setup_logging, load_config
from ocpmodels.datasets import data_list_collater
from ocpmodels.preprocessing import AtomsToGraphs


def batch_to_atoms(batch):
    n_systems = batch.neighbors.shape[0]
    natoms = batch.natoms.tolist()
    numbers = torch.split(batch.atomic_numbers, natoms)
    fixed = torch.split(batch.fixed, natoms)
    forces = torch.split(batch.force, natoms)
    positions = torch.split(batch.pos, natoms)
    tags = torch.split(batch.tags, natoms)
    cells = batch.cell
    energies = batch.y.tolist()

    atoms_objects = []
    for idx in range(n_systems):
        atoms = Atoms(
            numbers=numbers[idx].tolist(),
            positions=positions[idx].cpu().detach().numpy(),
            tags=tags[idx].tolist(),
            cell=cells[idx].cpu().detach().numpy(),
            constraint=FixAtoms(mask=fixed[idx].tolist()),
            pbc=[True, True, True],
        )
        calc = sp(
            atoms=atoms,
            energy=energies[idx],
            forces=forces[idx].cpu().detach().numpy(),
        )
        atoms.set_calculator(calc)
        atoms_objects.append(atoms)

    return atoms_objects


class OCPCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, config=None, checkpoint=None, cutoff=6, max_neighbors=50):
        """
        OCP-ASE Calculator

        Args:
            config (str):
                "{model}-{task}-{split}" config string or trainer config dictionary.
            checkpoint (str):
                Path to trained checkpoint.
            cutoff (int):
                Cutoff radius to be used for data preprocessing.
            max_neighbors (int):
                Maximum amount of neighbors to store for a given atom.
        """
        setup_imports()
        setup_logging()
        Calculator.__init__(self)

        # Either the config path or the checkpoint path needs to be provided
        assert config or checkpoint is not None

        if config is not None:
            if isinstance(config, str):
                trainer_config = load_config(config)
            else:
                trainer_config = config
            # Only keeps the train data that might have normalizer values
            trainer_config["dataset"] = trainer_config["dataset"][0]
        else:
            # Loads the trainer_config from the checkpoint directly
            trainer_config = torch.load(
                checkpoint,
                map_location=torch.device("cpu"),
            )["config"]

            # Load the trainer based on the dataset used
            if trainer_config["task"]["dataset"] == "trajectory_lmdb":
                trainer_config["trainer"] = "forces"
            else:
                trainer_config["trainer"] = "energy"

            trainer_config["model"]["name"] = trainer_config.pop("model_name")

        # Calculate the edge indices on the fly
        trainer_config["model"]["otf_graph"] = True

        # Save trainer_config so obj can be transported over network (pkl)
        self.trainer_config = copy.deepcopy(trainer_config)
        self.trainer_config["checkpoint"] = checkpoint

        if "normalizer" not in trainer_config:
            del trainer_config["dataset"]["src"]
            trainer_config["normalizer"] = trainer_config["dataset"]

        self.trainer = registry.get_trainer_class(trainer_config["trainer"])(
            **trainer_config,
            dataset=None,
            local_rank=trainer_config.get("local_rank", 0),
            is_debug=trainer_config.get("is_debug", True),
            cpu=True,
        )

        if checkpoint is not None:
            self.load_checkpoint(checkpoint)

        self.a2g = AtomsToGraphs(
            max_neigh=max_neighbors,
            radius=cutoff,
            r_energy=False,
            r_forces=False,
            r_distances=False,
            r_edges=False,
        )

    def load_checkpoint(self, checkpoint_path):
        """
        Load existing trained model

        Args:
            checkpoint_path: string
                Path to trained model
        """
        try:
            self.trainer.load_checkpoint(checkpoint_path)
        except NotImplementedError:
            logging.warning("Unable to load checkpoint!")

    def calculate(self, atoms, properties, system_changes):
        Calculator.calculate(self, atoms, properties, system_changes)
        data_object = self.a2g.convert(atoms)
        batch = data_list_collater([data_object], otf_graph=True)

        predictions = self.trainer.predict(batch, per_image=False, disable_tqdm=True)
        if self.trainer.name == "s2ef":
            self.results["energy"] = predictions["energy"].item()
            self.results["forces"] = predictions["forces"].cpu().numpy()

        elif self.trainer.name == "is2re":
            self.results["energy"] = predictions["energy"].item()
