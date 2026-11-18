"""Port of python/services/transcription_service.py (NeMo Canary / Parakeet + pyannote diarization).

Models are loaded once and cached in memory. All methods are blocking and must run on the
single model worker thread (see ModelRunner) so GPU usage is serialised.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.schemas import TranscriptSegment
from app.services.device import get_device
from app.services.diarization import DiarizationService, SpeakerTurn
from app.services.interfaces import ProgressCallback

if TYPE_CHECKING:
    import nemo.collections.asr as nemo_asr

SAMPLE_RATE = 16000
MIN_DUR = 0.15
MERGE_GAP_S = 1.5


def merge_short_turns(turns: list[SpeakerTurn], min_dur: float = MIN_DUR) -> list[SpeakerTurn]:
    """Fold turns shorter than `min_dur` into the preceding turn instead of dropping them."""
    merged: list[SpeakerTurn] = []
    for s, e, spk in turns:
        if (e - s) >= min_dur:
            merged.append((s, e, spk))
        elif merged:
            ps, _, pspk = merged[-1]
            merged[-1] = (ps, e, pspk)
    return merged


def merge_adjacent_turns(turns: list[SpeakerTurn], max_gap: float = MERGE_GAP_S) -> list[SpeakerTurn]:
    """Coalesce consecutive turns of the same speaker separated by a gap below `max_gap`."""
    coalesced: list[SpeakerTurn] = []
    for s, e, spk in turns:
        if coalesced:
            ps, pe, pspk = coalesced[-1]
            if pspk == spk and s >= pe and (s - pe) < max_gap:
                coalesced[-1] = (ps, e, pspk)
                continue
        coalesced.append((s, e, spk))
    return coalesced


class NemoTranscriptionService:
    def __init__(self, canary_path: Path, parakeet_path: Path, hf_token: str | None = None) -> None:
        self._diarizer = DiarizationService(hf_token)
        self._model_paths = {"canary": canary_path, "parakeet": parakeet_path}
        self._model_cache: dict[str, nemo_asr.models.ASRModel] = {}
        self._backends: dict[str, Callable[[str | None], dict[str, Any]]] = {
            "canary": lambda lang: {"source_lang": lang or "cs", "target_lang": lang or "cs"},
            "parakeet": lambda _lang: {},
        }

    @property
    def available_models(self) -> list[str]:
        return list(self._backends)

    def model_files(self) -> dict[str, bool]:
        return {name: path.exists() for name, path in self._model_paths.items()}

    def _load_model(self, name: str, on_progress: ProgressCallback) -> nemo_asr.models.ASRModel:
        if name not in self._model_cache:
            import nemo.collections.asr as nemo_asr

            path = self._model_paths[name]
            if not path.exists():
                raise FileNotFoundError(f"{name} model nenalezen: {path}")
            on_progress(f"Načítám {name} model z lokálního souboru ({path.name})...")
            with contextlib.redirect_stdout(sys.stderr):
                model = nemo_asr.models.ASRModel.restore_from(str(path))
            if get_device() == "cuda":
                model = model.cuda()
            model.eval()
            self._model_cache[name] = model
        return self._model_cache[name]

    def warmup(self, models: list[str], on_progress: ProgressCallback) -> None:
        self._diarizer.load(on_progress)
        files = self.model_files()
        for name in models:
            if files.get(name):
                self._load_model(name, on_progress)
            else:
                on_progress(f"Warmup: model '{name}' není k dispozici, přeskakuji.")

    def transcribe(
        self,
        audio_path: str,
        model: str,
        language: str | None,
        on_progress: ProgressCallback,
    ) -> list[TranscriptSegment]:
        if model not in self._backends:
            raise ValueError(f"Unknown backend '{model}'. Available: {list(self._backends)}")
        asr_model = self._load_model(model, on_progress)
        transcribe_kwargs = self._backends[model](language)

        import librosa
        import soundfile as sf

        turns = self._diarizer.get_speaker_turns(audio_path, on_progress)
        if not turns:
            return []

        y_full, sr_native = sf.read(audio_path, dtype="float32", always_2d=False)
        if y_full.ndim > 1:
            y_full = y_full.mean(axis=1)
        if sr_native != SAMPLE_RATE:
            y_full = librosa.resample(y_full, orig_sr=sr_native, target_sr=SAMPLE_RATE)

        coalesced = merge_adjacent_turns(merge_short_turns(turns))
        if not coalesced:
            return []

        with tempfile.TemporaryDirectory(prefix="mm-seg-") as tmp_dir:
            seg_files: list[str] = []
            for i, (s, e, _) in enumerate(coalesced):
                path = os.path.join(tmp_dir, f"{i:05d}.wav")
                sf.write(path, y_full[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)], SAMPLE_RATE)
                seg_files.append(path)

            on_progress(f"Přepisuji {len(coalesced)} segmentů s {model}...")
            with contextlib.redirect_stdout(sys.stderr):
                hypotheses = asr_model.transcribe(seg_files, **transcribe_kwargs)

        result: list[TranscriptSegment] = []
        for (s, e, spk), hyp in zip(coalesced, hypotheses, strict=False):
            text = (hyp.text if hasattr(hyp, "text") else str(hyp)).strip()
            if text:
                result.append(TranscriptSegment(start=s, end=e, speaker=spk, text=text))

        on_progress(f"Nalezeno {len(result)} segmentů.")
        return result
