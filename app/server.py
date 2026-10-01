"""Session Manager — web server dan routing (arsitektur-sistem-photobooth.md §3.1).

Server utama MCF Photobooth. Menghubungkan:
  - Database SQLite (db.py)
  - Klien Google Drive (drive_client.py)
  - Folder Watcher (watcher.py)
  - QR Generator (qr.py)
  - Bus peristiwa SSE (peristiwa.py)

Tampilan operator dan layar tamu disajikan dari folder `web/` di root.

Jalankan:
    py -m uvicorn app.server:app
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Muat .env sebelum import modul lain supaya environment variables tersedia.
from .jalur import AKAR, env_bool, path_env  # noqa: E402

load_dotenv(AKAR / ".env")

from fastapi import FastAPI, Query, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from . import db, drive_client, peristiwa, petblessing, qr, sertifikat, watcher  # noqa: E402

VERSI = "1.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

KAMERA = os.environ.get("CAMERA_MODEL", "Sony ZV-E10")
TETHERING_APP = os.environ.get("TETHERING_APP", "Imaging Edge Desktop")
IZINKAN_TANPA_DRIVE = env_bool("MCF_IZINKAN_TANPA_DRIVE", False)
THUMBS_DIR = watcher.THUMBS_DIR
QR_DIR = qr.QR_DIR
WEB_DIR = AKAR / "web"

# Galat yang sudah diduga dipetakan ke kode status di satu tempat.
STATUS = {
    "nama_kosong": 422,
    "tidak_ada": 404,
    "sesi_masih_aktif": 409,
    "sudah_selesai": 409,
    "sudah_terupload": 409,
    "sedang_diupload": 409,
    "berkas_hilang": 410,
    "drive_tidak_siap": 503,
    "bukan_mode_pb": 404,
    "pemilik_tidak_dikenal": 404,
    "data_tidak_cocok": 422,
    "belum_reg_ulang": 409,
    "foto_tidak_cocok": 422,
}


@asynccontextmanager
async def daur_hidup(app: FastAPI):
    db.siapkan()
    qr.siapkan()
    watcher.mulai()
    log.info("=== MCF Photobooth %s dimulai ===", VERSI)
    log.info("Kamera: %s via %s", KAMERA, TETHERING_APP)
    log.info("Tether dropbox: %s", watcher.TETHER_DIR)
    log.info("Arsip lokal: %s", watcher.ARCHIVE_DIR)
    log.info("Folder induk Drive: %s", drive_client.PARENT_FOLDER_ID or "(dibuat aplikasi)")
    if drive_client.PALSU:
        log.warning("MODE UJI: Google Drive digantikan tiruan dalam memori (MCF_DRIVE_PALSU=1).")
    await asyncio.get_running_loop().run_in_executor(None, watcher.pulihkan)
    yield
    watcher.berhenti()
    log.info("=== MCF Photobooth dihentikan ===")


app = FastAPI(
    title="MCF Photobooth — Session Manager",
    version=VERSI,
    summary="Sistem photobooth otomatis: tethering kamera, Google Drive, QR untuk tamu.",
    lifespan=daur_hidup,
)


@app.middleware("http")
async def tolak_lintas_situs(request: Request, call_next):
    """Aplikasi tidak punya login, jadi Origin adalah satu-satunya pagar:
    halaman web lain yang dibuka di laptop yang sama tidak boleh bisa mengakhiri
    sesi atau menghapus token lewat POST lintas situs."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        asal = request.headers.get("origin")
        host = request.headers.get("host", "")
        situs = request.headers.get("sec-fetch-site", "")
        if situs == "cross-site" or (asal and asal.split("://", 1)[-1] != host):
            return JSONResponse(status_code=403, content={"galat": "lintas_situs", "pesan": "Permintaan dari situs lain ditolak."})
    return await call_next(request)


@app.exception_handler(db.GalatDB)
async def tangani_galat_db(request, exc: db.GalatDB):
    return JSONResponse(
        status_code=STATUS.get(exc.kode, 400),
        content={"galat": exc.kode, "pesan": exc.pesan, **exc.data},
    )


# --------------------------------------------------------------- Model


class SesiBaru(BaseModel):
    guest_name: str | None = Field(None, max_length=120)
    # Mode Pet Blessing: nama sesi disusun server dari data pendaftaran,
    # bukan dari ketikan operator.
    owner_id: str | None = Field(None, max_length=64)
    pet_id: str | None = Field(None, max_length=64)


class PilihFoto(BaseModel):
    photo_id: int


# --------------------------------------------------------------- Sesi


@app.post("/api/sessions", status_code=201)
def buat_sesi(muatan: SesiBaru):
    """Mulai Sesi. Sesi tercatat seketika; folder Drive, izin, dan QR dipasang
    di latar dan diumumkan lewat peristiwa `sesi_drive_terpasang` — wifi venue
    yang lambat tidak boleh membuat tombol Mulai Sesi menggantung."""
    if muatan.pet_id or muatan.owner_id:
        sesi = _buat_sesi_pb(muatan.owner_id or "", muatan.pet_id or "")
    else:
        sesi = db.buat_sesi(muatan.guest_name or "")
    peristiwa.kirim({"jenis": "sesi_mulai", "sesi": sesi})
    watcher.pasang_drive_latar(sesi)
    return sesi


def _buat_sesi_pb(owner_id: str, pet_id: str) -> dict:
    if not petblessing.AKTIF:
        raise db.GalatDB("Mode Pet Blessing tidak aktif di laptop ini.", "bukan_mode_pb")
    pemilik = petblessing.pemilik_dari_id(owner_id)
    hewan = next((h for h in (pemilik or {}).get("hewan", []) if h["id"] == pet_id), None)
    if not pemilik or not hewan:
        raise db.GalatDB("Data pemilik atau hewan tidak ditemukan. Scan ulang QR-nya.", "data_tidak_cocok")
    if not pemilik.get("nomor"):
        raise db.GalatDB("Peserta ini belum reg ulang, jadi belum punya nomor kedatangan. "
                         "Arahkan ke meja reg ulang dulu.", "belum_reg_ulang")
    pb = {"owner_id": pemilik["id"], "pet_id": hewan["id"], "nomor": pemilik["nomor"],
          "nomor_daftar": pemilik.get("nomor_daftar"), "huruf": hewan["huruf"], "label": hewan["label"],
          "pemilik": pemilik["nama"], "hewan": hewan["nama"], "jenis": hewan["jenis"]}
    sesi = db.buat_sesi(f"{hewan['label']} {hewan['nama']} ({pemilik['nama']})", pb)
    watcher._jadwalkan(petblessing.tulis_hewan, pet_id, {"mcfbooth_session_code": sesi["session_code"]})
    return sesi


# --------------------------------------------------------------- Pet Blessing


@app.get("/api/pb/cari")
def pb_cari(q: str = Query(..., min_length=1, max_length=80)):
    """Nama pemilik atau nomor kedatangan → daftar calon (paling banyak 8)."""
    if not petblessing.AKTIF:
        raise db.GalatDB("Mode Pet Blessing tidak aktif di laptop ini.", "bukan_mode_pb")
    hasil, dari_salinan = petblessing.cari_nama(q)
    return {"hasil": [{"id": o["id"], "nama": o["nama"], "nomor": o["nomor"], "uji": o["uji"],
                       "hewan": [h["nama"] for h in o["hewan"]]} for o in hasil],
            "dari_salinan": dari_salinan}


@app.get("/api/pb/pemilik")
def pb_pemilik(kode: str = Query(..., min_length=8, max_length=64)):
    """Isi QR pendaftaran (UUID) atau kode 8 huruf → pemilik + hewannya,
    ditambah sertifikat yang sudah dibuat di booth ini untuk tiap hewan."""
    if not petblessing.AKTIF:
        raise db.GalatDB("Mode Pet Blessing tidak aktif di laptop ini.", "bukan_mode_pb")
    pemilik, dari_salinan = petblessing.cari_pemilik(kode)
    if not pemilik:
        raise db.GalatDB("QR tidak dikenali. Coba scan lagi atau ketik kode 8 hurufnya.",
                         "pemilik_tidak_dikenal", {"dari_salinan": dari_salinan})
    sudah = db.sertifikat_per_hewan([h["id"] for h in pemilik["hewan"]])
    for h in pemilik["hewan"]:
        h["sertifikat"] = sudah.get(h["id"])
    return {**pemilik, "dari_salinan": dari_salinan}


@app.post("/api/sessions/{sesi_id}/sertifikat", status_code=202)
def buat_sertifikat(sesi_id: int, muatan: PilihFoto):
    """Foto pilihan operator → sertifikat. Render dan upload berjalan di latar;
    hasilnya diumumkan lewat peristiwa sertifikat_siap / _uploaded / _gagal."""
    sesi = db.ambil_sesi(sesi_id)
    if not sesi.get("pb"):
        raise db.GalatDB("Sesi ini bukan sesi Pet Blessing.", "bukan_mode_pb")
    foto = db.ambil_foto(muatan.photo_id)
    if not foto or foto["session_id"] != sesi_id:
        raise db.GalatDB("Foto itu bukan milik sesi ini.", "foto_tidak_cocok")
    if Path(foto["local_path"]).suffix.lower() not in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        raise db.GalatDB("Pilih foto JPEG. Berkas RAW tidak bisa dipakai untuk sertifikat.", "foto_tidak_cocok")
    if not Path(foto["local_path"]).exists():
        raise db.GalatDB("Berkas foto tidak ada lagi di arsip lokal.", "berkas_hilang")
    return sertifikat.mulai(sesi, foto)


@app.get("/api/sessions/{sesi_id}/sertifikat")
def daftar_sertifikat(sesi_id: int):
    db.ambil_sesi(sesi_id)
    return db.sertifikat_sesi(sesi_id)


@app.get("/api/sertifikat/{sertifikat_id}/berkas.{jenis}")
def berkas_sertifikat(sertifikat_id: int, jenis: str):
    """Pratinjau PNG atau unduh PDF dari salinan lokal."""
    srt = db.ambil_sertifikat(sertifikat_id)
    path = srt and srt.get({"png": "png_path", "pdf": "pdf_path"}.get(jenis, "-"))
    if not path or not Path(path).exists():
        raise db.GalatDB("Berkas sertifikat belum ada.", "tidak_ada")
    return FileResponse(path, media_type="image/png" if jenis == "png" else "application/pdf",
                        filename=Path(path).name)


@app.get("/api/sessions")
def cari_sesi(
    q: str = Query("", description="Cari di nama tamu atau kode sesi"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Tanpa `q`, ini daftar Riwayat: terbaru di atas."""
    return db.cari_sesi(q, limit, offset)


# Rute statis harus di atas /{sesi_id} — kalau tidak, ditelan sebagai id.


@app.get("/api/sessions/active")
def sesi_aktif():
    sesi = db.sesi_aktif()
    if sesi is None:
        raise db.GalatDB("Tidak ada sesi yang berjalan.", "tidak_ada")
    return sesi


@app.get("/api/sessions/ringkasan")
def ringkasan_sesi():
    return db.ringkasan_riwayat()


@app.get("/api/sessions/nama-serupa")
def nama_serupa(q: str = Query("", max_length=120)):
    """Berapa sesi hari ini memakai nama yang sama — keterangan di input nama."""
    return {"jumlah": db.nama_serupa_hari_ini(q)}


@app.post("/api/sessions/bersiap")
def bersiap():
    """Operator mulai mengetik nama tamu berikutnya: tenggang setelah Selesai
    dibatalkan supaya jepretan uji tidak masuk ke folder tamu sebelumnya."""
    watcher.batalkan_tenggang()
    return {"ok": True}


@app.get("/api/sessions/{sesi_id}")
def ambil_sesi(sesi_id: int):
    return db.ambil_sesi(sesi_id)


@app.post("/api/sessions/{sesi_id}/finish")
def akhiri_sesi(sesi_id: int):
    """Selesai. QR ditampilkan di monitor tamu."""
    sesi = db.akhiri_sesi(sesi_id)
    sesi = watcher.pastikan_qr(sesi)
    peristiwa.kirim({"jenis": "sesi_selesai", "sesi": sesi})
    return sesi


@app.post("/api/sessions/{sesi_id}/drive")
def pasang_drive_sesi(sesi_id: int):
    """Pasang folder Drive + QR ke sesi yang dimulai saat Drive putus, lalu
    antrekan foto yang sudah menunggu."""
    sesi = db.ambil_sesi(sesi_id)
    hasil = watcher.pasang_drive(sesi)
    if not hasil or not hasil.get("drive_folder_id"):
        raise db.GalatDB("Drive belum bisa dijangkau. Periksa sambungan di Pengaturan.", "drive_tidak_siap")
    return hasil


@app.post("/api/sessions/{sesi_id}/tampilkan-qr")
def tampilkan_qr(sesi_id: int):
    """Riwayat → Tampilkan QR: monitor tamu menampilkan QR sesi ini sampai
    sesi berikutnya dimulai atau dibatalkan lewat DELETE /api/tampilan-tamu/qr."""
    sesi = db.ambil_sesi(sesi_id)
    if not sesi.get("drive_folder_link"):
        raise db.GalatDB("Sesi ini belum punya folder Drive, jadi belum ada QR.", "drive_tidak_siap")
    if db.sesi_aktif():
        raise db.GalatDB("Masih ada sesi berjalan — akhiri dulu sebelum menampilkan QR lama.", "sesi_masih_aktif")
    watcher.pastikan_qr(sesi)
    db.simpan_pengaturan("paksa_sambutan", None)
    db.simpan_pengaturan("tampilkan_qr_sesi_id", str(sesi_id))
    peristiwa.kirim({"jenis": "tampilan_tamu", "tampilan": tampilan_tamu()})
    return {"ok": True, "sesi": sesi}


@app.delete("/api/tampilan-tamu/qr")
def kembali_ke_sambutan():
    """Batalkan QR dari Riwayat dan paksa monitor tamu ke layar sambutan
    sampai sesi berikutnya dimulai."""
    db.simpan_pengaturan("tampilkan_qr_sesi_id", None)
    db.simpan_pengaturan("paksa_sambutan", "1")
    peristiwa.kirim({"jenis": "tampilan_tamu", "tampilan": tampilan_tamu()})
    return {"ok": True}


@app.post("/api/tanpa-sesi/akui")
def akui_tanpa_sesi():
    """Operator sudah membaca pita "foto masuk saat tidak ada sesi"."""
    watcher.akui_tanpa_sesi()
    return {"ok": True, "foto_tanpa_sesi": watcher.jumlah_tanpa_sesi()}


# --------------------------------------------------------------- Foto


def _bentuk_foto(f: dict) -> dict:
    d = dict(f)
    d["nama"] = Path(f["local_path"]).name
    d["thumb"] = watcher.nama_thumb(f["local_path"])
    return d


@app.get("/api/sessions/{sesi_id}/photos")
def daftar_foto(sesi_id: int):
    """Daftar foto satu sesi dengan status per foto."""
    db.ambil_sesi(sesi_id)
    return [_bentuk_foto(f) for f in db.daftar_foto(sesi_id)]


@app.get("/api/sessions/{sesi_id}/foto-terakhir")
def foto_terakhir(sesi_id: int):
    f = db.foto_terakhir(sesi_id)
    if f is None:
        raise db.GalatDB("Belum ada foto di sesi ini.", "tidak_ada")
    return _bentuk_foto(f)


@app.post("/api/photos/{foto_id}/retry")
def retry_foto(foto_id: int):
    """Upload ulang satu foto yang gagal (atau menggantung)."""
    ok, alasan = watcher.retry_foto(foto_id)
    if not ok:
        pesan = {
            "tidak_ada": "Foto tidak ditemukan.",
            "sudah_terupload": "Foto ini sudah ada di Drive.",
            "sedang_diupload": "Foto ini sedang diupload.",
            "berkas_hilang": "Berkas aslinya tidak ada lagi di arsip lokal.",
        }.get(alasan, "Tidak bisa di-retry.")
        raise db.GalatDB(pesan, alasan)
    return {"ok": True}


@app.post("/api/sessions/{sesi_id}/retry-failed")
def retry_semua_gagal(sesi_id: int):
    """Upload ulang semua foto gagal/menggantung dari satu sesi."""
    db.ambil_sesi(sesi_id)
    return watcher.retry_semua_gagal(sesi_id)


# --------------------------------------------------------------- Berkas


def _berkas_aman(dasar: Path, *bagian: str) -> Path | None:
    """Path di bawah `dasar`, ditolak kalau ada yang mencoba keluar darinya
    atau membawa karakter yang tidak mungkin ada di nama berkas."""
    if any((not b) or ("\x00" in b) or ("/" in b) or ("\\" in b) for b in bagian):
        return None
    try:
        calon = dasar.joinpath(*bagian).resolve()
        calon.relative_to(dasar)
        return calon if calon.is_file() else None
    except (ValueError, OSError):
        return None


@app.get("/api/thumb/{session_code}/{filename}")
def ambil_thumb(session_code: str, filename: str):
    """Thumbnail foto dari thumbs/<session_code>/<nama>.jpg."""
    thumb = _berkas_aman(THUMBS_DIR, session_code, filename)
    if thumb is None:
        # Nama asli (IMG_0041.JPG) juga diterima — thumbnail selalu .jpg.
        thumb = _berkas_aman(THUMBS_DIR, session_code, Path(filename).stem + ".jpg")
    if thumb is None:
        raise db.GalatDB("Thumbnail tidak ditemukan.", "tidak_ada")
    return FileResponse(str(thumb), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/qr/{session_code}")
def ambil_qr(session_code: str):
    qr_path = _berkas_aman(QR_DIR, f"{session_code}.png")
    if qr_path is None:
        # PNG hilang (pindah laptop) tapi tautannya ada di DB: buat lagi.
        sesi = db.sesi_dari_kode(session_code)
        if sesi and sesi.get("drive_folder_link"):
            watcher.pastikan_qr(sesi)
            qr_path = _berkas_aman(QR_DIR, f"{session_code}.png")
    if qr_path is None:
        raise db.GalatDB("QR code tidak ditemukan.", "tidak_ada")
    return FileResponse(str(qr_path), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})


# --------------------------------------------------------------- Preflight

_cache_struktur: tuple[float, dict | None] = (0.0, None)


def _struktur_drive(terhubung: bool) -> dict | None:
    global _cache_struktur
    if not terhubung:
        return None
    if time.time() - _cache_struktur[0] < 60 and _cache_struktur[1]:
        return _cache_struktur[1]
    struktur = drive_client.pastikan_struktur()
    _cache_struktur = (time.time(), struktur)
    return struktur


def _gb(n: int | None) -> float | None:
    return round(n / (1024 ** 3), 1) if isinstance(n, (int, float)) else None


@app.get("/api/preflight")
def pemeriksaan_awal():
    """Enam pemeriksaan sebelum sesi dimulai (design.md §4.1), plus ringkasan
    yang dipakai kaki sidebar di semua halaman.

    Yang menghalangi Mulai Sesi hanya keadaan yang tidak akan pulih sendiri:
    belum login, kredensial tidak ada, token ditolak, pemantau mati, sesi lain
    masih berjalan. Wifi putus hanya peringatan — foto diarsipkan dan diupload
    begitu tersambung; itulah alasan arsip lokal ada."""
    st = drive_client.status()
    terhubung = st["keadaan"] == "terhubung"
    info = drive_client.info_akun() if terhubung else None
    struktur = _struktur_drive(terhubung)

    tether_dir, archive_dir = watcher.TETHER_DIR, watcher.ARCHIVE_DIR
    try:
        disk = shutil.disk_usage(str(archive_dir if archive_dir.exists() else archive_dir.parent))
        disk_bebas_gb = round(disk.free / (1024 ** 3), 1)
    except Exception:
        disk_bebas_gb = None

    stat = watcher.statistik()
    sesi = db.sesi_aktif()

    boleh, alasan, peringatan = True, None, None
    if sesi:
        boleh, alasan = False, f"Masih ada sesi berjalan atas nama {sesi['guest_name']} — lanjutkan atau akhiri lewat pita di atas."
    elif not watcher.sedang_berjalan():
        boleh, alasan = False, "Pemantau folder tethering tidak berjalan. Mulai ulang server."
    elif st["keadaan"] in ("belum_login", "tanpa_credentials", "token_kedaluwarsa") and not IZINKAN_TANPA_DRIVE:
        boleh, alasan = False, "Google Drive belum terhubung — foto tidak akan sampai ke tamu. Login di Pengaturan."
    elif not terhubung:
        peringatan = "Drive tidak terjangkau saat ini. Foto diarsipkan di laptop dan diupload otomatis begitu tersambung."

    return {
        "versi": VERSI,
        "mode": petblessing.MODE,
        "pb_siap": petblessing.siap(),
        "drive": {
            **st,
            "kuota_total_gb": _gb(info["kuota_total"]) if info else None,
            "kuota_terpakai_gb": _gb(info["kuota_terpakai"]) if info else None,
            "kuota_sisa_gb": _gb(info["kuota_sisa"]) if info else None,
        },
        "drive_terhubung": terhubung,
        "drive_struktur": struktur,
        "internet": drive_client.internet_ok(),
        "watcher_aktif": watcher.sedang_berjalan(),
        "tether_folder": str(tether_dir),
        "tether_ada": tether_dir.exists(),
        "archive_folder": str(archive_dir),
        "disk_bebas_gb": disk_bebas_gb,
        "layar_tamu": peristiwa.ada_tamu(),
        "layar_tamu_jumlah": peristiwa.jumlah_tamu(),
        "tampilan_tamu": tampilan_tamu(),
        "kamera": KAMERA,
        "tethering_app": TETHERING_APP,
        "sesi_aktif": sesi,
        "boleh_mulai": boleh,
        "alasan_tidak_boleh": alasan,
        "peringatan_mulai": peringatan,
        "izinkan_tanpa_drive": IZINKAN_TANPA_DRIVE,
        **stat,
    }


@app.get("/api/pengaturan")
def pengaturan():
    """Nilai konfigurasi yang berlaku — dibaca dari .env, tidak bisa diubah
    dari browser (sengaja: aplikasi tidak punya login)."""
    return {
        "versi": VERSI,
        "kamera": KAMERA,
        "tethering_app": TETHERING_APP,
        "tether_folder": str(watcher.TETHER_DIR),
        "archive_folder": str(watcher.ARCHIVE_DIR),
        "thumbs_folder": str(THUMBS_DIR),
        "qr_folder": str(QR_DIR),
        "db": str(db.BERKAS_DB),
        "retry_delays": watcher.RETRY_DELAYS,
        "penjaga_detik": watcher.PENJAGA_DETIK,
        "upload_paralel": watcher.UPLOAD_PARALEL,
        "tenggang_setelah_selesai": watcher.TENGGANG_SETELAH_SELESAI,
        "stabilitas_detik": watcher.STABILITAS_DETIK,
        "stabil_timeout": watcher.STABIL_TIMEOUT,
        "izinkan_tanpa_drive": IZINKAN_TANPA_DRIVE,
        "drive": drive_client.ringkasan(),
        "ringkasan": db.ringkasan_riwayat(),
    }


# --------------------------------------------------------------- Drive


@app.get("/api/drive/status")
def drive_status(paksa: bool = False):
    st = drive_client.status(paksa=paksa)
    return {**st, "login": drive_client.login_keadaan()}


@app.post("/api/drive/login")
def drive_login():
    return {**drive_client.login_mulai(), "login": drive_client.login_keadaan()}


@app.get("/api/drive/login")
def drive_login_keadaan():
    return drive_client.login_keadaan()


@app.post("/api/drive/logout")
def drive_logout():
    global _cache_struktur
    _cache_struktur = (0.0, None)
    hasil = drive_client.logout()
    peristiwa.kirim({"jenis": "drive_status", "status": drive_client.status(paksa=True)}, ke_tamu=False)
    return hasil


# --------------------------------------------------------------- Tampilan tamu


def _thumbs_tampilan(sesi: dict, jumlah: int = 6) -> list[dict]:
    fotos = db.daftar_foto(sesi["id"])
    hasil = []
    for f in fotos[-jumlah:]:
        thumb = watcher.nama_thumb(f["local_path"])
        if (THUMBS_DIR / sesi["session_code"] / thumb).exists():
            hasil.append({"nama": Path(f["local_path"]).name, "thumb": thumb})
    return hasil


def _keadaan_qr(sesi: dict) -> dict:
    sesi = watcher.pastikan_qr(sesi)
    hitung = sesi["foto"]
    return {
        "keadaan": "qr",
        "session_id": sesi["id"],
        "nama_tamu": sesi["guest_name"],
        "session_code": sesi["session_code"],
        "drive_folder_link": sesi["drive_folder_link"],
        "qr_ada": bool(sesi.get("qr_path")) and Path(sesi["qr_path"]).exists(),
        # Tamu tidak boleh melihat status upload (design.md §5.2): angkanya
        # jumlah foto, sama seperti saat memotret — bukan yang sudah di Drive.
        "foto_count": hitung["total"],
        "foto_uploaded": hitung["uploaded"],
        "fotos": _thumbs_tampilan(sesi),
    }


@app.get("/api/tampilan-tamu")
def tampilan_tamu():
    """Keadaan yang harus ditampilkan di layar tamu: sambutan, memotret, qr."""
    sesi = db.sesi_aktif()
    if sesi:
        return {
            "keadaan": "memotret",
            "session_id": sesi["id"],
            "nama_tamu": sesi["guest_name"],
            "session_code": sesi["session_code"],
            "foto_count": sesi["foto"]["total"],
            "fotos": _thumbs_tampilan(sesi),
        }

    paksa = db.ambil_pengaturan("tampilkan_qr_sesi_id")
    if paksa:
        try:
            s = db.ambil_sesi(int(paksa))
            if s.get("drive_folder_link"):
                return {**_keadaan_qr(s), "dari_riwayat": True}
        except (db.GalatDB, ValueError):
            db.simpan_pengaturan("tampilkan_qr_sesi_id", None)

    if db.ambil_pengaturan("paksa_sambutan"):
        return {"keadaan": "sambutan", "dipaksa": True}

    terakhir = db.sesi_terakhir_selesai()
    if terakhir and terakhir.get("drive_folder_link"):
        return _keadaan_qr(terakhir)
    return {"keadaan": "sambutan"}


# --------------------------------------------------------------- SSE


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _aliran(q: asyncio.Queue, lepas, halo: dict):
    """Generator SSE. Pelanggan dilepas hanya di finally milik generator —
    yaitu saat koneksi benar-benar putus — bukan saat handler return."""

    async def gen():
        try:
            yield {"event": "halo", "data": _json(halo)}
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=25)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"data": '{"jenis":"ping"}'}
        finally:
            lepas(q)

    return EventSourceResponse(gen(), ping=60)


@app.get("/api/peristiwa")
async def sse_operator():
    """Server-Sent Events untuk jendela operator."""
    q = peristiwa.daftar()
    halo = {"jenis": "halo", "sesi_aktif": db.sesi_aktif(), "tampilan": tampilan_tamu(),
            "layar_tamu": peristiwa.ada_tamu()}
    return _aliran(q, peristiwa.hapus, halo)


@app.get("/api/peristiwa-tamu")
async def sse_tamu():
    """Server-Sent Events untuk jendela tamu. Koneksi yang hidup di sini
    yang membuat chip "Layar tamu terhubung" menyala."""
    q = peristiwa.daftar_tamu()
    halo = {"jenis": "halo", "tampilan": tampilan_tamu()}
    peristiwa.kirim({"jenis": "layar_tamu", "terhubung": True,
                     "jumlah": peristiwa.jumlah_tamu()}, ke_tamu=False)

    def lepas(qq):
        peristiwa.hapus_tamu(qq)
        peristiwa.kirim({"jenis": "layar_tamu", "terhubung": peristiwa.ada_tamu(),
                         "jumlah": peristiwa.jumlah_tamu()}, ke_tamu=False)

    return _aliran(q, lepas, halo)


# --------------------------------------------------------------- Halaman


@app.get("/tema.js", include_in_schema=False)
def tema_js():
    """Dimuat di <head> tiap halaman, sebelum tampil, supaya tema Pet Blessing
    tidak berkedip dari tema MCF."""
    isi = "document.documentElement.setAttribute('data-pb','');" if petblessing.AKTIF else ""
    return Response(isi, media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.get("/tamu", include_in_schema=False)
def halaman_tamu():
    """Halaman layar tamu — dokumen terpisah tanpa navigasi (design.md §8)."""
    return FileResponse(str(WEB_DIR / "tamu.html"), media_type="text/html")


if WEB_DIR.exists():
    # Harus terakhir karena catch-all. html=True menjadikan index.html
    # halaman untuk "/".
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)
