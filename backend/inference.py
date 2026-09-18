"""
Step 3: run the trained CNN over a full-night audio file.

Slices the uploaded recording into the same 10s non-overlapping windows used
during training, scores each one, then merges consecutive apnea-positive
windows into "events" so the result reads like a clinical report instead of
a raw list of per-window probabilities.
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from model import ApneaCNN  # noqa: E402

SAMPLE_RATE = 4000
WINDOW_SEC = 10.0
N_MELS = 64
N_FFT = 256
HOP_LENGTH = 64
DEFAULT_THRESHOLD = 0.5
MIN_EVENT_DURATION_SEC = 20.0  # drop single-window blips (likely noise, not a real event)


class ApneaAnalyzer:
    def __init__(self, checkpoint_path: Path, device: str = "cpu"):
        self.device = torch.device(device)
        self.model = ApneaCNN().to(self.device)
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=SAMPLE_RATE, n_fft=N_FFT, hop_length=HOP_LENGTH, n_mels=N_MELS
        )
        self.to_db = torchaudio.transforms.AmplitudeToDB()

    def _load_audio(self, path: str) -> np.ndarray:
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)  # downmix to mono
        if sr != SAMPLE_RATE:
            waveform = torch.from_numpy(audio).unsqueeze(0)
            waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)
            audio = waveform.squeeze(0).numpy()
        return audio

    def _score_window(self, chunk: np.ndarray) -> float:
        waveform = torch.from_numpy(chunk).unsqueeze(0)
        spec = self.to_db(self.mel(waveform))
        spec = (spec - spec.mean()) / (spec.std() + 1e-6)
        with torch.no_grad():
            logit = self.model(spec.unsqueeze(0).to(self.device))
        return torch.sigmoid(logit).item()

    def analyze_file(self, path: str, threshold: float = DEFAULT_THRESHOLD) -> dict:
        audio = self._load_audio(path)
        window_samples = int(WINDOW_SEC * SAMPLE_RATE)
        n_windows = len(audio) // window_samples
        duration_sec = len(audio) / SAMPLE_RATE

        windows = []
        for i in range(n_windows):
            chunk = audio[i * window_samples: (i + 1) * window_samples]
            prob = self._score_window(chunk)
            windows.append({
                "start_sec": round(i * WINDOW_SEC, 1),
                "end_sec": round((i + 1) * WINDOW_SEC, 1),
                "probability": round(prob, 4),
                "is_apnea": prob >= threshold,
            })

        events = self._merge_into_events(windows)
        hours = duration_sec / 3600 if duration_sec > 0 else 0
        apnea_windows = [w for w in windows if w["is_apnea"]]

        summary = {
            "duration_sec": round(duration_sec, 1),
            "duration_hms": self._format_hms(duration_sec),
            "total_windows": n_windows,
            "apnea_windows": len(apnea_windows),
            "apnea_time_ratio": round(len(apnea_windows) / n_windows, 4) if n_windows else 0.0,
            "num_events": len(events),
            "events_per_hour": round(len(events) / hours, 2) if hours > 0 else 0.0,
        }
        return {"summary": summary, "events": events, "windows": windows}

    @staticmethod
    def _merge_into_events(windows: list[dict]) -> list[dict]:
        events = []
        current = None
        for w in windows:
            if w["is_apnea"]:
                if current is None:
                    current = {"start_sec": w["start_sec"], "end_sec": w["end_sec"], "probs": [w["probability"]]}
                else:
                    current["end_sec"] = w["end_sec"]
                    current["probs"].append(w["probability"])
            else:
                if current is not None:
                    events.append(current)
                    current = None
        if current is not None:
            events.append(current)

        return [
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "duration_sec": round(e["end_sec"] - e["start_sec"], 1),
                "avg_probability": round(sum(e["probs"]) / len(e["probs"]), 4),
            }
            for e in events
            if (e["end_sec"] - e["start_sec"]) >= MIN_EVENT_DURATION_SEC
        ]

    @staticmethod
    def _format_hms(seconds: float) -> str:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


if __name__ == "__main__":
    import json

    checkpoint = Path(__file__).resolve().parent.parent / "prepared_dataset" / "best_model.pt"
    test_wav = sys.argv[1] if len(sys.argv) > 1 else None
    if not test_wav:
        raise SystemExit("usage: python inference.py <path-to-wav>")

    analyzer = ApneaAnalyzer(checkpoint)
    result = analyzer.analyze_file(test_wav)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print(f"\nFirst 5 events: {json.dumps(result['events'][:5], indent=2, ensure_ascii=False)}")
