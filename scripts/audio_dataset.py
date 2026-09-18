"""
Step 2: PyTorch Dataset that reads the manifest from step 1 and turns each
10s audio window into a log-mel spectrogram on the fly.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torchaudio
from torch.utils.data import Dataset

DATASET_DIR = Path(__file__).resolve().parent.parent

SAMPLE_RATE = 4000  # native rate of the APSAA recordings
N_MELS = 64
N_FFT = 256
HOP_LENGTH = 64


class ApneaWindowDataset(Dataset):
    """One item = one 10s audio window -> (log-mel spectrogram, label)."""

    def __init__(self, manifest_csv: Path):
        self.df = pd.read_csv(manifest_csv)
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=SAMPLE_RATE,
            n_fft=N_FFT,
            hop_length=HOP_LENGTH,
            n_mels=N_MELS,
        )
        self.to_db = torchaudio.transforms.AmplitudeToDB()

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int):
        row = self.df.iloc[idx]
        wav_path = DATASET_DIR / row["wav_path"]

        frame_offset = int(round(row["start_sec"] * SAMPLE_RATE))
        num_frames = int(round((row["end_sec"] - row["start_sec"]) * SAMPLE_RATE))

        audio, sr = sf.read(
            str(wav_path), start=frame_offset, frames=num_frames,
            dtype="float32", always_2d=True,
        )
        waveform = torch.from_numpy(audio.T)  # (channels, samples)
        if sr != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)

        # pad/truncate in case the last window in a file is short
        target_len = num_frames
        if waveform.shape[1] < target_len:
            waveform = torch.nn.functional.pad(waveform, (0, target_len - waveform.shape[1]))
        elif waveform.shape[1] > target_len:
            waveform = waveform[:, :target_len]

        spec = self.to_db(self.mel(waveform))  # shape: (1, n_mels, time)
        spec = (spec - spec.mean()) / (spec.std() + 1e-6)  # per-sample normalize

        label = torch.tensor(row["label"], dtype=torch.float32)
        return spec, label


if __name__ == "__main__":
    ds = ApneaWindowDataset(DATASET_DIR / "prepared_dataset" / "manifest_train.csv")
    print(f"Dataset size: {len(ds)}")
    spec, label = ds[0]
    print(f"Spectrogram shape: {tuple(spec.shape)}, label: {label.item()}")
    spec, label = ds[100]
    print(f"Spectrogram shape: {tuple(spec.shape)}, label: {label.item()}")
