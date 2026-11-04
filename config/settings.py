"""Percorsi locali indipendenti dal checkout e dal sistema operativo."""
import os
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("LOTTOPREDICT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "LottoPredictAI"
