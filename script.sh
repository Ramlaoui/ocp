#!/bin/bash
#SBATCH --job-name=test
#SBATCH --ntasks=1
#SBATCH --time=20:00:00
#SBATCH --mem=32GB
#SBATCH --gres=gpu:1
#SBATCH --output=output-job.txt

module load anaconda/3
conda activate ocp
python main.py $@
