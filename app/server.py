"""Session Manager — web server dan routing (arsitektur-sistem-photobooth.md §3.1).

Server utama MCF Photobooth. Menghubungkan:
  - Database SQLite (db.py)
  - Google Drive client (drive_client.py)
  - Folder Watcher (watcher.py)
  - QR Generator (qr.py)
  - SSE event bus (peristiwa.py)

Kamera Sony ZV-E10 disambung via Imaging Edge Desktop ke tether_dropbox/.

Jalankan:
    py -m uvicorn app.server:app --reload
"""

from __future__ import annotations

import asyncio
import os
import shutil
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Muat .env sebelum import modul lain supaya environment variables tersedia.
AKAR = Path(__file__).resolve().parent.parent
load_dotenv(AKAR / ".env")

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from . import db
from . import drive_client
from . import qr
from . import watcher
from . import peristiwa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

# Galat yang sudah diduga dipetakan ke kode status di satu tempat.
STATUS = {
    "nama_kosong": 422,
    "tidak_ada": 404,
    "sesi_masih_aktif": 409,
    "sudah_selesai": 409,
}


@asynccontextmanager
async def daur_hidup(app: FastAPI):
    db.siapkan()
    watcher.mulai()
    log.info("=== MCF Photobooth dimulai ===")
    log.info("Kamera: %s via %s",
             os.environ.get("CAMERA_MODEL", "Sony ZV-E10"),
             os.environ.get("TETHERING_APP", "Imaging Edge Desktop"))
    log.info("Tether dropbox: %s", os.environ.get("TETHER_DROPBOX", "tether_dropbox/"))
    log.info("Drive parent folder: %s", os.environ.get("DRIVE_PARENT_FOLDER_ID", "(tidak diset)"))
    yield
    watcher.berhenti()
    log.info("=== MCF Photobooth dihentikan ===")


app = FastAPI(
    title="MCF Photobooth — Session Manager",
    version="0.2.0",
    summary="Sistem photobooth otomatis dengan Google Drive, folder watcher, dan Sony ZV-E10.",
    lifespan=daur_hidup,
)


@app.exception_handler(db.GalatDB)
async def tangani_galat_db(request, exc: db.GalatDB):
    return JSONResponse(
        status_code=STATUS.get(exc.kode, 400),
        content={"galat": exc.kode, "pesan": exc.pesan, **exc.data},
    )


# --------------------------------------------------------------- Model


class SesiBaru(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)


# --------------------------------------------------------------- Sesi


@app.post("/api/sessions", status_code=201)
def buat_sesi(muatan: SesiBaru):
    """Mulai Sesi. Folder Drive dibuat, izin diset, dan QR disiapkan."""
    sesi = db.buat_sesi(muatan.guest_name)

    # Buat folder di Drive.
    folder = drive_client.buat_folder_sesi(sesi["session_code"])
    if folder:
        # Buat QR dari link Drive.
        qr_path = qr.buat_qr(folder["link"], sesi["session_code"])
        db.simpan_drive_info(sesi["id"], folder["id"], folder["link"], qr_path)
        # Upload QR ke Drive di folder 1. QR
        if qr_path:
            drive_client.upload_qr(qr_path, f"{sesi['session_code']}.png")
        # Refresh sesi dengan info Drive.
        sesi = db.ambil_sesi(sesi["id"])
        log.info("Sesi dimulai: %s → Drive: %s", sesi["session_code"], folder["link"])
    else:
        log.warning("Sesi dimulai tanpa folder Drive: %s", sesi["session_code"])

    # Kirim peristiwa SSE.
    peristiwa.kirim({
        "jenis": "sesi_mulai",
        "sesi": sesi,
    })

    return sesi


@app.get("/api/sessions")
def cari_sesi(
    q: str = Query("", description="Cari di nama tamu atau kode sesi"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Tanpa `q`, ini daftar Riwayat: terbaru di atas."""
    return db.cari_sesi(q, limit, offset)


# Harus di atas /{sesi_id} — kalau tidak, "active" ditelan sebagai id.
@app.get("/api/sessions/active")
def sesi_aktif():
    sesi = db.sesi_aktif()
    if sesi is None:
        raise db.GalatDB("Tidak ada sesi yang berjalan.", "tidak_ada")
    return sesi


@app.get("/api/sessions/{sesi_id}")
def ambil_sesi(sesi_id: int):
    return db.ambil_sesi(sesi_id)


@app.post("/api/sessions/{sesi_id}/finish")
def akhiri_sesi(sesi_id: int):
    """Selesai. QR ditampilkan di monitor tamu."""
    sesi = db.akhiri_sesi(sesi_id)

    # Kirim peristiwa SSE.
    peristiwa.kirim({
        "jenis": "sesi_selesai",
        "sesi": sesi,
    })

    return sesi


# --------------------------------------------------------------- Foto


@app.get("/api/sessions/{sesi_id}/photos")
def daftar_foto(sesi_id: int):
    """Daftar foto satu sesi dengan status per foto."""
    return db.daftar_foto(sesi_id)


@app.get("/api/sessions/{sesi_id}/foto-terakhir")
def foto_terakhir(sesi_id: int):
    """Foto terakhir yang masuk di sesi ini."""
    f = db.foto_terakhir(sesi_id)
    if f is None:
        raise db.GalatDB("Belum ada foto di sesi ini.", "tidak_ada")
    return f


@app.post("/api/photos/{foto_id}/retry")
def retry_foto(foto_id: int):
    """Retry upload satu foto yang gagal."""
    ok = watcher.retry_foto(foto_id)
    if not ok:
        raise db.GalatDB("Foto tidak ditemukan atau tidak bisa di-retry.", "tidak_ada")
    return {"ok": True}


@app.post("/api/sessions/{sesi_id}/retry-failed")
def retry_semua_gagal(sesi_id: int):
    """Retry semua foto gagal dari satu sesi."""
    jumlah = watcher.retry_semua_gagal(sesi_id)
    return {"ok": True, "jumlah_retry": jumlah}


# --------------------------------------------------------------- Thumbnail


THUMBS_DIR = Path(os.environ.get("THUMBS", AKAR / "thumbs"))


@app.get("/api/thumb/{session_code}/{filename}")
def ambil_thumb(session_code: str, filename: str):
    """Thumbnail foto dari local_archive."""
    thumb = THUMBS_DIR / session_code / filename
    if thumb.exists():
        return FileResponse(str(thumb), media_type="image/jpeg")
    raise db.GalatDB("Thumbnail tidak ditemukan.", "tidak_ada")


# --------------------------------------------------------------- QR Code


QR_DIR = Path(os.environ.get("QR_CODES", AKAR / "qr_codes"))


@app.get("/api/qr/{session_code}")
def ambil_qr(session_code: str):
    """QR code gambar untuk satu sesi."""
    qr_path = QR_DIR / f"{session_code}.png"
    if qr_path.exists():
        return FileResponse(str(qr_path), media_type="image/png")
    raise db.GalatDB("QR code tidak ditemukan.", "tidak_ada")


# --------------------------------------------------------------- Preflight


@app.get("/api/preflight")
def pemeriksaan_awal():
    """Pemeriksaan awal sebelum sesi dimulai."""
    drive_ok = drive_client.terhubung()
    drive_info = drive_client.info_akun() if drive_ok else None

    tether_dir = Path(os.environ.get("TETHER_DROPBOX", AKAR / "tether_dropbox"))
    archive_dir = Path(os.environ.get("LOCAL_ARCHIVE", AKAR / "local_archive"))

    # Ruang disk.
    try:
        disk = shutil.disk_usage(str(archive_dir.parent))
        disk_bebas_gb = round(disk.free / (1024 ** 3), 1)
    except Exception:
        disk_bebas_gb = None

    return {
        "drive_terhubung": drive_ok,
        "drive_email": drive_info["email"] if drive_info else None,
        "drive_kuota_sisa_gb": round(drive_info["kuota_sisa"] / (1024 ** 3), 1) if drive_info else None,
        "watcher_aktif": watcher.sedang_berjalan(),
        "tether_folder": str(tether_dir),
        "tether_ada": tether_dir.exists(),
        "disk_bebas_gb": disk_bebas_gb,
        "layar_tamu": peristiwa.ada_tamu(),
        "kamera": os.environ.get("CAMERA_MODEL", "Sony ZV-E10"),
        "tethering_app": os.environ.get("TETHERING_APP", "Imaging Edge Desktop"),
    }


# --------------------------------------------------------------- Tampilan Tamu


@app.get("/api/tampilan-tamu")
def tampilan_tamu():
    """Keadaan yang harus ditampilkan di layar tamu."""
    sesi = db.sesi_aktif()
    if sesi is None:
        # Cek sesi terakhir yang selesai (untuk tampilkan QR).
        with db.koneksi() as conn:
            terakhir = conn.execute(
                "SELECT * FROM sessions WHERE status = 'done' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if terakhir and terakhir["qr_path"]:
            fotos = db.daftar_foto(terakhir["id"])
            return {
                "keadaan": "qr",
                "nama_tamu": terakhir["guest_name"],
                "session_code": terakhir["session_code"],
                "drive_folder_link": terakhir["drive_folder_link"],
                "foto_count": len(fotos),
                "fotos": [{"nama": Path(f["local_path"]).name} for f in fotos[:6]],
            }
        return {"keadaan": "sambutan"}

    if sesi["status"] == "active":
        fotos = db.daftar_foto(sesi["id"])
        return {
            "keadaan": "memotret",
            "nama_tamu": sesi["guest_name"],
            "session_code": sesi["session_code"],
            "foto_count": len(fotos),
            "fotos": [{"nama": Path(f["local_path"]).name} for f in fotos[-6:]],
        }

    return {"keadaan": "sambutan"}


# --------------------------------------------------------------- SSE


@app.get("/api/peristiwa")
async def sse_operator():
    """Server-Sent Events untuk jendela operator."""
    q = peristiwa.daftar()
    try:
        async def gen():
            try:
                while True:
                    data = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"data": data}
            except asyncio.TimeoutError:
                yield {"data": '{"jenis":"ping"}'}
            except asyncio.CancelledError:
                pass

        return EventSourceResponse(gen())
    finally:
        peristiwa.hapus(q)


@app.get("/api/peristiwa-tamu")
async def sse_tamu():
    """Server-Sent Events untuk jendela tamu."""
    q = peristiwa.daftar_tamu()
    try:
        async def gen():
            try:
                while True:
                    data = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"data": data}
            except asyncio.TimeoutError:
                yield {"data": '{"jenis":"ping"}'}
            except asyncio.CancelledError:
                pass

        return EventSourceResponse(gen())
    finally:
        peristiwa.hapus_tamu(q)


# --------------------------------------------------------------- Static & Tamu

PROTO_DIR = AKAR / "prototipe"
STATIC_DIR = AKAR / "app" / "static"

# Mount static files kalau ada (fonts, dll).
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount folder prototipe di root — HARUS terakhir karena catch-all.
# Ini membuat ui.css, app.js, dan aset lain bisa diakses langsung dari
# root (/ui.css, /app.js) sesuai referensi relatif di HTML prototipe.
# html=True menjadikan index.html sebagai halaman default untuk "/".
if PROTO_DIR.exists():
    app.mount("/", StaticFiles(directory=str(PROTO_DIR), html=True), name="prototipe")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)
