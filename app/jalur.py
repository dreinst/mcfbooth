"""Path dan konfigurasi bersama.

Semua path dari `.env` diselesaikan relatif terhadap akar repo, bukan terhadap
folder tempat perintah dijalankan — pintasan Windows tanpa "Start in" tidak
boleh membuat `sessions.db` kosong di tempat lain.
"""

from __future__ import annotations

import os
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent


def path_env(nama: str, bawaan: Path) -> Path:
    nilai = os.environ.get(nama, "").strip()
    if not nilai:
        return bawaan.resolve()
    p = Path(nilai).expanduser()
    if not p.is_absolute():
        p = AKAR / p
    return p.resolve()


def env_bool(nama: str, bawaan: bool = False) -> bool:
    nilai = os.environ.get(nama)
    if nilai is None:
        return bawaan
    return nilai.strip().lower() in ("1", "true", "ya", "yes", "on")


def env_float(nama: str, bawaan: float) -> float:
    try:
        return float(os.environ.get(nama, bawaan))
    except (TypeError, ValueError):
        return bawaan


def env_int(nama: str, bawaan: int) -> int:
    try:
        return int(os.environ.get(nama, bawaan))
    except (TypeError, ValueError):
        return bawaan
