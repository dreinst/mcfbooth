"""QR Generator (arsitektur-sistem-photobooth.md §3.4).

Modul kecil dan sengaja dibuat sesederhana mungkin: terima 1 string link,
keluarkan 1 file gambar QR. Karena input-nya cuma "link", nanti kalau mau
ganti dari link Drive mentah ke gallery page custom, cukup ganti sumber
link-nya di Session Manager — modul ini sendiri tidak perlu disentuh.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_H

log = logging.getLogger(__name__)

AKAR = Path(__file__).resolve().parent.parent
QR_DIR = Path(os.environ.get("QR_CODES", AKAR / "qr_codes"))


def siapkan() -> None:
    """Pastikan folder QR ada."""
    QR_DIR.mkdir(parents=True, exist_ok=True)


def buat_qr(link: str, session_code: str) -> str | None:
    """Generate QR code dari link. Simpan di qr_codes/<session_code>.png.

    Returns path file QR atau None kalau gagal.
    """
    try:
        siapkan()
        path = QR_DIR / f"{session_code}.png"

        qr = qrcode.QRCode(
            version=None,  # auto-detect ukuran
            error_correction=ERROR_CORRECT_H,  # high correction — terbaca walau agak kotor
            box_size=12,
            border=4,
        )
        qr.add_data(link)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(path))

        log.info("QR dibuat: %s → %s", session_code, path)
        return str(path)

    except Exception as e:
        log.error("Gagal buat QR untuk '%s': %s", session_code, e)
        return None
