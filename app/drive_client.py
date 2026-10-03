"""Klien Google Drive (arsitektur-sistem-photobooth.md §3).

OAuth dengan scope `drive.file` saja — aplikasi hanya bisa melihat folder
dan berkas yang ia buat sendiri, bukan seluruh isi Drive (arsitektur §7).

Alur:
  1. Buat folder per sesi saat operator menekan Mulai Sesi.
  2. Set izin *anyone with link = viewer*.
  3. Upload foto ke folder sesi.
  4. Retry dilakukan watcher; modul ini hanya melapor sukses/gagal.

Kredensial:
  credentials.json — OAuth client (Desktop app) dari Google Cloud Console.
  token.json      — dibuat saat login pertama lewat tombol di Pengaturan.

Aturan yang membentuk modul ini:

* **Tidak ada browser yang terbuka di tengah request.** `status()`,
  `terhubung()`, dan semua operasi Drive hanya memakai token yang sudah ada.
  Login interaktif dijalankan terpisah lewat `login_mulai()` di thread latar.
* **Tidak ada I/O jaringan di bawah kunci.** Kunci hanya menukar objek
  kredensial; refresh token dan semua panggilan API punya batas waktu pendek
  supaya wifi venue yang setengah mati tidak membekukan preflight dan upload.
* **Folder induk harus milik aplikasi.** Dengan scope `drive.file`, folder
  yang dibuat operator lewat browser tidak terlihat oleh aplikasi. Kalau
  `DRIVE_PARENT_FOLDER_ID` diisi dan bisa diakses, ia dipakai; kalau kosong
  atau ditolak, aplikasi memakai (atau membuat) folder induknya sendiri di
  akar Drive dan mengingat ID-nya di tabel `pengaturan`.
* **Mode palsu untuk uji.** `MCF_DRIVE_PALSU=1` mengganti seluruh Drive
  dengan tiruan dalam memori — folder dan upload dicatat, tidak ada jaringan —
  supaya alur upload, QR, dan balapan bisa diuji tanpa kredensial.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from pathlib import Path

from . import db
from .jalur import AKAR, env_bool, env_float, path_env

log = logging.getLogger(__name__)

# Pet Blessing hari-H: foto dan sertifikat ditulis ke folder Drive milik
# panitia ("Raw Photo Pet Blessings" dan "Sertifikat Pet Blessing"). Folder yang
# bukan buatan aplikasi hanya bisa ditulisi dengan scope drive penuh, jadi scope
# itu dipakai HANYA kalau ID folder ini diisi. Setelah diisi, login Google di
# Pengaturan harus diulang (token lama ber-scope drive.file).
FOLDER_RAW_ID = os.environ.get("DRIVE_FOLDER_RAW_ID", "").strip()
FOLDER_SERTIFIKAT_ID = os.environ.get("DRIVE_FOLDER_SERTIFIKAT_ID", "").strip()
SCOPES = ["https://www.googleapis.com/auth/drive" if (FOLDER_RAW_ID or FOLDER_SERTIFIKAT_ID)
          else "https://www.googleapis.com/auth/drive.file"]
CRED_PATH = path_env("GOOGLE_CREDENTIALS", AKAR / "credentials.json")
TOKEN_PATH = path_env("GOOGLE_TOKEN", AKAR / "token.json")

PARENT_FOLDER_ID = os.environ.get("DRIVE_PARENT_FOLDER_ID", "").strip()
NAMA_ROOT = os.environ.get("DRIVE_ROOT_NAME", "MCF Photobooth").strip() or "MCF Photobooth"
NAMA_FOLDER_QR = os.environ.get("DRIVE_FOLDER_QR", "1. QR").strip()
NAMA_FOLDER_RESULT = os.environ.get("DRIVE_FOLDER_RESULT", "2. Result").strip()
NAMA_FOLDER_SERTIFIKAT = os.environ.get("DRIVE_FOLDER_SERTIFIKAT", "3. Sertifikat").strip() or "3. Sertifikat"
HTTP_TIMEOUT = env_float("DRIVE_HTTP_TIMEOUT", 20)
LOGIN_TIMEOUT = env_float("DRIVE_LOGIN_TIMEOUT", 240)
JEDA_CEK_KEMBAR = env_float("DRIVE_JEDA_CEK_KEMBAR", 1.5)
PALSU = env_bool("MCF_DRIVE_PALSU", False)
# Mode palsu: kalau berkas ini ada, semua operasi Drive gagal seolah wifi putus.
PALSU_SAKLAR_MATI = path_env("MCF_DRIVE_PALSU_SAKLAR", AKAR / "drive-palsu-mati")

MIME_FOLDER = "application/vnd.google-apps.folder"

_lokal = threading.local()
_kunci = threading.Lock()
_creds = None
_creds_alasan = "belum_dicek"

_cache_status: tuple[float, dict] | None = None
_cache_internet: tuple[float, bool] | None = None

_login_hasil: dict = {"berjalan": False, "hasil": None, "pesan": ""}


# ------------------------------------------------------------------ jaringan


def internet_ok(paksa: bool = False) -> bool:
    """Sambungan TCP ringan ke Google, di-cache 10 detik (design.md §4.1)."""
    global _cache_internet
    if PALSU:
        return not _palsu.mati()
    if not paksa and _cache_internet and time.time() - _cache_internet[0] < 10:
        return _cache_internet[1]
    try:
        with socket.create_connection(("www.googleapis.com", 443), timeout=2.5):
            ok = True
    except OSError:
        ok = False
    _cache_internet = (time.time(), ok)
    return ok


# ================================================================ mode palsu


class _DrivePalsu:
    """Tiruan Drive dalam memori. Jeda kecil di tiap operasi memperlebar
    jendela balapan supaya uji paralel benar-benar menguji kuncinya."""

    def __init__(self) -> None:
        self.kunci = threading.Lock()
        self.jeda = env_float("MCF_DRIVE_PALSU_JEDA", 0.2)
        self.gagal_sisa = int(env_float("MCF_DRIVE_PALSU_GAGAL", 0))
        self.folder: dict[str, dict] = {}          # id → {"nama", "parent"}
        self.berkas: dict[str, list[str]] = {}     # folder_id → nama berkas
        self.berkas_id: dict[str, dict] = {}       # file_id → {"nama", "parent", "sumber"}
        self.n_folder_sesi = 0
        self.n_upload = 0
        self.n_upload_gagal = 0

    def mati(self) -> bool:
        return PALSU_SAKLAR_MATI.exists()

    def buat_folder(self, nama: str, parent: str | None) -> dict:
        time.sleep(self.jeda)
        with self.kunci:
            fid = f"palsu-{len(self.folder) + 1}"
            self.folder[fid] = {"nama": nama, "parent": parent}
            self.berkas.setdefault(fid, [])
            return {"id": fid, "webViewLink": f"https://drive.google.com/drive/folders/{fid}"}

    def upload(self, folder_id: str, nama: str, sumber: str | None = None) -> dict | None:
        time.sleep(self.jeda / 2)
        with self.kunci:
            # Kegagalan yang disengaja hanya untuk foto — salinan QR ke "1. QR"
            # memang usaha terbaik tanpa retry.
            if self.gagal_sisa > 0 and folder_id != "palsu-qr":
                self.gagal_sisa -= 1
                self.n_upload_gagal += 1
                return None
            self.n_upload += 1
            self.berkas.setdefault(folder_id, []).append(nama)
            self.berkas_id[f"berkas-{self.n_upload}"] = {"nama": nama, "parent": folder_id, "sumber": sumber}
            return {"id": f"berkas-{self.n_upload}", "webViewLink": f"https://drive.google.com/file/d/berkas-{self.n_upload}"}

    def pindah(self, file_id: str, ke: str, nama: str | None = None) -> bool:
        with self.kunci:
            b = self.berkas_id.get(file_id)
            if not b:
                return False
            if b["nama"] in self.berkas.get(b["parent"], []):
                self.berkas[b["parent"]].remove(b["nama"])
            b["parent"], b["nama"] = ke, nama or b["nama"]
            self.berkas.setdefault(ke, []).append(b["nama"])
            return True

    def statistik(self) -> dict:
        with self.kunci:
            sesi = {fid: list(n) for fid, n in self.berkas.items()
                    if self.folder.get(fid, {}).get("parent") == "palsu-result"}
            def jalur(fid: str) -> str:
                f = self.folder.get(fid)
                if not f:
                    return fid
                return (jalur(f["parent"]) + "/" if f.get("parent") else "") + f["nama"]
            return {
                "pohon": sorted(jalur(fid) + "/" + n for fid, ns in self.berkas.items() for n in ns),
                "folder_sesi_dibuat": self.n_folder_sesi,
                "upload_sukses": self.n_upload,
                "upload_gagal": self.n_upload_gagal,
                "berkas_per_folder_sesi": sesi,
                "berkas_sertifikat": list(self.berkas.get("palsu-sertifikat", [])),
            }


_palsu = _DrivePalsu() if PALSU else None


# ---------------------------------------------------------------- kredensial


def _tulis_token(creds) -> None:
    TOKEN_PATH.write_text(creds.to_json())
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass


class _RequestBerbatas:
    """Transport refresh token dengan batas waktu — google-auth memanggil
    transport tanpa timeout, dan wifi venue yang menerima SYN tapi tidak
    menjawab bisa menggantung sampai dua menit."""

    def __init__(self) -> None:
        from google.auth.transport.requests import Request
        self._req = Request()

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kw):
        return self._req(url, method=method, body=body, headers=headers,
                         timeout=timeout or HTTP_TIMEOUT, **kw)


def _muat_kredensial():
    """Kredensial dari token.json, di-refresh kalau kedaluwarsa. Tidak pernah
    membuka browser, dan refresh dijalankan di luar kunci."""
    global _creds, _creds_alasan
    from google.oauth2.credentials import Credentials

    with _kunci:
        creds = _creds
    if creds is not None and creds.valid:
        return creds

    if not CRED_PATH.exists():
        with _kunci:
            _creds_alasan, _creds = "tanpa_credentials", None
        return None
    if not TOKEN_PATH.exists():
        with _kunci:
            _creds_alasan, _creds = "belum_login", None
        return None

    if creds is None:
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            log.warning("token.json rusak: %s", e)
            with _kunci:
                _creds_alasan, _creds = "belum_login", None
            return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(_RequestBerbatas())
            _tulis_token(creds)
        except Exception as e:
            teks = str(e)
            if "invalid_grant" in teks or "invalid_client" in teks or "unauthorized" in teks.lower():
                alasan = "token_kedaluwarsa"
            elif not internet_ok():
                alasan = "offline"
            else:
                alasan = "galat"
            log.warning("Refresh token gagal (%s): %s", alasan, teks[:160])
            with _kunci:
                _creds_alasan = alasan
                # Kredensial tetap disimpan kalau cuma soal jaringan: percobaan
                # berikutnya cukup refresh lagi, tidak perlu login ulang.
                _creds = creds if alasan in ("offline", "galat") else None
            return None

    if not creds.valid:
        with _kunci:
            _creds_alasan, _creds = "token_kedaluwarsa", None
        return None

    with _kunci:
        _creds_alasan, _creds = "ok", creds
    return creds


def _svc():
    """Service Drive v3 per thread dengan batas waktu HTTP. httplib2 di balik
    googleapiclient tidak thread-safe, sementara beberapa upload berjalan
    bersamaan."""
    creds = _muat_kredensial()
    if creds is None:
        return None
    svc = getattr(_lokal, "svc", None)
    if svc is None or getattr(_lokal, "creds", None) is not creds:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        dasar = httplib2.Http(timeout=HTTP_TIMEOUT)
        # 308 dari Drive berarti "lanjutkan upload", bukan pindah alamat. Tanpa ini
        # berkas yang lebih besar dari satu potongan (4 MB) selalu gagal diupload.
        dasar.redirect_codes = dasar.redirect_codes - {308}
        http = AuthorizedHttp(creds, http=dasar)
        svc = build("drive", "v3", http=http, cache_discovery=False)
        _lokal.svc = svc
        _lokal.creds = creds
    return svc


def reset_service() -> None:
    """Lupakan kredensial yang di-cache — dipanggil setelah login/logout."""
    global _creds, _cache_status
    with _kunci:
        _creds = None
        _cache_status = None
    if hasattr(_lokal, "svc"):
        del _lokal.svc


# -------------------------------------------------------------------- status


def status(paksa: bool = False) -> dict:
    """Keadaan sambungan Drive untuk pemeriksaan awal dan Pengaturan.

    keadaan: terhubung | belum_login | token_kedaluwarsa | tanpa_credentials |
             offline | galat
    """
    global _cache_status
    if PALSU:
        mati = _palsu.mati()
        return {"keadaan": "offline" if mati else "terhubung",
                "email": None if mati else "drive-palsu@example.com", "nama": "Drive palsu",
                "pesan": "Mode uji: saklar mati aktif." if mati else "Mode uji: Drive tiruan dalam memori.",
                "login_berjalan": False, "credentials_ada": True, "token_ada": True, "palsu": True}
    if not paksa and _cache_status and time.time() - _cache_status[0] < 15:
        return _cache_status[1]

    hasil: dict = {
        "keadaan": "galat", "email": None, "nama": None, "pesan": "",
        "login_berjalan": _login_hasil["berjalan"],
        "credentials_ada": CRED_PATH.exists(), "token_ada": TOKEN_PATH.exists(),
    }
    if not (CRED_PATH.exists() and TOKEN_PATH.exists()) or not internet_ok():
        # Jalur cepat: tanpa berkas, atau tanpa internet, tidak perlu menyentuh Google.
        if not CRED_PATH.exists():
            hasil.update(keadaan="tanpa_credentials", pesan=f"credentials.json tidak ditemukan di {CRED_PATH}.")
        elif not TOKEN_PATH.exists():
            hasil.update(keadaan="belum_login", pesan="Belum pernah login. Tekan Login Google di Pengaturan.")
        else:
            hasil.update(keadaan="offline", pesan="Tidak ada koneksi internet. Foto diarsipkan dan diupload begitu tersambung.")
        _cache_status = (time.time(), hasil)
        return hasil

    svc = _svc()
    if svc is None:
        hasil["keadaan"] = _creds_alasan if _creds_alasan != "ok" else "galat"
        hasil["pesan"] = {
            "tanpa_credentials": f"credentials.json tidak ditemukan di {CRED_PATH}.",
            "belum_login": "Belum pernah login. Tekan Login Google di Pengaturan.",
            "token_kedaluwarsa": "Token ditolak Google. Tekan Login Google untuk login ulang.",
            "offline": "Tidak ada koneksi internet. Foto diarsipkan dan diupload begitu tersambung.",
            "galat": "Google tidak menjawab. Coba lagi sebentar.",
        }.get(hasil["keadaan"], "")
    else:
        try:
            about = svc.about().get(fields="user").execute()
            user = about.get("user", {})
            hasil.update(keadaan="terhubung", email=user.get("emailAddress"), nama=user.get("displayName"))
        except Exception as e:
            teks = str(e)
            if "invalid_grant" in teks or "401" in teks:
                hasil.update(keadaan="token_kedaluwarsa", pesan="Token ditolak Google. Tekan Login Google untuk login ulang.")
                reset_service()
            elif not internet_ok(paksa=True):
                hasil.update(keadaan="offline", pesan="Tidak ada koneksi internet.")
            else:
                hasil.update(keadaan="galat", pesan=teks[:200])
            log.warning("Drive tidak terhubung: %s", teks[:200])

    _cache_status = (time.time(), hasil)
    return hasil


def terhubung() -> bool:
    return status()["keadaan"] == "terhubung"


def info_akun() -> dict | None:
    """Email dan kuota Drive."""
    if PALSU:
        gb = 1024 ** 3
        return {"email": "drive-palsu@example.com", "nama": "Drive palsu",
                "kuota_total": 15 * gb, "kuota_terpakai": 3 * gb, "kuota_sisa": 12 * gb}
    try:
        svc = _svc()
        if svc is None:
            return None
        about = svc.about().get(fields="user,storageQuota").execute()
        user = about.get("user", {})
        quota = about.get("storageQuota", {})
        limit = int(quota.get("limit", 0) or 0)
        usage = int(quota.get("usage", 0) or 0)
        return {
            "email": user.get("emailAddress", ""), "nama": user.get("displayName", ""),
            "kuota_total": limit, "kuota_terpakai": usage,
            "kuota_sisa": max(0, limit - usage) if limit else None,
        }
    except Exception as e:
        log.warning("Gagal ambil info akun: %s", e)
        return None


def kuota() -> dict | None:
    info = info_akun()
    if not info:
        return None
    return {"total": info["kuota_total"], "terpakai": info["kuota_terpakai"], "sisa": info["kuota_sisa"]}


# --------------------------------------------------------------------- login


def login_mulai() -> dict:
    """Jalankan alur OAuth di thread latar. Browser bawaan laptop terbuka;
    setelah operator mengizinkan, token.json ditulis dan sambungan diuji.
    Ada batas waktu supaya tab yang ditutup tidak mengunci tombol selamanya."""
    if PALSU:
        return {"ok": True, "pesan": "Mode uji: Drive palsu selalu terhubung."}
    if not CRED_PATH.exists():
        return {"ok": False, "pesan": f"credentials.json tidak ditemukan di {CRED_PATH}."}
    with _kunci:
        if _login_hasil["berjalan"]:
            return {"ok": True, "pesan": "Login sudah berjalan — periksa jendela browser."}
        _login_hasil.update(berjalan=True, hasil=None, pesan="Menunggu izin di browser…")

    def jalan() -> None:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
            creds = flow.run_local_server(
                port=0, open_browser=True, timeout_seconds=int(LOGIN_TIMEOUT),
                authorization_prompt_message="",
                success_message="Login berhasil. Tab ini boleh ditutup, kembali ke MCF Photobooth.",
            )
            _tulis_token(creds)
            reset_service()
            st = status(paksa=True)
            if st["keadaan"] == "terhubung":
                _login_hasil.update(hasil="ok", pesan=f"Terhubung sebagai {st['email']}.")
            else:
                _login_hasil.update(hasil="gagal", pesan=st.get("pesan") or "Token tersimpan tapi Drive belum menjawab.")
        except Exception as e:
            teks = str(e)
            if "timed out" in teks.lower() or "timeout" in teks.lower() or isinstance(e, TimeoutError):
                teks = f"Waktu login habis ({int(LOGIN_TIMEOUT)} detik). Tekan Login Google lagi."
            log.error("Login Google gagal: %s", teks[:200])
            _login_hasil.update(hasil="gagal", pesan=teks[:200])
        finally:
            _login_hasil["berjalan"] = False
            try:
                from . import peristiwa
                peristiwa.kirim({"jenis": "drive_status", "status": status()}, ke_tamu=False)
            except Exception:
                pass

    threading.Thread(target=jalan, name="drive-login", daemon=True).start()
    return {"ok": True, "pesan": "Browser dibuka. Pilih akun Drive yang akan menampung foto."}


def login_keadaan() -> dict:
    return dict(_login_hasil)


def logout() -> dict:
    """Hapus token.json — dipakai tombol Ganti akun. ID folder yang diingat
    ikut dilupakan; folder induk bernama sama dicari lagi saat login berikutnya
    supaya akun yang sama tidak mendapat dua "MCF Photobooth"."""
    if PALSU:
        return {"ok": True, "pesan": "Mode uji: tidak ada token untuk dihapus."}
    try:
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()
    except OSError as e:
        return {"ok": False, "pesan": str(e)}
    reset_service()
    for kunci in ("drive_root_id", "drive_qr_id", "drive_result_id", "drive_induk_sumber"):
        db.simpan_pengaturan(kunci, None)
    return {"ok": True, "pesan": "Token dihapus. Login lagi untuk memilih akun."}


# ------------------------------------------------------------------- folder


def _folder_bisa_diakses(svc, folder_id: str) -> bool:
    try:
        meta = svc.files().get(fileId=folder_id, fields="id,mimeType,trashed").execute()
        return meta.get("mimeType") == MIME_FOLDER and not meta.get("trashed")
    except Exception as e:
        log.warning("Folder %s tidak bisa diakses dengan scope drive.file: %s", folder_id, str(e)[:120])
        return False


def _buat_folder(svc, nama: str, parent_id: str | None) -> dict:
    meta = {"name": nama, "mimeType": MIME_FOLDER}
    if parent_id:
        meta["parents"] = [parent_id]
    return svc.files().create(body=meta, fields="id,webViewLink").execute()


def _aman_q(teks: str) -> str:
    return teks.replace("\\", "\\\\").replace("'", "\\'")


def _cari_subfolder(svc, parent_id: str, nama: str) -> str | None:
    res = svc.files().list(
        q=f"'{_aman_q(parent_id)}' in parents and name='{_aman_q(nama)}' and mimeType='{MIME_FOLDER}' and trashed=false",
        fields="files(id)", pageSize=1,
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def cari_berkas(folder_id: str, nama: str) -> str | None:
    """ID berkas bernama `nama` di dalam folder — dipakai sebelum upload ulang
    supaya respons yang hilang di jaringan tidak menghasilkan berkas ganda."""
    if PALSU:
        if _palsu.mati():
            return None
        with _palsu.kunci:
            return "ada" if nama in _palsu.berkas.get(folder_id, []) else None
    try:
        svc = _svc()
        if svc is None:
            return None
        res = svc.files().list(
            q=f"'{_aman_q(folder_id)}' in parents and name='{_aman_q(nama)}' and trashed=false",
            fields="files(id)", pageSize=1,
        ).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None
    except Exception as e:
        log.warning("Gagal mencari berkas %s: %s", nama, str(e)[:120])
        return None


def folder_induk() -> dict | None:
    """Folder induk yang benar-benar bisa dipakai, beserta asalnya.

    Returns {"id": ..., "sumber": "env"|"aplikasi"} atau None kalau Drive
    tidak terhubung."""
    if PALSU:
        if "palsu-root" not in _palsu.folder:
            _palsu.folder["palsu-root"] = {"nama": NAMA_ROOT, "parent": None}
        return {"id": "palsu-root", "sumber": "aplikasi"}

    svc = _svc()
    if svc is None:
        return None

    if PARENT_FOLDER_ID:
        if _folder_bisa_diakses(svc, PARENT_FOLDER_ID):
            db.simpan_pengaturan("drive_induk_sumber", "env")
            return {"id": PARENT_FOLDER_ID, "sumber": "env"}
        log.error(
            "DRIVE_PARENT_FOLDER_ID=%s ditolak Drive. Dengan scope drive.file hanya folder "
            "buatan aplikasi yang terlihat — aplikasi memakai folder induknya sendiri.",
            PARENT_FOLDER_ID,
        )

    with _kunci_struktur:
        return _folder_induk_aplikasi(svc)


# Preflight, Mulai Sesi, dan penjaga latar bisa menyiapkan struktur bersamaan.
# Tanpa kunci, masing-masing tidak menemukan folder lalu membuatnya sendiri (folder kembar).
_kunci_struktur = threading.RLock()


def _folder_induk_aplikasi(svc) -> dict | None:
    root_id = db.ambil_pengaturan("drive_root_id")
    if root_id and _folder_bisa_diakses(svc, root_id):
        db.simpan_pengaturan("drive_induk_sumber", "aplikasi")
        return {"id": root_id, "sumber": "aplikasi"}

    try:
        root_id = _cari_subfolder(svc, "root", NAMA_ROOT)
        if root_id:
            log.info("Folder induk '%s' ditemukan lagi di Drive.", NAMA_ROOT)
        else:
            folder = _buat_folder(svc, NAMA_ROOT, None)
            root_id = folder["id"]
            log.info("Folder induk dibuat di Drive: %s → %s", NAMA_ROOT, folder.get("webViewLink"))
    except Exception as e:
        log.error("Gagal menyiapkan folder induk '%s': %s", NAMA_ROOT, e)
        return None
    db.simpan_pengaturan("drive_root_id", root_id)
    db.simpan_pengaturan("drive_induk_sumber", "aplikasi")
    for kunci in ("drive_qr_id", "drive_result_id"):
        db.simpan_pengaturan(kunci, None)
    return {"id": root_id, "sumber": "aplikasi"}


def _subfolder(nama: str, kunci_cache: str) -> str | None:
    """Subfolder bernama `nama` di bawah folder induk, dibuat kalau belum ada.
    ID-nya diingat supaya tidak ada files.list di tiap Mulai Sesi."""
    if PALSU:
        fid = {"drive_qr_id": "palsu-qr", "drive_sertifikat_id": "palsu-sertifikat"}.get(kunci_cache, "palsu-result")
        folder_induk()
        _palsu.folder.setdefault(fid, {"nama": nama, "parent": "palsu-root"})
        _palsu.berkas.setdefault(fid, [])
        return fid

    svc = _svc()
    if svc is None:
        return None
    if not nama:
        induk = folder_induk()
        return induk["id"] if induk else None

    with _kunci_struktur:
        return _subfolder_buat(svc, nama, kunci_cache)


def _subfolder_buat(svc, nama: str, kunci_cache: str) -> str | None:
    cached = db.ambil_pengaturan(kunci_cache)
    if cached and _folder_bisa_diakses(svc, cached):
        return cached

    induk = folder_induk()
    if not induk:
        return None
    try:
        fid = _cari_subfolder(svc, induk["id"], nama)
        if not fid:
            fid = _buat_folder(svc, nama, induk["id"])["id"]
            log.info("Subfolder Drive dibuat: %s", nama)
        db.simpan_pengaturan(kunci_cache, fid)
        return fid
    except Exception as e:
        log.error("Gagal menyiapkan subfolder '%s': %s", nama, e)
        return None


def pastikan_struktur() -> dict | None:
    """Folder induk + subfolder QR dan Result. Dipanggil preflight supaya
    masalah struktur ketahuan sebelum tamu pertama, bukan saat Mulai Sesi."""
    induk = folder_induk()
    if not induk:
        return None
    return {
        "induk": induk["id"], "sumber": induk["sumber"],
        "qr": _subfolder(NAMA_FOLDER_QR, "drive_qr_id"),
        "result": _subfolder(NAMA_FOLDER_RESULT, "drive_result_id"),
    }


_kunci_pemilik = threading.Lock()


def _ganti_nama(svc, fid: str | None, nama: str) -> str | None:
    """Folder yang disiapkan sebelum hari-H diberi nama nomor urut; isi dan link tetap."""
    if fid:
        if PALSU:
            _palsu.folder[fid]["nama"] = nama
        else:
            svc.files().update(fileId=fid, body={"name": nama}).execute()
        log.info("Folder Drive diganti nama: %s", nama)
    return fid


def _cari_palsu(parent: str, nama: str) -> str | None:
    return next((k for k, f in _palsu.folder.items() if f["nama"] == nama and f["parent"] == parent), None)


def _tanpa_kembar(svc, parent: str, nama: str, fid: str) -> str:
    """Kunci di modul ini hanya berlaku di satu laptop. Dua booth yang mulai
    bersamaan bisa sama-sama membuat folder bernama sama, jadi setelah membuat
    folder dicek ulang: yang paling tua dipakai, folder baru milik sendiri
    (masih kosong) dibuang ke Sampah."""
    if PALSU:
        with _palsu.kunci:
            kembar = [k for k, f in _palsu.folder.items() if f["nama"] == nama and f["parent"] == parent]
            if kembar[0] != fid:
                del _palsu.folder[fid]
        return kembar[0]
    time.sleep(JEDA_CEK_KEMBAR)  # beri waktu folder booth lain muncul di pencarian
    res = svc.files().list(
        q=f"'{_aman_q(parent)}' in parents and name='{_aman_q(nama)}' and mimeType='{MIME_FOLDER}' and trashed=false",
        fields="files(id,createdTime)",
    ).execute()
    kembar = sorted(res.get("files", []), key=lambda f: (f["createdTime"], f["id"]))
    if not kembar or kembar[0]["id"] == fid:
        return fid
    svc.files().update(fileId=fid, body={"trashed": True}).execute()
    log.warning("Folder '%s' sudah dibuat booth lain; dipakai yang itu, folder kembar dibuang.", nama)
    return kembar[0]["id"]


def _folder_pemilik(svc, parent: str, nama: str, lama: str | None = None) -> str | None:
    """Folder pengelompokan per pemilik di bawah '2. Result'. Dicari dulu
    (cache di pengaturan, lalu Drive) supaya hewan kedua pemilik yang sama
    masuk folder yang sama, tidak membuat folder kembar."""
    kunci_cache = f"drive_pemilik:{parent}:{nama}"
    with _kunci_pemilik:
        cached = db.ambil_pengaturan(kunci_cache)
        if cached and (PALSU or _folder_bisa_diakses(svc, cached)):
            return cached
        cari = (lambda n: _cari_palsu(parent, n)) if PALSU else (lambda n: _cari_subfolder(svc, parent, n))
        # Folder nomor pendaftaran dicari lebih dulu: nama nomor urut bisa kebetulan sama
        # dengan folder pendaftaran pemilik lain yang bernama sama (dua "Lita").
        fid = (lama and lama != nama and _ganti_nama(svc, cari(lama), nama)) or cari(nama)
        if not fid:
            baru = _palsu.buat_folder(nama, parent) if PALSU else _buat_folder(svc, nama, parent)
            fid = _tanpa_kembar(svc, parent, nama, baru["id"])
        db.simpan_pengaturan(kunci_cache, fid)
        return fid


def buat_folder_sesi(nama_folder: str, induk: str | None = None,
                     lama: str | None = None, induk_lama: str | None = None) -> dict | None:
    """Folder sesi di bawah '2. Result' (atau langsung di bawah induk kalau
    nama subfolder dikosongkan), izin anyone-with-link viewer. `induk` =
    nama folder pengelompokan (Pet Blessing: satu folder per pemilik).

    Returns {"id", "link"} atau None kalau gagal. Pemanggil (watcher) yang
    menjamin fungsi ini dipanggil paling banyak sekali per sesi."""
    if PALSU:
        if _palsu.mati():
            return None
        parent = (induk and FOLDER_RAW_ID) or _subfolder(NAMA_FOLDER_RESULT, "drive_result_id")
        if induk:
            parent = _folder_pemilik(None, parent, induk, induk_lama)
            ada = (lama and _ganti_nama(None, _cari_palsu(parent, lama), nama_folder)) or _cari_palsu(parent, nama_folder)
            if ada:
                return {"id": ada, "link": f"https://drive.google.com/drive/folders/{ada}"}
        f = _palsu.buat_folder(nama_folder, parent)
        with _palsu.kunci:
            _palsu.n_folder_sesi += 1
        return {"id": f["id"], "link": f["webViewLink"]}

    try:
        svc = _svc()
        if svc is None:
            return None
        parent = (induk and FOLDER_RAW_ID) or _subfolder(NAMA_FOLDER_RESULT, "drive_result_id")
        if not parent:
            akar = folder_induk()
            parent = akar["id"] if akar else None
        if induk:
            parent = _folder_pemilik(svc, parent, induk, induk_lama)
            # Pet Blessing: folder hewan bisa sudah disiapkan dari database (nama
            # nomor pendaftaran); pakai itu dan ganti namanya ke nomor urut.
            ada = (lama and _ganti_nama(svc, _cari_subfolder(svc, parent, lama), nama_folder)) \
                or _cari_subfolder(svc, parent, nama_folder)
            if ada:
                return {"id": ada, "link": f"https://drive.google.com/drive/folders/{ada}"}

        folder = _buat_folder(svc, nama_folder, parent)
        folder_id, folder_link = folder["id"], folder["webViewLink"]
        if induk:
            folder_id = _tanpa_kembar(svc, parent, nama_folder, folder_id)
            folder_link = f"https://drive.google.com/drive/folders/{folder_id}"
        svc.permissions().create(
            fileId=folder_id, body={"type": "anyone", "role": "reader"}, fields="id",
        ).execute()
        log.info("Folder Drive dibuat: %s → %s", nama_folder, folder_link)
        return {"id": folder_id, "link": folder_link}
    except Exception as e:
        log.error("Gagal buat folder Drive '%s': %s", nama_folder, str(e)[:200])
        return None


# ------------------------------------------------------------ kotak masuk
# Foto yang dijepret tanpa sesi naik ke '<Raw>/!Need Organized/Camera <booth>'
# dan dipilah belakangan di meja pilah (app/pilah.py).

NAMA_KOTAK = os.environ.get("DRIVE_FOLDER_KOTAK", "").strip() or "!Need Organized"
AWALAN_KAMERA = "Camera "


def _induk_kotak(svc) -> str | None:
    parent = FOLDER_RAW_ID or _subfolder(NAMA_FOLDER_RESULT, "drive_result_id")
    return _folder_pemilik(svc, parent, NAMA_KOTAK) if parent else None


def folder_kotak(booth: str, sub: str | None = None) -> str | None:
    """ID folder penampung satu kamera (dibuat kalau belum ada). `sub` =
    subfolder di dalamnya, misalnya 'Disisihkan'."""
    try:
        svc = None if PALSU else _svc()
        if (not PALSU and svc is None) or (PALSU and _palsu.mati()):
            return None
        induk = _induk_kotak(svc)
        if not induk:
            return None
        fid = _folder_pemilik(svc, induk, AWALAN_KAMERA + booth)
        return _folder_pemilik(svc, fid, sub) if sub else fid
    except Exception as e:
        log.error("Gagal menyiapkan kotak masuk %s: %s", booth, str(e)[:200])
        return None


def kamera_kotak() -> list[dict] | None:
    """Semua folder 'Camera …' di kotak masuk: [{"id", "nama"}]. None = Drive tidak terjangkau."""
    try:
        svc = None if PALSU else _svc()
        if (not PALSU and svc is None) or (PALSU and _palsu.mati()):
            return None
        induk = _induk_kotak(svc)
        if not induk:
            return None
        if PALSU:
            sub = [{"id": k, "name": f["nama"]} for k, f in _palsu.folder.items() if f["parent"] == induk]
        else:
            sub = svc.files().list(
                q=f"'{_aman_q(induk)}' in parents and mimeType='{MIME_FOLDER}' and trashed=false",
                fields="files(id,name)", pageSize=50,
            ).execute().get("files", [])
        return sorted(({"id": f["id"], "nama": f["name"][len(AWALAN_KAMERA):].strip()}
                       for f in sub if f["name"].startswith(AWALAN_KAMERA)), key=lambda k: k["nama"])
    except Exception as e:
        log.warning("Gagal membaca kotak masuk: %s", str(e)[:160])
        return None


def isi_folder(folder_id: str) -> list[dict] | None:
    """Berkas (bukan folder) di satu folder, urut nama: [{"id", "name", "size"}]."""
    if PALSU:
        if _palsu.mati():
            return None
        with _palsu.kunci:
            return sorted(({"id": k, "name": b["nama"], "size": "0"} for k, b in _palsu.berkas_id.items()
                           if b["parent"] == folder_id), key=lambda b: b["name"])
    try:
        svc = _svc()
        if svc is None:
            return None
        hasil, token = [], None
        while True:
            res = svc.files().list(
                q=f"'{_aman_q(folder_id)}' in parents and mimeType!='{MIME_FOLDER}' and trashed=false",
                fields="nextPageToken, files(id,name,size)", orderBy="name", pageSize=200, pageToken=token,
            ).execute()
            hasil += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                return hasil
    except Exception as e:
        log.warning("Gagal membaca isi folder %s: %s", folder_id, str(e)[:160])
        return None


def pindah_berkas(file_id: str, dari: str, ke: str) -> bool:
    """Pindahkan satu berkas antar folder Drive. ID dan tautannya tidak berubah."""
    if PALSU:
        return not _palsu.mati() and _palsu.pindah(file_id, ke)
    try:
        _svc().files().update(fileId=file_id, addParents=ke, removeParents=dari, fields="id").execute()
        return True
    except Exception as e:
        log.error("Gagal memindah berkas %s: %s", file_id, str(e)[:200])
        return False


def buang_berkas(file_id: str) -> bool:
    if PALSU:
        return _palsu.pindah(file_id, "sampah")
    try:
        _svc().files().update(fileId=file_id, body={"trashed": True}).execute()
        return True
    except Exception as e:
        log.warning("Gagal membuang berkas %s: %s", file_id, str(e)[:160])
        return False


def unduh_berkas(file_id: str, tujuan: Path) -> bool:
    """Unduh isi berkas Drive ke `tujuan` (foto dari laptop lain untuk sertifikat)."""
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    part = tujuan.with_name(tujuan.name + ".part")
    try:
        if PALSU:
            sumber = _palsu.berkas_id.get(file_id, {}).get("sumber")
            if not sumber or _palsu.mati():
                return False
            import shutil
            shutil.copyfile(sumber, part)
        else:
            from googleapiclient.http import MediaIoBaseDownload
            with open(part, "wb") as fh:
                unduhan = MediaIoBaseDownload(fh, _svc().files().get_media(fileId=file_id), chunksize=8 * 1024 * 1024)
                selesai = False
                while not selesai:
                    _, selesai = unduhan.next_chunk()
        os.replace(part, tujuan)
        return True
    except Exception as e:
        log.error("Gagal mengunduh berkas %s: %s", file_id, str(e)[:200])
        return False


def thumb_berkas(file_id: str) -> bytes | None:
    """Thumbnail buatan Drive (JPEG) untuk foto yang berkasnya tidak ada di laptop ini."""
    if PALSU:
        return None
    try:
        svc = _svc()
        meta = svc.files().get(fileId=file_id, fields="thumbnailLink").execute()
        link = meta.get("thumbnailLink")
        if not link:
            return None
        resp, isi = svc._http.request(link.rsplit("=", 1)[0] + "=s480")
        return isi if resp.status == 200 else None
    except Exception as e:
        log.warning("Thumbnail Drive %s belum bisa diambil: %s", file_id, str(e)[:120])
        return None


def upload_qr(qr_path: str, nama_file: str) -> dict | None:
    """Simpan salinan QR ke subfolder '1. QR' — cadangan kalau laptop rusak."""
    try:
        parent = _subfolder(NAMA_FOLDER_QR, "drive_qr_id")
        if not parent:
            return None
        return upload_foto(qr_path, parent, nama_file)
    except Exception as e:
        log.error("Gagal upload QR ke Drive: %s", e)
        return None


def folder_sertifikat(nama_pemilik: str, folder_sesi: str | None, lama: str | None = None) -> str | None:
    """Tujuan sertifikat Pet Blessing: folder pemilik di dalam folder
    Sertifikat panitia kalau DRIVE_FOLDER_SERTIFIKAT_ID diisi, selain itu
    folder hewan (folder sesi) itu sendiri."""
    if not FOLDER_SERTIFIKAT_ID:
        return folder_sesi
    try:
        return _folder_pemilik(None if PALSU else _svc(), FOLDER_SERTIFIKAT_ID, nama_pemilik, lama)
    except Exception as e:
        log.error("Gagal menyiapkan folder sertifikat '%s': %s", nama_pemilik, str(e)[:200])
        return None


NAMA_SIAP_CETAK = os.environ.get("DRIVE_FOLDER_SIAP_CETAK", "").strip() or "Sertifikat Siap Cetak (PDF)"
_siap_cetak: dict = {}   # {"id", "link"} folder siap cetak, diingat selama server hidup
_siap_cetak_isi: tuple[float, list] | None = None


def folder_siap_cetak() -> dict | None:
    """Folder "siap cetak" di folder "Hari H" (induk folder Sertifikat panitia): salinan PDF tiap sertifikat untuk
    dicetak fisik, di samping susunan folder yang sudah ada. Susunannya sama dengan folder lain: satu folder per
    pemilik ("027 Nama Pemilik", nomor urut di depan), di dalamnya satu folder per hewan ("027A Nama Hewan (Jenis)").
    {} kalau fitur ini tidak dipakai (tanpa folder Sertifikat panitia, atau Drive palsu untuk uji), None kalau
    Drive tidak menjawab."""
    if PALSU or not FOLDER_SERTIFIKAT_ID:
        return {}
    if _siap_cetak:
        return _siap_cetak
    try:
        svc = _svc()
        if svc is None:
            return None
        induk = svc.files().get(fileId=FOLDER_SERTIFIKAT_ID, fields="parents").execute().get("parents", [None])[0]
        if not induk:
            return {}
        fid = _folder_pemilik(svc, induk, NAMA_SIAP_CETAK)
        if not fid:
            return None
        _siap_cetak.update(id=fid, link=f"https://drive.google.com/drive/folders/{fid}")
        return _siap_cetak
    except Exception as e:
        log.warning("Gagal menyiapkan folder siap cetak: %s", str(e)[:160])
        return None


# PDF siap cetak ditandai properti ini, supaya jumlahnya bisa dihitung dengan satu pencarian walaupun
# berkasnya tersebar di folder pemilik dan hewan.
_TANDA_CETAK = "properties has { key='siap_cetak' and value='1' }"


def upload_siap_cetak(pdf_lokal: str, nama_pemilik: str, nama_hewan: str) -> dict | None:
    """Salin PDF sertifikat ke folder siap cetak / pemilik / hewan. PDF lama hewan itu diganti.
    {} = fitur tidak dipakai, None = belum berhasil (pemanggil mengulang)."""
    global _siap_cetak_isi
    akar = folder_siap_cetak()
    if not akar:
        return akar
    try:
        svc = _svc()
        pemilik = _folder_pemilik(svc, akar["id"], nama_pemilik)
        hewan = pemilik and _folder_pemilik(svc, pemilik, nama_hewan)
        hasil = hewan and upload_sertifikat(pdf_lokal, cek_dulu=True, folder_id=hewan)
        if not hasil:
            return None
        svc.files().update(fileId=hasil["id"], body={"properties": {"siap_cetak": "1"}}, fields="id").execute()
        _siap_cetak_isi = None
        return hasil
    except Exception as e:
        log.warning("PDF siap cetak %s belum naik: %s", Path(pdf_lokal).name, str(e)[:160])
        return None


def isi_siap_cetak() -> list[dict] | None:
    """Semua PDF siap cetak di Drive (dari semua laptop), urut nama = urut nomor urut. None = tidak terbaca."""
    global _siap_cetak_isi
    if _siap_cetak_isi and time.time() - _siap_cetak_isi[0] < 3:
        return _siap_cetak_isi[1]
    if not folder_siap_cetak():
        return None
    try:
        svc = _svc()
        hasil, token = [], None
        while True:
            res = svc.files().list(q=f"{_TANDA_CETAK} and trashed=false", fields="nextPageToken, files(id,name)",
                                   pageSize=1000, pageToken=token).execute()
            hasil += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                break
        hasil.sort(key=lambda b: b["name"])
        _siap_cetak_isi = (time.time(), hasil)
        return hasil
    except Exception as e:
        log.warning("Gagal membaca PDF siap cetak: %s", str(e)[:160])
        return None


def buang_siap_cetak(nama_pdf: str) -> None:
    """Buang PDF siap cetak bernama ini (pemilahan dibatalkan), supaya tidak tercetak."""
    global _siap_cetak_isi
    if not folder_siap_cetak():
        return
    try:
        svc = _svc()
        for b in svc.files().list(q=f"name='{_aman_q(nama_pdf)}' and {_TANDA_CETAK} and trashed=false", fields="files(id)").execute().get("files", []):
            svc.files().update(fileId=b["id"], body={"trashed": True}).execute()
        _siap_cetak_isi = None
    except Exception as e:
        log.warning("PDF siap cetak %s belum terbuang: %s", nama_pdf, str(e)[:160])


def upload_sertifikat(path_lokal: str, cek_dulu: bool = False, folder_id: str | None = None) -> dict | None:
    """Upload sertifikat Pet Blessing ke folder hewannya (`folder_id`, di
    dalam folder pemilik) atau, tanpa folder_id, ke subfolder '3. Sertifikat'.
    Izin baca dibuka per berkas."""
    parent = folder_id or _subfolder(NAMA_FOLDER_SERTIFIKAT, "drive_sertifikat_id")
    if not parent:
        return None
    # Sertifikat hewan yang sama bisa dibuat lagi (sesi ulang, atau booth lain).
    # Yang baru diupload dulu, lalu berkas lama bernama sama dibuang, supaya
    # yang tersimpan selalu sertifikat terbaru dan tidak ada dua berkas kembar.
    lama = None if PALSU else cari_berkas(parent, Path(path_lokal).name)
    hasil = upload_foto(path_lokal, parent, cek_dulu=cek_dulu and not lama)
    if not hasil or PALSU:
        return hasil
    if lama and lama != hasil["id"]:
        try:
            _svc().files().update(fileId=lama, body={"trashed": True}).execute()
            log.info("Sertifikat lama dibuang, diganti yang baru: %s", Path(path_lokal).name)
        except Exception as e:
            log.warning("Sertifikat lama %s belum terbuang: %s", lama, str(e)[:120])
    try:
        svc = _svc()
        svc.permissions().create(
            fileId=hasil["id"], body={"type": "anyone", "role": "reader"}, fields="id",
        ).execute()
        if not hasil.get("link"):
            meta = svc.files().get(fileId=hasil["id"], fields="webViewLink").execute()
            hasil["link"] = meta.get("webViewLink", "")
        return hasil
    except Exception as e:
        log.error("Gagal membuka izin sertifikat %s: %s", path_lokal, str(e)[:200])
        return None


def upload_foto(path_lokal: str, folder_id: str, custom_name: str | None = None,
                cek_dulu: bool = False) -> dict | None:
    """Upload satu berkas ke folder Drive. Returns {"id", "link"} atau None.

    `cek_dulu=True` (dipakai pada percobaan ulang) mencari berkas bernama sama
    di folder itu lebih dulu: upload sebelumnya bisa saja sampai di Google
    tapi responsnya hilang di jaringan."""
    path = Path(path_lokal)
    nama = custom_name or path.name
    if cek_dulu:
        ada = cari_berkas(folder_id, nama)
        if ada:
            log.info("Sudah ada di Drive, tidak diupload lagi: %s", nama)
            return {"id": ada, "link": "", "sudah_ada": True}

    if PALSU:
        if not path.exists() or _palsu.mati():
            return None
        hasil = _palsu.upload(folder_id, nama, str(path))
        return {"id": hasil["id"], "link": hasil["webViewLink"]} if hasil else None

    try:
        svc = _svc()
        if svc is None:
            return None
        from googleapiclient.http import MediaFileUpload

        ext = path.suffix.lower()
        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".tif": "image/tiff", ".tiff": "image/tiff", ".heic": "image/heic",
            ".pdf": "application/pdf",
        }.get(ext, "application/octet-stream")
        media = MediaFileUpload(str(path), mimetype=mime, resumable=True, chunksize=4 * 1024 * 1024)
        meta = {"name": nama, "parents": [folder_id]}
        berkas = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        log.info("Diupload: %s → %s", nama, berkas.get("webViewLink"))
        return {"id": berkas["id"], "link": berkas.get("webViewLink", "")}
    except Exception as e:
        log.error("Gagal upload '%s' ke folder %s: %s", path_lokal, folder_id, str(e)[:200])
        return None


def ringkasan() -> dict:
    """Nilai konfigurasi untuk halaman Pengaturan — tanpa memanggil Drive."""
    hasil = {
        "scope": SCOPES[0].rsplit("/", 1)[-1],
        "credentials_path": str(CRED_PATH), "credentials_ada": CRED_PATH.exists() or PALSU,
        "token_path": str(TOKEN_PATH), "token_ada": TOKEN_PATH.exists() or PALSU,
        "parent_folder_env": PARENT_FOLDER_ID or None,
        "induk_id": (PARENT_FOLDER_ID if db.ambil_pengaturan("drive_induk_sumber") == "env" else db.ambil_pengaturan("drive_root_id")),
        "induk_sumber": db.ambil_pengaturan("drive_induk_sumber"),
        "nama_root": NAMA_ROOT, "folder_qr": NAMA_FOLDER_QR, "folder_result": NAMA_FOLDER_RESULT,
        "http_timeout": HTTP_TIMEOUT, "palsu": PALSU,
    }
    if PALSU:
        hasil["statistik_palsu"] = _palsu.statistik()
    return hasil
