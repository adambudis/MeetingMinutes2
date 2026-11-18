"""Port of python/services/diarization_service.py (pyannote speaker diarization)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from app.services.device import get_device
from app.services.interfaces import ProgressCallback

if TYPE_CHECKING:
    from pyannote.audio import Pipeline

SpeakerTurn = tuple[float, float, str]

PIPELINE_NAME = "pyannote/speaker-diarization-3.1"


def _peak_normalize(waveform: np.ndarray) -> np.ndarray:
    """Peak-normalize to 0.9 so pyannote's VAD detects speech in quiet mic recordings."""
    peak = np.abs(waveform).max()
    if peak < 1e-6:
        return waveform
    return waveform * (0.9 / peak)


class DiarizationService:
    def __init__(self, hf_token: str | None = None) -> None:
        self._hf_token = hf_token
        self._pipeline: Pipeline | None = None

    def load(self, on_progress: ProgressCallback) -> Pipeline:
        if self._pipeline is None:
            import torch
            from pyannote.audio import Pipeline

            on_progress("Načítám pyannote diarizační model...")
            pipeline = Pipeline.from_pretrained(PIPELINE_NAME, token=self._hf_token)
            if pipeline is None:
                raise RuntimeError(f"Diarizační model {PIPELINE_NAME} nelze načíst (chybí v cache?)")
            pipeline.to(torch.device(get_device()))
            self._pipeline = pipeline
        return self._pipeline

    def get_speaker_turns(self, audio_path: str, on_progress: ProgressCallback) -> list[SpeakerTurn]:
        import soundfile as sf
        import torch

        pipeline = self.load(on_progress)

        on_progress("Diarizuji audio...")
        waveform, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        waveform = _peak_normalize(waveform)
        result = pipeline({"waveform": torch.tensor(waveform.T), "sample_rate": sr})
        annotation = getattr(result, "speaker_diarization", result)

        raw_turns = [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]

        if not raw_turns:
            duration = waveform.shape[0] / sr
            on_progress("Diarizace nenalezla žádné úseky — přepisuji celý soubor jako jednoho mluvčího.")
            return [(0.0, duration, "SPEAKER_00")]

        all_speakers = sorted({spk for _, _, spk in raw_turns})
        speaker_map = {spk: f"SPEAKER_{i:02d}" for i, spk in enumerate(all_speakers)}

        on_progress(f"Pyannote detekoval {len(all_speakers)} mluvčích v {len(raw_turns)} úsecích.")
        return [(s, e, speaker_map[spk]) for s, e, spk in raw_turns]
