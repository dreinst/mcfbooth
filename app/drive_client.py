"""Klien Google Drive (arsitektur-sistem-photobooth.md §3, langkah 2).

OAuth dengan scope `drive.file` saja — aplikasi hanya bisa melihat folder
dan berkas yang ia buat sendiri, bukan seluruh isi Drive (arsitektur §7).

Alur:
  1. Buat folder per sesi saat operator menekan Mulai Sesi.
  2. Set izin *anyone with link = viewer*.
  3. Upload foto ke folder sesi.
  4. Retry otomatis kalau gagal.

Kredensial:
  credentials.json — OAuth client dari Google Cloud Console.
  token.json      — dibuat otomatis saat login pertama.
"""

from __future__ import annotations

import io
import os
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

log = logging.getLogger(__name__)

AKAR = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CRED_PATH = AKAR / "credentials.json"
TOKEN_PATH = AKAR / "token.json"

# ID folder induk di Drive — diisi dari .env atau langsung di sini.
PARENT_FOLDER_ID = os.environ.get("DRIVE_PARENT_FOLDER_ID", "")


def _dapatkan_kredensial() -> Credentials | None:
    """Dapatkan kredensial OAuth. Buka browser kalau belum pernah login."""
    creds = None

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            log.warning("Token rusak, akan login ulang: %s", e)
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            log.warning("Refresh token gagal: %s", e)
            creds = None

    if not creds or not creds.valid:
        if not CRED_PATH.exists():
            log.error(
                "credentials.json tidak ditemukan di %s. "
                "Unduh dari Google Cloud Console → APIs & Services → Credentials.",
                CRED_PATH,
            )
            return None
        flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
        log.info("Token baru disimpan di %s", TOKEN_PATH)

    return creds


def _bangun_layanan():
    """Bangun service Google Drive API v3."""
    creds = _dapatkan_kredensial()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


# Cache service supaya tidak rebuild tiap panggilan.
_service = None


def _svc():
    global _service
    if _service is None:
        _service = _bangun_layanan()
    return _service


def reset_service():
    """Reset service — dipanggil kalau token kedaluwarsa di tengah jalan."""
    global _service
    _service = None


def terhubung() -> bool:
    """Cek apakah Google Drive terhubung dan token valid."""
    try:
        svc = _svc()
        if svc is None:
            return False
        svc.about().get(fields="user").execute()
        return True
    except Exception as e:
        log.warning("Drive tidak terhubung: %s", e)
        return False


def info_akun() -> dict | None:
    """Dapatkan info akun Drive (email, kuota)."""
    try:
        svc = _svc()
        if svc is None:
            return None
        about = svc.about().get(
            fields="user,storageQuota"
        ).execute()
        user = about.get("user", {})
        quota = about.get("storageQuota", {})
        return {
            "email": user.get("emailAddress", ""),
            "nama": user.get("displayName", ""),
            "kuota_total": int(quota.get("limit", 0)),
            "kuota_terpakai": int(quota.get("usage", 0)),
            "kuota_sisa": int(quota.get("limit", 0)) - int(quota.get("usage", 0)),
        }
    except Exception as e:
        log.warning("Gagal ambil info akun: %s", e)
        return None


def buat_folder_sesi(nama_folder: str) -> dict | None:
    """Buat folder baru di Drive untuk satu sesi.

    Returns dict {"id": ..., "link": ...} atau None kalau gagal.
    """
    try:
        svc = _svc()
        if svc is None:
            return None

        meta = {
            "name": nama_folder,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if PARENT_FOLDER_ID:
            meta["parents"] = [PARENT_FOLDER_ID]

        folder = svc.files().create(body=meta, fields="id,webViewLink").execute()
        folder_id = folder["id"]
        folder_link = folder["webViewLink"]

        # Set izin: anyone with link = viewer.
        svc.permissions().create(
            fileId=folder_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()

        log.info("Folder Drive dibuat: %s → %s", nama_folder, folder_link)
        return {"id": folder_id, "link": folder_link}

    except Exception as e:
        log.error("Gagal buat folder Drive '%s': %s", nama_folder, e)
        return None


def upload_foto(path_lokal: str, folder_id: str) -> dict | None:
    """Upload satu foto ke folder Drive.

    Returns dict {"id": ..., "link": ...} atau None kalau gagal.
    """
    try:
        svc = _svc()
        if svc is None:
            return None

        path = Path(path_lokal)
        mime = "image/jpeg"
        if path.suffix.lower() == ".png":
            mime = "image/png"
        elif path.suffix.lower() in (".arw", ".raw"):
            mime = "application/octet-stream"

        media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
        meta = {
            "name": path.name,
            "parents": [folder_id],
        }
        berkas = svc.files().create(
            body=meta,
            media_body=media,
            fields="id,webViewLink",
        ).execute()

        log.info("Foto diupload: %s → %s", path.name, berkas.get("webViewLink"))
        return {"id": berkas["id"], "link": berkas.get("webViewLink", "")}

    except Exception as e:
        log.error("Gagal upload '%s' ke folder %s: %s", path_lokal, folder_id, e)
        return None


def kuota() -> dict | None:
    """Dapatkan kuota Drive."""
    info = info_akun()
    if not info:
        return None
    return {
        "total": info["kuota_total"],
        "terpakai": info["kuota_terpakai"],
        "sisa": info["kuota_sisa"],
    }
