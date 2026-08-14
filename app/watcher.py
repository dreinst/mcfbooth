"""Folder Watcher — pemantau folder tethering (arsitektur §3.2, langkah 3).

Proses background yang memantau `tether_dropbox/`. Untuk tiap file baru:
  1. Tunggu file selesai ditulis (cek ukuran file stabil).
  2. Salin ke `local_archive/<session_code>/`.
  3. Upload ke folder Drive milik sesi yang sedang `active`.
  4. Catat hasilnya (sukses/gagal) ke tabel `photo_uploads`.
  5. Retry otomatis dengan jeda bertambah (1, 5, 15 detik).

Mendukung format dari Sony ZV-E10 via Imaging Edge Desktop:
  - JPEG (.jpg, .jpeg)
  - ARW (Sony RAW) — diupload apa adanya, tidak dikonversi.
"""

from __future__ import annotations

import os
import shutil
import time
import logging
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from . import db
from . import drive_client
from . import peristiwa

log = logging.getLogger(__name__)

AKAR = Path(__file__).resolve().parent.parent
TETHER_DIR = Path(os.environ.get("TETHER_DROPBOX", AKAR / "tether_dropbox"))
ARCHIVE_DIR = Path(os.environ.get("LOCAL_ARCHIVE", AKAR / "local_archive"))
THUMBS_DIR = Path(os.environ.get("THUMBS", AKAR / "thumbs"))

# Ekstensi yang dianggap foto — dari Imaging Edge Desktop (Sony ZV-E10).
FOTO_EXT = {".jpg", ".jpeg", ".arw", ".png", ".tif", ".tiff"}

# Jeda retry dalam detik: 1, 5, 15. Setelah itu ditandai failed.
RETRY_DELAYS = [1, 5, 15]

# Waktu tunggu stabilitas file (detik) — file dianggap selesai ditulis
# kalau ukurannya tidak berubah selama interval ini.
STABILITAS_DETIK = 1.5

# Observer global.
_observer: Observer | None = None
_berjalan = False


def _tunggu_stabil(path: Path, timeout: float = 30) -> bool:
    """Tunggu sampai ukuran file stabil — file belum selesai ditulis oleh
    Imaging Edge selama ukurannya masih berubah."""
    prev = -1
    elapsed = 0
    while elapsed < timeout:
        try:
            curr = path.stat().st_size
            if curr == prev and curr > 0:
                return True
            prev = curr
            time.sleep(STABILITAS_DETIK)
            elapsed += STABILITAS_DETIK
        except OSError:
            return False
    return False


def _buat_thumbnail(src: Path, session_code: str) -> str | None:
    """Buat thumbnail 400px dari foto JPEG."""
    try:
        from PIL import Image

        thumb_dir = THUMBS_DIR / session_code
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / src.name

        if src.suffix.lower() in (".arw", ".raw"):
            # RAW tidak bisa di-thumbnail langsung — skip.
            return None

        with Image.open(src) as img:
            img.thumbnail((400, 400))
            img.save(str(thumb_path), "JPEG", quality=85)
            return str(thumb_path)
    except Exception as e:
        log.warning("Gagal buat thumbnail %s: %s", src.name, e)
        return None


def _proses_foto(path: Path) -> None:
    """Proses satu foto baru yang jatuh ke tether_dropbox."""
    nama = path.name
    log.info("Foto baru terdeteksi: %s", nama)

    # 1. Tunggu file selesai ditulis.
    if not _tunggu_stabil(path):
        log.warning("File tidak stabil dalam 30 detik: %s", nama)
        return

    # 2. Cari sesi aktif.
    sesi = db.sesi_aktif()
    if sesi is None:
        log.warning("Tidak ada sesi aktif — foto %s diabaikan.", nama)
        return

    session_code = sesi["session_code"]
    session_id = sesi["id"]
    drive_folder_id = sesi.get("drive_folder_id")

    # 3. Salin ke local_archive/<session_code>/.
    archive_dir = ARCHIVE_DIR / session_code
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / nama
    try:
        shutil.copy2(str(path), str(dest))
        log.info("Disalin ke arsip: %s", dest)
    except Exception as e:
        log.error("Gagal salin %s ke arsip: %s", nama, e)
        return

    # 4. Catat ke photo_uploads sebagai pending.
    foto_id = db.catat_foto(session_id, str(dest))

    # 5. Buat thumbnail.
    _buat_thumbnail(dest, session_code)

    # 6. Kirim peristiwa SSE — foto baru masuk.
    peristiwa.kirim({
        "jenis": "foto_baru",
        "session_id": session_id,
        "nama": nama,
        "foto_id": foto_id,
    })

    # 7. Upload ke Drive.
    if drive_folder_id:
        _upload_dengan_retry(foto_id, str(dest), drive_folder_id, session_id)
    else:
        log.warning("Sesi %s tidak punya folder Drive — foto ditandai pending.", session_code)


def _upload_dengan_retry(foto_id: int, path: str, folder_id: str, session_id: int) -> None:
    """Upload foto ke Drive dengan retry otomatis."""
    for i, delay in enumerate(RETRY_DELAYS):
        hasil = drive_client.upload_foto(path, folder_id)
        if hasil:
            db.tandai_foto_uploaded(foto_id, hasil["id"])
            peristiwa.kirim({
                "jenis": "foto_uploaded",
                "session_id": session_id,
                "foto_id": foto_id,
                "drive_file_id": hasil["id"],
            })
            return
        log.warning("Upload gagal (percobaan %d), retry dalam %d detik...", i + 1, delay)
        db.tambah_retry(foto_id)
        time.sleep(delay)

    # Semua retry gagal.
    db.tandai_foto_gagal(foto_id)
    peristiwa.kirim({
        "jenis": "foto_gagal",
        "session_id": session_id,
        "foto_id": foto_id,
    })
    log.error("Upload gagal setelah %d percobaan: %s", len(RETRY_DELAYS), path)


class _PemantauFoto(FileSystemEventHandler):
    """Handler watchdog yang hanya peduli file baru dengan ekstensi foto."""

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in FOTO_EXT:
            # Proses di thread terpisah supaya watchdog tidak terblokir.
            thread = threading.Thread(target=_proses_foto, args=(path,), daemon=True)
            thread.start()


def mulai() -> bool:
    """Mulai pemantau folder. Dipanggil di lifespan server."""
    global _observer, _berjalan

    TETHER_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    if _berjalan:
        log.info("Watcher sudah berjalan.")
        return True

    try:
        _observer = Observer()
        _observer.schedule(_PemantauFoto(), str(TETHER_DIR), recursive=False)
        _observer.start()
        _berjalan = True
        log.info("Watcher dimulai — memantau %s", TETHER_DIR)
        return True
    except Exception as e:
        log.error("Gagal memulai watcher: %s", e)
        return False


def berhenti() -> None:
    """Hentikan pemantau folder."""
    global _observer, _berjalan
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
    _berjalan = False
    log.info("Watcher dihentikan.")


def sedang_berjalan() -> bool:
    return _berjalan


def retry_foto(foto_id: int) -> bool:
    """Retry upload satu foto yang gagal."""
    with db.koneksi() as conn:
        baris = conn.execute(
            "SELECT * FROM photo_uploads WHERE id = ?", (foto_id,)
        ).fetchone()
        if not baris:
            return False

        sesi = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (baris["session_id"],)
        ).fetchone()
        if not sesi or not sesi["drive_folder_id"]:
            return False

    # Reset status ke pending dan coba upload.
    db.reset_foto_status(foto_id)
    thread = threading.Thread(
        target=_upload_dengan_retry,
        args=(foto_id, baris["local_path"], sesi["drive_folder_id"], sesi["id"]),
        daemon=True,
    )
    thread.start()
    return True


def retry_semua_gagal(session_id: int) -> int:
    """Retry semua foto gagal dari satu sesi. Returns jumlah yang di-retry."""
    with db.koneksi() as conn:
        fotos = conn.execute(
            "SELECT * FROM photo_uploads WHERE session_id = ? AND status = 'failed'",
            (session_id,),
        ).fetchall()
        sesi = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    if not sesi or not sesi["drive_folder_id"]:
        return 0

    count = 0
    for foto in fotos:
        db.reset_foto_status(foto["id"])
        thread = threading.Thread(
            target=_upload_dengan_retry,
            args=(foto["id"], foto["local_path"], sesi["drive_folder_id"], sesi["id"]),
            daemon=True,
        )
        thread.start()
        count += 1

    return count
