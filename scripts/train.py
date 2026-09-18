"""
Step 2: train the CNN on the manifests produced in step 1.

Usage:
    python scripts/train.py --epochs 5
    python scripts/train.py --epochs 1 --limit 500   # quick smoke test
"""

import argparse
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Subset

from audio_dataset import ApneaWindowDataset
from model import ApneaCNN

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET_DIR = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = DATASET_DIR / "prepared_dataset"


def evaluate(model, loader, device):
    model.eval()
    tp = fp = fn = tn = 0
    total_loss = 0.0
    loss_fn = torch.nn.BCEWithLogitsLoss()
    with torch.no_grad():
        for specs, labels in loader:
            specs, labels = specs.to(device), labels.to(device)
            logits = model(specs)
            total_loss += loss_fn(logits, labels).item() * len(labels)
            preds = (torch.sigmoid(logits) >= 0.5).float()
            tp += ((preds == 1) & (labels == 1)).sum().item()
            fp += ((preds == 1) & (labels == 0)).sum().item()
            fn += ((preds == 0) & (labels == 1)).sum().item()
            tn += ((preds == 0) & (labels == 0)).sum().item()

    n = tp + fp + fn + tn
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "loss": total_loss / n if n else 0.0,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--limit", type=int, default=None, help="use only first N rows of each manifest, for a quick smoke test")
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true", help="load prepared_dataset/best_model.pt before training instead of starting from random weights")
    parser.add_argument("--lr-step-size", type=int, default=3, help="halve the learning rate every N epochs")
    parser.add_argument("--lr-gamma", type=float, default=0.5)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    train_ds = ApneaWindowDataset(DATASET_DIR / "prepared_dataset" / "manifest_train.csv")
    val_ds = ApneaWindowDataset(DATASET_DIR / "prepared_dataset" / "manifest_val.csv")

    if args.limit:
        train_ds = Subset(train_ds, range(min(args.limit, len(train_ds))))
        val_ds = Subset(val_ds, range(min(args.limit, len(val_ds))))

    persistent = args.num_workers > 0
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
        persistent_workers=persistent, prefetch_factor=4 if persistent else None,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
        persistent_workers=persistent, prefetch_factor=4 if persistent else None,
    )

    # class imbalance: weight positives up by neg/pos ratio from the training manifest
    labels = train_ds.dataset.df["label"] if isinstance(train_ds, Subset) else train_ds.df["label"]
    if args.limit:
        labels = labels.iloc[: args.limit]
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    pos_weight = torch.tensor(n_neg / max(n_pos, 1), dtype=torch.float32, device=device)
    print(f"Train windows: {len(labels)}  positive: {n_pos} ({n_pos/len(labels):.1%})  pos_weight={pos_weight.item():.2f}")

    model = ApneaCNN().to(device)
    checkpoint_path = CHECKPOINT_DIR / "best_model.pt"
    if args.resume and checkpoint_path.exists():
        model.load_state_dict(torch.load(checkpoint_path, map_location=device))
        print(f"Resumed weights from {checkpoint_path}")
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=args.lr_step_size, gamma=args.lr_gamma)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    best_f1 = -1.0
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    if checkpoint_path.exists() and not args.resume:
        backup_path = CHECKPOINT_DIR / "best_model_prev.pt"
        checkpoint_path.rename(backup_path)
        print(f"Backed up previous checkpoint to {backup_path}")

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for i, (specs, labels) in enumerate(train_loader):
            specs, labels = specs.to(device), labels.to(device)
            optimizer.zero_grad()
            logits = model(specs)
            loss = loss_fn(logits, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * len(labels)
            if (i + 1) % 50 == 0:
                print(f"  epoch {epoch} batch {i+1}/{len(train_loader)} loss {loss.item():.4f}")

        train_loss = running_loss / len(train_loader.dataset)
        metrics = evaluate(model, val_loader, device)
        print(
            f"Epoch {epoch}: lr={optimizer.param_groups[0]['lr']:.2e}  train_loss={train_loss:.4f}  "
            f"val_loss={metrics['loss']:.4f}  val_acc={metrics['accuracy']:.3f}  "
            f"val_precision={metrics['precision']:.3f}  val_recall={metrics['recall']:.3f}  "
            f"val_f1={metrics['f1']:.3f}"
        )
        scheduler.step()

        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            torch.save(model.state_dict(), CHECKPOINT_DIR / "best_model.pt")
            print(f"  -> saved new best model (f1={best_f1:.3f})")

    print(f"\nDone. Best val F1: {best_f1:.3f}. Checkpoint: {CHECKPOINT_DIR / 'best_model.pt'}")


if __name__ == "__main__":
    main()
