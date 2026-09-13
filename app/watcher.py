"""Folder Watcher — pemantau folder tethering (arsitektur §3.2).

Proses latar yang memantau `tether_dropbox/`. Untuk tiap berkas foto baru:
  1. Tunggu berkas selesai ditulis (ukuran stabil dan bisa dibuka).
  2. Tentukan sesinya: yang `active`; kalau tidak ada, sesi yang baru saja
     diakhiri dalam tenggang `TENGGANG_SETELAH_SELESAI`; kalau itu pun tidak
     ada, berkas diamankan ke `local_archive/_tanpa_sesi/` dan operator
     diberi tahu.
  3. Salin ke `local_archive/<session_code>/` (lewat berkas sementara, lalu
     rename) — tidak pernah dihapus.
  4. Catat ke `photo_uploads` sebagai pending, buat thumbnail.
  5. Upload ke folder Drive sesi lewat pool pekerja; percobaan pertama plus
     retry 1, 5, 15 detik; setelah itu ditandai `failed`.

Yang juga dijaga modul ini:

* `pasang_drive` dikunci per sesi dan membaca ulang DB di dalam kunci — tanpa
  itu, delapan upload paralel untuk sesi yang dimulai saat Drive putus akan
  membuat delapan folder Drive dan QR menunjuk folder yang tidak lengkap.
* Penjaga latar tiap `PENJAGA_DETIK`: mengulang upload yang gagal/menggantung
  begitu Drive terjangkau lagi, memasang folder ke sesi yang belum punya, dan
  menyapu berkas tether yang terlewat selama ada sesi aktif.
* Berkas yang gagal diproses (tidak stabil, disk penuh) tidak dianggap
  selesai: operator diberi tahu dan penjaga mencobanya lagi.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import db, drive_client, peristiwa, qr
from .jalur import AKAR, env_float, env_int, path_env

log = logging.getLogger(__name__)

# Di-resolve supaya path dari watchdog (yang selalu nyata, mis. /private/var di
# macOS) bisa dibandingkan dengan path dari .env (yang boleh lewat symlink).
TETHER_DIR = path_env("TETHER_DROPBOX", AKAR / "tether_dropbox")
ARCHIVE_DIR = path_env("LOCAL_ARCHIVE", AKAR / "local_archive")
THUMBS_DIR = path_env("THUMBS", AKAR / "thumbs")
FOLDER_TANPA_SESI = "_tanpa_sesi"

# Ekstensi yang dianggap foto. ARW (RAW Sony) ikut diupload apa adanya —
# tidak dikonversi dan tidak punya thumbnail.
FOTO_EXT = {".jpg", ".jpeg", ".arw", ".png", ".tif", ".tiff", ".heic"}

# Jeda retry dalam detik setelah percobaan pertama gagal: 1, 5, 15.
RETRY_DELAYS = [1, 5, 15]

# Berkas dianggap selesai ditulis kalau ukurannya tidak berubah selama
# interval ini. Aplikasi tethering menulis JPEG 24 MP dalam beberapa detik.
STABILITAS_DETIK = env_float("STABILITAS_DETIK", 1.5)
STABIL_TIMEOUT = env_float("STABIL_TIMEOUT", 45)

# Foto yang mendarat setelah Selesai masih dianggap milik sesi itu selama
# tenggang ini (detik). Tenggang batal begitu operator mulai mengetik nama
# tamu berikutnya.
TENGGANG_SETELAH_SELESAI = env_float("TENGGANG_SETELAH_SELESAI", 45)

# Penjaga latar dan pool upload.
PENJAGA_DETIK = env_float("PENJAGA_DETIK", 30)
UPLOAD_PARALEL = max(1, env_int("UPLOAD_PARALEL", 3))

_observer: Observer | None = None
_berjalan = False
_kunci = threading.Lock()
_sedang_diproses: set[str] = set()          # path sumber yang sedang ditangani
_sedang_diupload: set[int] = set()          # foto_id yang sedang diupload
_sumber_selesai: dict[str, tuple[int, float]] = {}   # path sumber → (ukuran, mtime) yang sudah beres
_kunci_drive: dict[int, threading.Lock] = {}
_tenggang_batal_at: float = 0.0
_pool: ThreadPoolExecutor | None = None
_penjaga_stop = threading.Event()


# ----------------------------------------------------------------- utilitas


def _aman(fn, *args):
    """Pembungkus target thread/pool: galat tak terduga dicatat, bukan
    membunuh pekerja diam-diam."""
    try:
        return fn(*args)
    except Exception as e:  # pragma: no cover — jaring pengaman
        log.exception("Galat tak terduga di %s: %s", getattr(fn, "__name__", fn), e)
        return None


def _jadwalkan(fn, *args) -> None:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=UPLOAD_PARALEL, thread_name_prefix="upload")
    _pool.submit(_aman, fn, *args)


def _kunci_sesi(sesi_id: int) -> threading.Lock:
    with _kunci:
        return _kunci_drive.setdefault(sesi_id, threading.Lock())


def _identitas(path: Path) -> tuple[int, float] | None:
    try:
        st = path.stat()
        return (st.st_size, st.st_mtime)
    except OSError:
        return None


def _tunggu_stabil(path: Path, timeout: float = STABIL_TIMEOUT) -> bool:
    """Tunggu sampai ukuran berkas stabil dan bisa dibuka untuk dibaca."""
    prev = -1
    elapsed = 0.0
    while elapsed < timeout:
        try:
            curr = path.stat().st_size
        except OSError:
            return False
        if curr == prev and curr > 0:
            try:
                # Di Windows, berkas yang masih dipegang aplikasi tethering
                # menolak dibuka — itu tanda belum selesai.
                with open(path, "rb"):
                    pass
                return True
            except OSError:
                pass
        prev = curr
        time.sleep(STABILITAS_DETIK)
        elapsed += STABILITAS_DETIK
    return False


def _salin_atomik(src: Path, dest: Path) -> None:
    """Salin lewat `.part` lalu rename, supaya crash di tengah salinan tidak
    meninggalkan berkas terpotong bernama asli di lapis backup permanen."""
    part = dest.with_name(dest.name + ".part")
    shutil.copy2(str(src), str(part))
    os.replace(part, dest)


def _buat_thumbnail(src: Path, session_code: str) -> str | None:
    """Thumbnail 400px, ditulis ke berkas sementara lalu di-rename supaya
    /api/thumb tidak pernah menyajikan berkas yang setengah jadi."""
    if src.suffix.lower() in (".arw", ".raw"):
        return None
    try:
        from PIL import Image, ImageOps

        thumb_dir = THUMBS_DIR / session_code
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / (src.stem + ".jpg")
        tmp_path = thumb_dir / (src.stem + ".tmp")
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((400, 400))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(str(tmp_path), "JPEG", quality=85)
        os.replace(tmp_path, thumb_path)
        return str(thumb_path)
    except Exception as e:
        log.warning("Gagal buat thumbnail %s: %s", src.name, e)
        return None


def nama_thumb(local_path: str) -> str:
    """Nama berkas thumbnail untuk satu foto — dipakai server dan tampilan."""
    return Path(local_path).stem + ".jpg"


def _sesi_tujuan() -> tuple[dict | None, str]:
    """Sesi yang harus menerima foto baru, beserta alasannya."""
    sesi = db.sesi_aktif()
    if sesi:
        return sesi, "aktif"
    terakhir = db.sesi_terakhir_selesai()
    if terakhir and terakhir.get("finished_at"):
        try:
            selesai = datetime.fromisoformat(terakhir["finished_at"])
            umur = (datetime.now().astimezone() - selesai).total_seconds()
            if 0 <= umur <= TENGGANG_SETELAH_SELESAI and selesai.timestamp() > _tenggang_batal_at:
                return terakhir, "tenggang"
        except ValueError:
            pass
    return None, "tanpa_sesi"


def batalkan_tenggang() -> None:
    """Operator mulai mengetik nama tamu berikutnya: jepretan uji untuk tamu
    baru tidak boleh masuk ke folder tamu sebelumnya yang sudah dibagikan."""
    global _tenggang_batal_at
    _tenggang_batal_at = time.time()


# --------------------------------------------------------------- drive/QR


def pastikan_qr(sesi: dict) -> dict:
    """Buat ulang PNG QR kalau hilang (pindah laptop, folder qr_codes dibersihkan)
    — tautannya tersimpan di DB, jadi QR selalu bisa dibuat lagi (PRD FR14)."""
    link = sesi.get("drive_folder_link")
    if not link:
        return sesi
    path = sesi.get("qr_path")
    if path and Path(path).exists():
        return sesi
    baru = qr.buat_qr(link, sesi["session_code"])
    if baru:
        db.simpan_qr_path(sesi["id"], baru)
        sesi = dict(sesi, qr_path=baru)
    return sesi


def pasang_drive(sesi: dict) -> dict | None:
    """Pastikan sesi punya folder Drive dan QR. Dipanggil saat Mulai Sesi,
    sebelum upload, dari tombol coba lagi, dan dari penjaga latar.

    Dikunci per sesi dan membaca ulang DB di dalam kunci, jadi berapa pun
    thread yang memanggilnya bersamaan, folder hanya dibuat sekali.

    Returns sesi yang sudah diperbarui, atau None kalau Drive belum bisa."""
    if sesi.get("drive_folder_id"):
        return pastikan_qr(sesi)

    with _kunci_sesi(sesi["id"]):
        try:
            sesi = db.ambil_sesi(sesi["id"])
        except db.GalatDB:
            return None
        if sesi.get("drive_folder_id"):
            return pastikan_qr(sesi)

        folder = drive_client.buat_folder_sesi(sesi["session_code"])
        if not folder:
            return None
        qr_path = qr.buat_qr(folder["link"], sesi["session_code"])
        if not db.simpan_drive_info(sesi["id"], folder["id"], folder["link"], qr_path):
            log.warning("Folder Drive untuk %s sudah dipasang thread lain; folder %s dibiarkan.",
                        sesi["session_code"], folder["id"])
            return db.ambil_sesi(sesi["id"])
        if qr_path:
            drive_client.upload_qr(qr_path, f"{sesi['session_code']}.png")
        baru = db.ambil_sesi(sesi["id"])

    peristiwa.kirim({"jenis": "sesi_drive_terpasang", "sesi": baru})
    log.info("Folder Drive terpasang ke sesi %s", sesi["session_code"])
    # Foto yang sudah menunggu di sesi ini ikut diantrekan sekarang.
    _antre_sisa(baru)
    return baru


def pasang_drive_latar(sesi: dict) -> None:
    """Versi latar untuk Mulai Sesi: request 201 kembali seketika, folder
    dipasang di pool dan diumumkan lewat `sesi_drive_terpasang`."""
    _jadwalkan(pasang_drive, sesi)


def _antre_sisa(sesi: dict, kecuali: int | None = None) -> int:
    """Antrekan upload untuk semua foto pending/failed satu sesi yang tidak
    sedang diupload. Returns jumlah yang diantrekan."""
    calon = db.foto_berstatus("pending", sesi["id"]) + db.foto_berstatus("failed", sesi["id"])
    jumlah = 0
    for foto in calon:
        if foto["id"] == kecuali:
            continue
        with _kunci:
            if foto["id"] in _sedang_diupload:
                continue
        if not Path(foto["local_path"]).exists():
            if foto["status"] != "failed":
                db.tandai_foto_gagal(foto["id"])
            continue
        if foto["status"] == "failed":
            db.reset_foto_status(foto["id"])
            foto = db.ambil_foto(foto["id"])
            peristiwa.kirim({"jenis": "foto_retry", "session_id": sesi["id"], "foto": foto}, ke_tamu=False)
        _jadwalkan(_upload_foto, foto, sesi)
        jumlah += 1
    return jumlah


# ------------------------------------------------------------------ proses


def _proses_foto(path: Path) -> bool:
    """Proses satu berkas yang jatuh ke tether_dropbox. Returns True kalau
    berkas sudah beres (tercatat atau diamankan) dan tidak perlu dilihat lagi."""
    kunci_path = str(path)
    identitas = _identitas(path)
    with _kunci:
        if kunci_path in _sedang_diproses:
            return False
        if identitas and _sumber_selesai.get(kunci_path) == identitas:
            return True
        _sedang_diproses.add(kunci_path)
    beres = False
    try:
        beres = _proses_foto_inti(path)
    except Exception as e:
        log.exception("Gagal memproses %s: %s", path.name, e)
        peristiwa.kirim({"jenis": "foto_dilewati", "nama": path.name, "alasan": str(e)[:160]}, ke_tamu=False)
    finally:
        with _kunci:
            _sedang_diproses.discard(kunci_path)
            if beres:
                _sumber_selesai[kunci_path] = _identitas(path) or identitas or (0, 0.0)
    return beres


def _proses_foto_inti(path: Path) -> bool:
    nama = path.name
    log.info("Foto baru terdeteksi: %s", nama)

    if not _tunggu_stabil(path):
        log.warning("Berkas belum stabil dalam %.0f detik: %s — dicoba lagi oleh penjaga.", STABIL_TIMEOUT, nama)
        peristiwa.kirim({"jenis": "foto_dilewati", "nama": nama,
                         "alasan": f"berkas belum selesai ditulis setelah {STABIL_TIMEOUT:.0f} detik"}, ke_tamu=False)
        return False
    if not path.exists():
        return True

    sesi, alasan = _sesi_tujuan()
    if sesi is None:
        aman_dir = ARCHIVE_DIR / FOLDER_TANPA_SESI
        aman_dir.mkdir(parents=True, exist_ok=True)
        dest = _nama_bebas(aman_dir / nama)
        _salin_atomik(path, dest)
        log.warning("Tidak ada sesi aktif — %s diamankan ke %s", nama, dest)
        peristiwa.kirim({"jenis": "foto_tanpa_sesi", "nama": nama, "jumlah": jumlah_tanpa_sesi()}, ke_tamu=False)
        return True

    session_code, session_id = sesi["session_code"], sesi["id"]
    archive_dir = ARCHIVE_DIR / session_code
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / nama

    tercatat = db.foto_dari_path(str(dest))
    if tercatat:
        # Nama sama sudah tercatat: laporan ganda watchdog untuk berkas yang sama
        # (ukuran sama) dilewati; berkas berbeda dengan nama sama (kartu diformat,
        # penomoran kamera kembali ke awal) diberi akhiran dan diproses.
        try:
            sama = dest.exists() and dest.stat().st_size == path.stat().st_size
        except OSError:
            sama = False
        if sama:
            log.info("Sudah tercatat, dilewati: %s", dest)
            return True
        dest = _nama_bebas(dest)
    elif dest.exists():
        dest = _nama_bebas(dest)

    _salin_atomik(path, dest)
    log.info("Disalin ke arsip: %s", dest)

    foto_id = db.catat_foto(session_id, str(dest))
    _buat_thumbnail(dest, session_code)
    foto = db.ambil_foto(foto_id)

    if alasan == "tenggang":
        log.info("Sesi %s sudah diakhiri; %s masih dihitung miliknya (tenggang %.0f detik)",
                 session_code, nama, TENGGANG_SETELAH_SELESAI)

    peristiwa.kirim({
        "jenis": "foto_baru", "session_id": session_id, "session_code": session_code,
        "foto": foto, "setelah_selesai": alasan == "tenggang",
    }, ke_tamu=False)
    peristiwa.kirim({"jenis": "foto_baru", "session_id": session_id}, ke_operator=False)

    _jadwalkan(_upload_foto, foto, sesi)
    return True


def _nama_bebas(dest: Path) -> Path:
    """IMG_0041.JPG yang sudah ada menjadi IMG_0041_2.JPG, dan seterusnya."""
    if not dest.exists():
        return dest
    n = 2
    while True:
        calon = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        if not calon.exists():
            return calon
        n += 1


def _upload_foto(foto: dict, sesi: dict) -> None:
    """Pastikan folder Drive lalu upload dengan retry. Kalau Drive belum bisa,
    foto tetap pending dan operator diberi tahu; penjaga mencobanya lagi."""
    with _kunci:
        if foto["id"] in _sedang_diupload:
            return
        _sedang_diupload.add(foto["id"])
    try:
        sesi = pasang_drive(sesi) or sesi
        folder_id = sesi.get("drive_folder_id")
        if not folder_id:
            log.warning("Sesi %s belum punya folder Drive — %s menunggu.",
                        sesi["session_code"], Path(foto["local_path"]).name)
            peristiwa.kirim({"jenis": "foto_menunggu_drive", "session_id": sesi["id"],
                             "foto_id": foto["id"]}, ke_tamu=False)
            return
        _upload_dengan_retry(foto["id"], foto["local_path"], folder_id, sesi["id"])
    finally:
        with _kunci:
            _sedang_diupload.discard(foto["id"])


def _upload_dengan_retry(foto_id: int, path: str, folder_id: str, session_id: int) -> None:
    """Percobaan pertama plus retry dengan jeda RETRY_DELAYS. Tidak ada jeda
    setelah percobaan terakhir; retry_count = jumlah pengulangan."""
    percobaan = len(RETRY_DELAYS) + 1
    for i in range(percobaan):
        hasil = drive_client.upload_foto(path, folder_id, cek_dulu=i > 0)
        if hasil:
            db.tandai_foto_uploaded(foto_id, hasil["id"])
            peristiwa.kirim({"jenis": "foto_uploaded", "session_id": session_id,
                             "foto_id": foto_id, "foto": db.ambil_foto(foto_id)}, ke_tamu=False)
            peristiwa.kirim({"jenis": "foto_uploaded", "session_id": session_id}, ke_operator=False)
            return
        if i < len(RETRY_DELAYS):
            delay = RETRY_DELAYS[i]
            log.warning("Upload gagal (percobaan %d/%d), coba lagi dalam %d detik: %s",
                        i + 1, percobaan, delay, Path(path).name)
            db.tambah_retry(foto_id)
            time.sleep(delay)

    db.tandai_foto_gagal(foto_id)
    peristiwa.kirim({"jenis": "foto_gagal", "session_id": session_id,
                     "foto_id": foto_id, "foto": db.ambil_foto(foto_id)}, ke_tamu=False)
    log.error("Upload gagal setelah %d percobaan: %s", percobaan, path)


# ------------------------------------------------------------- watchdog


class _PemantauFoto(FileSystemEventHandler):
    """Hanya peduli berkas dengan ekstensi foto di bawah folder tether
    (subfolder ikut, sebagian aplikasi tethering membuat folder per sesi).
    `on_moved` ikut ditangani karena sebagian aplikasi menulis ke nama
    sementara lalu me-rename; tanpa ini jepretan itu tidak pernah terlihat."""

    def _tangani(self, src: str) -> None:
        path = Path(src)
        if path.suffix.lower() not in FOTO_EXT:
            return
        try:
            path.resolve().relative_to(TETHER_DIR)
        except (OSError, ValueError):
            return
        threading.Thread(target=_aman, args=(_proses_foto, path), daemon=True,
                         name=f"foto-{path.name}").start()

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._tangani(event.src_path)

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._tangani(event.dest_path)


def mulai() -> bool:
    """Mulai pemantau folder dan penjaga latar. Dipanggil di lifespan server."""
    global _observer, _berjalan

    for d in (TETHER_DIR, ARCHIVE_DIR, THUMBS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if _berjalan:
        return True
    try:
        _observer = Observer()
        _observer.schedule(_PemantauFoto(), str(TETHER_DIR), recursive=True)
        _observer.start()
        _berjalan = True
        log.info("Watcher dimulai — memantau %s", TETHER_DIR)
    except Exception as e:
        log.error("Gagal memulai watcher: %s", e)
        return False

    _penjaga_stop.clear()
    threading.Thread(target=_penjaga, name="penjaga", daemon=True).start()
    return True


def berhenti() -> None:
    global _observer, _berjalan
    _penjaga_stop.set()
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
    _berjalan = False
    log.info("Watcher dihentikan.")


def sedang_berjalan() -> bool:
    return _berjalan


# ------------------------------------------------------------ pemulihan


def _batas_waktu_tether() -> float | None:
    """Berkas di tether_dropbox yang lebih tua dari batas ini dianggap milik
    acara sebelumnya. Aplikasi tethering menumpuk semua jepretan di folder itu
    dan watcher tidak pernah menghapus, jadi tanpa batas ini restart di tengah
    acara akan menempelkan ratusan foto lama ke sesi yang sedang berjalan."""
    sesi = db.sesi_aktif() or db.sesi_terakhir_selesai()
    if not sesi:
        return None
    acuan = sesi["started_at"] if sesi["status"] == "active" else (sesi.get("finished_at") or sesi["started_at"])
    try:
        return datetime.fromisoformat(acuan).timestamp()
    except ValueError:
        return None


def _waktu_mendarat(p: Path) -> float:
    """Kapan berkas mendarat di laptop: yang terbaru dari mtime dan ctime —
    sebagian aplikasi transfer mewarisi mtime dari jam kamera yang bisa salah."""
    st = p.stat()
    return max(st.st_mtime, st.st_ctime)


def berkas_menunggu() -> list[Path]:
    """Berkas foto di tether_dropbox yang belum beres dan lebih baru daripada
    sesi terakhir — kandidat yang masih perlu diproses."""
    if not TETHER_DIR.exists():
        return []
    batas = _batas_waktu_tether()
    hasil = []
    with _kunci:
        selesai = dict(_sumber_selesai)
        diproses = set(_sedang_diproses)
    for p in TETHER_DIR.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in FOTO_EXT:
            continue
        k = str(p)
        if k in diproses:
            continue
        ident = _identitas(p)
        if ident and selesai.get(k) == ident:
            continue
        try:
            if batas is not None and _waktu_mendarat(p) < batas:
                continue
        except OSError:
            continue
        hasil.append(p)
    return hasil


def pulihkan() -> dict:
    """Dipanggil sekali saat server naik.

    * Foto `pending` diantrekan lagi — upload yang terpotong restart tidak
      pernah ditandai apa pun, jadi tanpa ini ia menggantung selamanya.
    * Berkas di tether_dropbox yang lebih baru daripada awal sesi aktif
      diproses (server mati di tengah sesi). Tanpa sesi aktif, dibiarkan dan
      jumlahnya dilaporkan di pemeriksaan awal.
    """
    pending = db.foto_berstatus("pending")
    diulang = 0
    for foto in pending:
        if not Path(foto["local_path"]).exists():
            db.tandai_foto_gagal(foto["id"])
            continue
        try:
            sesi = db.ambil_sesi(foto["session_id"])
        except db.GalatDB:
            continue
        _jadwalkan(_upload_foto, foto, sesi)
        diulang += 1

    tertinggal = berkas_menunggu()
    diproses = 0
    if tertinggal and db.sesi_aktif():
        for p in tertinggal:
            threading.Thread(target=_aman, args=(_proses_foto, p), daemon=True).start()
            diproses += 1

    if pending or tertinggal:
        log.info("Pemulihan: %d foto pending diulang, %d berkas di tether (%d diproses)",
                 diulang, len(tertinggal), diproses)
    return {"pending_diulang": diulang, "tether_tertinggal": len(tertinggal), "tether_diproses": diproses}


def _penjaga() -> None:
    """Loop latar: sapu berkas tether yang terlewat selama ada sesi aktif, dan
    ulangi upload yang gagal/menggantung begitu Drive terjangkau."""
    while not _penjaga_stop.wait(PENJAGA_DETIK):
        try:
            if db.sesi_aktif():
                for p in berkas_menunggu():
                    threading.Thread(target=_aman, args=(_proses_foto, p), daemon=True).start()
            sisa = db.sesi_dengan_sisa()
            if sisa and drive_client.terhubung():
                for sesi in sisa:
                    dipasang = pasang_drive(sesi)
                    if dipasang and dipasang.get("drive_folder_id"):
                        n = _antre_sisa(dipasang)
                        if n:
                            log.info("Penjaga: %d foto sesi %s diantrekan lagi.", n, sesi["session_code"])
        except Exception as e:  # pragma: no cover
            log.exception("Penjaga gagal satu putaran: %s", e)


# ------------------------------------------------------------- statistik


def berkas_di_tether() -> int:
    try:
        return sum(1 for p in TETHER_DIR.rglob("*") if p.is_file() and p.suffix.lower() in FOTO_EXT)
    except OSError:
        return 0


def jumlah_tanpa_sesi() -> int:
    """Berkas di _tanpa_sesi yang lebih baru daripada pengakuan terakhir operator
    (tombol Mengerti) — jepretan uji sebelum acara tidak boleh menetap sebagai
    pita kuning sepanjang hari."""
    d = ARCHIVE_DIR / FOLDER_TANPA_SESI
    if not d.exists():
        return 0
    try:
        batas = float(db.ambil_pengaturan("tanpa_sesi_diakui_at") or 0)
    except ValueError:
        batas = 0.0
    try:
        return sum(1 for p in d.iterdir()
                   if p.is_file() and not p.name.endswith(".part") and p.stat().st_mtime > batas)
    except OSError:
        return 0


def akui_tanpa_sesi() -> None:
    db.simpan_pengaturan("tanpa_sesi_diakui_at", str(time.time()))


def statistik() -> dict:
    with _kunci:
        n_upload = len(_sedang_diupload)
        n_proses = len(_sedang_diproses)
    return {
        "upload_berjalan": n_upload, "sedang_diproses": n_proses,
        "berkas_di_tether": berkas_di_tether(), "berkas_menunggu": len(berkas_menunggu()),
        "foto_tanpa_sesi": jumlah_tanpa_sesi(),
    }


# ----------------------------------------------------------------- retry


def retry_foto(foto_id: int) -> tuple[bool, str]:
    """Upload ulang satu foto. Hanya `failed`, atau `pending` yang tidak
    sedang diupload (menggantung). Foto yang sudah `uploaded` ditolak supaya
    Drive tidak berisi duplikat."""
    foto = db.ambil_foto(foto_id)
    if not foto:
        return False, "tidak_ada"
    if foto["status"] == "uploaded":
        return False, "sudah_terupload"
    with _kunci:
        if foto_id in _sedang_diupload:
            return False, "sedang_diupload"
    try:
        sesi = db.ambil_sesi(foto["session_id"])
    except db.GalatDB:
        return False, "tidak_ada"
    if not Path(foto["local_path"]).exists():
        db.tandai_foto_gagal(foto_id)
        return False, "berkas_hilang"

    db.reset_foto_status(foto_id)
    foto = db.ambil_foto(foto_id)
    peristiwa.kirim({"jenis": "foto_retry", "session_id": sesi["id"], "foto": foto}, ke_tamu=False)
    _jadwalkan(_upload_foto, foto, sesi)
    return True, "ok"


def retry_semua_gagal(session_id: int) -> dict:
    """Upload ulang semua foto `failed` dan `pending` yang menggantung di satu
    sesi — tombol "Upload sisanya" di Riwayat dan "Coba lagi semuanya" di
    layar sesi."""
    try:
        sesi = db.ambil_sesi(session_id)
    except db.GalatDB:
        return {"ok": False, "jumlah_retry": 0, "alasan": "tidak_ada"}
    return {"ok": True, "jumlah_retry": _antre_sisa(sesi)}
