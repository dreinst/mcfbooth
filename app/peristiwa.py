"""Server-Sent Events — aliran peristiwa ke jendela tamu dan operator.

Jendela tamu berganti keadaan tanpa polling; jendela operator ikut
memperbarui angkanya. Koneksi SSE dari /tamu yang masih hidup dipakai
untuk mendeteksi apakah jendela tamu terbuka (design.md §8).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

# Kumpulan antrean SSE yang sedang aktif.
_pelanggan: list[asyncio.Queue] = []
_pelanggan_tamu: list[asyncio.Queue] = []


def daftar() -> asyncio.Queue:
    """Daftarkan pelanggan SSE baru (operator). Returns queue."""
    q: asyncio.Queue = asyncio.Queue()
    _pelanggan.append(q)
    log.debug("Pelanggan operator terdaftar — total: %d", len(_pelanggan))
    return q


def hapus(q: asyncio.Queue) -> None:
    """Hapus pelanggan SSE."""
    if q in _pelanggan:
        _pelanggan.remove(q)
    log.debug("Pelanggan operator dihapus — total: %d", len(_pelanggan))


def daftar_tamu() -> asyncio.Queue:
    """Daftarkan pelanggan SSE baru (layar tamu). Returns queue."""
    q: asyncio.Queue = asyncio.Queue()
    _pelanggan_tamu.append(q)
    log.debug("Pelanggan tamu terdaftar — total: %d", len(_pelanggan_tamu))
    return q


def hapus_tamu(q: asyncio.Queue) -> None:
    """Hapus pelanggan SSE tamu."""
    if q in _pelanggan_tamu:
        _pelanggan_tamu.remove(q)
    log.debug("Pelanggan tamu dihapus — total: %d", len(_pelanggan_tamu))


def ada_tamu() -> bool:
    """Apakah ada jendela tamu yang terhubung via SSE?"""
    return len(_pelanggan_tamu) > 0


def kirim(data: dict[str, Any]) -> None:
    """Kirim peristiwa ke semua pelanggan (operator + tamu)."""
    import json
    pesan = json.dumps(data, ensure_ascii=False)
    for q in _pelanggan + _pelanggan_tamu:
        try:
            q.put_nowait(pesan)
        except asyncio.QueueFull:
            pass
    log.debug("Peristiwa dikirim ke %d pelanggan: %s",
              len(_pelanggan) + len(_pelanggan_tamu), data.get("jenis", "?"))
