"""Audio normalisation via ffmpeg (replaces NAudio ConvertToWav in the WPF client)."""

import subprocess
from pathlib import Path

SAMPLE_RATE = 16000
ALLOWED_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".oga", ".opus", ".flac", ".aac"})


class AudioConversionError(Exception):
    pass


def convert_to_wav(input_path: Path, output_path: Path) -> None:
    """Convert any ffmpeg-readable audio/video file to 16 kHz mono 16-bit PCM WAV."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16",
        str(output_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as ex:
        raise AudioConversionError("ffmpeg není nainstalován") from ex
    if proc.returncode != 0:
        raise AudioConversionError(f"Konverze audia selhala: {proc.stderr.strip()[-500:]}")
