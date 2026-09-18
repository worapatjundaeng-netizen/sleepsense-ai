"""
Step 1: Build a labeled manifest for sleep-apnea audio classification.

Reads each subject's annotation CSV, slices the full-night recording into
fixed-length windows, and labels each window as apnea / non-apnea based on
how much it overlaps annotated apnea-type events. No audio is duplicated to
disk here -- the manifest just records (subject, start_sec, end_sec, label,
wav_path); actual audio samples get read on the fly during training (step 2).

Usage:
    python scripts/prepare_dataset.py
"""

import random
import sys
import wave
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Config ---------------------------------------------------------------

DATASET_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = DATASET_DIR / "prepared_dataset"

WINDOW_SEC = 10.0
HOP_SEC = 10.0  # non-overlapping windows
POSITIVE_OVERLAP_RATIO = 0.3  # window counts as "apnea" if >=30% of it overlaps an apnea event

APNEA_EVENT_NAMES = {"Obstructive Apnea", "Central Apnea", "Mixed Apnea", "Hypopnea"}
ALL_EVENT_NAMES = APNEA_EVENT_NAMES | {"Snore", "Desaturation", "No Effort"}

VAL_SUBJECT_RATIO = 0.2
RANDOM_SEED = 42

SUBJECT_DIR_PATTERN = "[0-9]" * 8 + "?"  # e.g. 20210919A


# --- Helpers ---------------------------------------------------------------

def parse_hhmmss(value: str) -> float:
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def overlap_sec(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def find_subjects(dataset_dir: Path) -> list[Path]:
    subjects = []
    for entry in sorted(dataset_dir.iterdir()):
        if not entry.is_dir():
            continue
        wav_path = entry / f"{entry.name}.wav"
        ann_path = entry / f"{entry.name}_Annotations.csv"
        if wav_path.exists() and ann_path.exists():
            subjects.append(entry)
    return subjects


def load_events(ann_path: Path) -> pd.DataFrame:
    df = pd.read_csv(ann_path)
    unknown = set(df["Event_Name"].unique()) - ALL_EVENT_NAMES
    if unknown:
        raise ValueError(f"{ann_path}: unexpected event names {unknown}")
    df["start_sec"] = df["Start_Time"].apply(parse_hhmmss)
    df["end_sec"] = df["start_sec"] + df["Duration"].astype(float)
    return df


def build_windows_for_subject(subject_dir: Path) -> list[dict]:
    subject = subject_dir.name
    wav_path = subject_dir / f"{subject}.wav"
    ann_path = subject_dir / f"{subject}_Annotations.csv"

    duration = wav_duration_sec(wav_path)
    events = load_events(ann_path)

    apnea_intervals = merge_intervals(
        list(
            zip(
                events.loc[events["Event_Name"].isin(APNEA_EVENT_NAMES), "start_sec"],
                events.loc[events["Event_Name"].isin(APNEA_EVENT_NAMES), "end_sec"],
            )
        )
    )
    event_tuples = list(zip(events["Event_Name"], events["start_sec"], events["end_sec"]))

    rows = []
    n_windows = int((duration - WINDOW_SEC) // HOP_SEC) + 1
    for i in range(max(n_windows, 0)):
        win_start = i * HOP_SEC
        win_end = win_start + WINDOW_SEC

        apnea_overlap = sum(overlap_sec(win_start, win_end, s, e) for s, e in apnea_intervals)
        label = int(apnea_overlap / WINDOW_SEC >= POSITIVE_OVERLAP_RATIO)

        overlapping_events = sorted(
            {name for name, s, e in event_tuples if overlap_sec(win_start, win_end, s, e) > 0}
        )

        rows.append(
            {
                "subject": subject,
                "wav_path": str(wav_path.relative_to(DATASET_DIR)),
                "start_sec": round(win_start, 2),
                "end_sec": round(win_end, 2),
                "label": label,
                "apnea_overlap_sec": round(apnea_overlap, 2),
                "events": "|".join(overlapping_events),
            }
        )
    return rows


def split_subjects(subjects: list[str]) -> tuple[set[str], set[str]]:
    rng = random.Random(RANDOM_SEED)
    shuffled = subjects[:]
    rng.shuffle(shuffled)
    n_val = max(1, round(len(shuffled) * VAL_SUBJECT_RATIO))
    val = set(shuffled[:n_val])
    train = set(shuffled[n_val:])
    return train, val


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    subject_dirs = find_subjects(DATASET_DIR)
    print(f"Found {len(subject_dirs)} subjects")

    all_rows: list[dict] = []
    for subject_dir in subject_dirs:
        rows = build_windows_for_subject(subject_dir)
        all_rows.extend(rows)
        n_pos = sum(r["label"] for r in rows)
        print(f"  {subject_dir.name}: {len(rows)} windows, {n_pos} positive ({n_pos / max(len(rows), 1):.1%})")

    manifest = pd.DataFrame(all_rows)
    manifest.to_csv(OUTPUT_DIR / "manifest_full.csv", index=False)

    subjects = sorted(manifest["subject"].unique())
    train_subjects, val_subjects = split_subjects(subjects)

    train_df = manifest[manifest["subject"].isin(train_subjects)]
    val_df = manifest[manifest["subject"].isin(val_subjects)]
    train_df.to_csv(OUTPUT_DIR / "manifest_train.csv", index=False)
    val_df.to_csv(OUTPUT_DIR / "manifest_val.csv", index=False)

    print("\n--- Summary ---")
    print(f"Total windows: {len(manifest)}  (positive: {manifest['label'].sum()}, "
          f"{manifest['label'].mean():.1%})")
    print(f"Train subjects: {len(train_subjects)}  windows: {len(train_df)}  "
          f"positive: {train_df['label'].mean():.1%}")
    print(f"Val subjects:   {len(val_subjects)}  windows: {len(val_df)}  "
          f"positive: {val_df['label'].mean():.1%}")
    print(f"\nWritten to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
