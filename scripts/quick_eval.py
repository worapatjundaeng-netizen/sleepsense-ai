"""Evaluate the current best checkpoint on a slice of the validation set (for progress reporting)."""

import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Subset

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from audio_dataset import ApneaWindowDataset
from model import ApneaCNN
from train import evaluate

DATASET_DIR = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    ds = ApneaWindowDataset(DATASET_DIR / "prepared_dataset" / "manifest_val.csv")
    sub = Subset(ds, range(min(limit, len(ds))))
    loader = DataLoader(sub, batch_size=32, num_workers=2)

    model = ApneaCNN()
    model.load_state_dict(torch.load(DATASET_DIR / "prepared_dataset" / "best_model.pt", map_location="cpu"))

    metrics = evaluate(model, loader, torch.device("cpu"))
    print(f"Evaluated on {len(sub)} validation windows:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.3f}")
