"""Siapkan folder Drive Pet Blessing dari database pendaftaran, sebelum hari-H.

    python -m app.siapkan_folder_pb

Untuk tiap pemilik (bukan data uji) dibuat folder `088 Nama Pemilik` di folder
Raw Photo panitia, dengan subfolder per hewan `A Nama Hewan (Jenis)`, dan folder
pemilik yang sama di folder Sertifikat panitia. Nama diambil dari
petblessing.folder_pemilik/folder_hewan, jadi booth nanti memakai folder ini
dan tidak membuat folder kembar. Aman dijalankan berulang (launchd tiap 30
menit): yang sudah ada dilewati, pendaftar baru menyusul.

Butuh .env mode petblessing dengan DRIVE_FOLDER_RAW_ID, dan sudah login Google
di Pengaturan (izin Drive penuh).
"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from .jalur import AKAR

load_dotenv(AKAR / ".env")

from . import db, drive_client, petblessing  # noqa: E402

log = logging.getLogger("siapkan_folder_pb")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not petblessing.AKTIF or not drive_client.FOLDER_RAW_ID:
        log.error("Butuh PHOTOBOOTH_MODE=petblessing dan DRIVE_FOLDER_RAW_ID di .env.")
        return 1
    db.siapkan()
    pemilik = petblessing.segarkan()
    if pemilik is None:
        log.error("Database pendaftaran tidak terjangkau.")
        return 1
    svc = drive_client._svc()
    if svc is None:
        log.error("Belum login Google (atau token kedaluwarsa). Login di Pengaturan booth.")
        return 1

    baru = gagal = 0
    for o in pemilik:
        # Yang sudah reg ulang foldernya diambil alih booth (diganti nama ke nomor urut).
        if o["uji"] or o["nomor"]:
            continue
        try:
            baru += _siapkan_pemilik(svc, o)
        except Exception as e:  # jaringan putus/timeout: pemilik ini disusulkan putaran berikutnya
            gagal += 1
            log.warning("Gagal menyiapkan folder %s: %s", o["nama"], str(e)[:160])
    log.info("Selesai: %d pemilik, %d folder hewan baru, %d pemilik gagal (diulang putaran berikutnya).",
             sum(1 for o in pemilik if not o["uji"]), baru, gagal)
    return 0


def _siapkan_pemilik(svc, o: dict) -> int:
    baru = 0
    nama_pemilik = petblessing.folder_pemilik({"nomor_daftar": o["nomor_daftar"], "pemilik": o["nama"]})
    induk = drive_client._folder_pemilik(svc, drive_client.FOLDER_RAW_ID, nama_pemilik)
    if drive_client.FOLDER_SERTIFIKAT_ID:
        drive_client._folder_pemilik(svc, drive_client.FOLDER_SERTIFIKAT_ID, nama_pemilik)
    for h in o["hewan"]:
        nama = petblessing.folder_hewan({"huruf": h["huruf"], "hewan": h["nama"], "jenis": h["jenis"]})
        kunci = f"drive_hewan:{induk}:{nama}"
        if db.ambil_pengaturan(kunci):
            continue
        fid = drive_client._cari_subfolder(svc, induk, nama)
        if not fid:
            fid = drive_client._buat_folder(svc, nama, induk)["id"]
            # Sama dengan folder buatan booth: link folder ini jadi QR untuk tamu.
            svc.permissions().create(fileId=fid, body={"type": "anyone", "role": "reader"}, fields="id").execute()
            baru += 1
            log.info("Folder dibuat: %s/%s", nama_pemilik, nama)
        db.simpan_pengaturan(kunci, fid)
    return baru


if __name__ == "__main__":
    sys.exit(main())
