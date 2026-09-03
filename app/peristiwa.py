"""Server-Sent Events — aliran peristiwa ke jendela operator dan jendela tamu
(design.md §8).

Jendela tamu berganti keadaan tanpa polling; jendela operator ikut
memperbarui angkanya. Koneksi SSE dari /tamu yang masih hidup dipakai untuk
mendeteksi apakah jendela tamu benar-benar terbuka dan menerima keadaan.

Dua hal yang harus dijaga modul ini:

1. Pelanggan hanya dicabut ketika koneksinya benar-benar putus. Versi
   sebelumnya mencabutnya di `finally` milik handler — yang dieksekusi saat
   handler `return`, jadi antrean dilepas sebelum satu pun peristiwa terkirim.
2. `kirim()` dipanggil dari thread watcher dan dari handler sinkron FastAPI
   (keduanya bukan thread event loop). `asyncio.Queue` tidak thread-safe,
   jadi penyerahannya lewat `loop.call_soon_threadsafe`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

_kunci = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_pelanggan: list[asyncio.Queue] = []
_pelanggan_tamu: list[asyncio.Queue] = []


def _ingat_loop() -> None:
    global _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        pass


def daftar() -> asyncio.Queue:
    """Daftarkan pelanggan SSE baru (operator). Panggil dari event loop."""
    _ingat_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _kunci:
        _pelanggan.append(q)
    log.debug("Pelanggan operator terdaftar — total: %d", len(_pelanggan))
    return q


def hapus(q: asyncio.Queue) -> None:
    with _kunci:
        if q in _pelanggan:
            _pelanggan.remove(q)
    log.debug("Pelanggan operator dihapus — total: %d", len(_pelanggan))


def daftar_tamu() -> asyncio.Queue:
    """Daftarkan pelanggan SSE baru (layar tamu). Panggil dari event loop."""
    _ingat_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _kunci:
        _pelanggan_tamu.append(q)
    log.debug("Pelanggan tamu terdaftar — total: %d", len(_pelanggan_tamu))
    return q


def hapus_tamu(q: asyncio.Queue) -> None:
    with _kunci:
        if q in _pelanggan_tamu:
            _pelanggan_tamu.remove(q)
    log.debug("Pelanggan tamu dihapus — total: %d", len(_pelanggan_tamu))


def ada_tamu() -> bool:
    """Apakah ada jendela tamu yang terhubung via SSE?"""
    return len(_pelanggan_tamu) > 0


def jumlah_tamu() -> int:
    return len(_pelanggan_tamu)


def jumlah_operator() -> int:
    return len(_pelanggan)


def _taruh(q: asyncio.Queue, pesan: str) -> None:
    try:
        q.put_nowait(pesan)
    except asyncio.QueueFull:
        # Pelanggan yang tidak pernah membaca (tab yang dibekukan browser)
        # tidak boleh menahan yang lain. Pesan terlama dibuang.
        try:
            q.get_nowait()
            q.put_nowait(pesan)
        except Exception:
            pass


def kirim(data: dict[str, Any], *, ke_tamu: bool = True, ke_operator: bool = True) -> None:
    """Kirim peristiwa ke pelanggan. Aman dipanggil dari thread mana pun."""
    pesan = json.dumps(data, ensure_ascii=False, default=str)
    with _kunci:
        tujuan = []
        if ke_operator:
            tujuan += list(_pelanggan)
        if ke_tamu:
            tujuan += list(_pelanggan_tamu)
        loop = _loop
    if not tujuan:
        return
    if loop is None or loop.is_closed():
        for q in tujuan:
            _taruh(q, pesan)
        return
    for q in tujuan:
        loop.call_soon_threadsafe(_taruh, q, pesan)
    log.debug("Peristiwa %s → %d pelanggan", data.get("jenis", "?"), len(tujuan))
