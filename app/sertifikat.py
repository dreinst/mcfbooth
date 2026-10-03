"""Render sertifikat Pet Blessing dari template Figma.

Figma tidak bisa diotomasi tanpa orang di depannya, jadi desainnya diekspor
sekali ke `assets/sertifikat/template.png` (area foto transparan, teks yang
berubah per hewan dikosongkan). Modul ini menaruh foto di bawah template lalu
menulis tiga isian dengan huruf dan koordinat yang sama seperti di Figma
(`layout.json`). Kalau desain di Figma berubah, ekspor ulang template dan
sesuaikan `layout.json`; kode di sini tidak perlu disentuh.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .jalur import AKAR

ASET = AKAR / "assets"
FOLDER_SERTIFIKAT = ASET / "sertifikat"
FOLDER_FONT = ASET / "fonts"

# Tinggi baris AUTO Figma untuk Poppins = 1,5 x ukuran huruf, dan garis dasar
# jatuh di 1,1 x ukuran dari atas kotak teks (ascender 1,05 + separuh line gap).
_GARIS_DASAR = 1.1


@lru_cache(maxsize=1)
def _layout() -> dict:
    return json.loads((FOLDER_SERTIFIKAT / "layout.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _template() -> Image.Image:
    return Image.open(FOLDER_SERTIFIKAT / "template.png").convert("RGBA")


@lru_cache(maxsize=16)
def _font(berkas: str, ukuran: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FOLDER_FONT / berkas), ukuran)


def _foto_isi(path: str, w: int, h: int) -> Image.Image:
    """Foto dipotong memenuhi kotak (cover), titik tengah dipertahankan."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def _tulis_baris(gambar: ImageDraw.ImageDraw, baris: dict, nilai: str, lay: dict) -> None:
    kolom = lay["kolom_teks"]
    tengah = kolom["x"] + kolom["w"] / 2
    ukuran = baris["ukuran"]
    warna = tuple(lay["warna_teks"])
    f_isi = _font(lay["font"]["isi"], ukuran)

    if "label" not in baris:
        # Nama hewan: satu baris di tengah; mengecil kalau lebih lebar dari kolom.
        while ukuran > 30 and f_isi.getlength(nilai) > kolom["w"]:
            ukuran -= 2
            f_isi = _font(lay["font"]["isi"], ukuran)
        dasar = baris["top"] + _GARIS_DASAR * baris["ukuran"] + (baris["ukuran"] - ukuran) * 0.75
        gambar.text((tengah, dasar), nilai, font=f_isi, fill=warna, anchor="ms")
        return

    f_label = _font(lay["font"]["label"], ukuran)
    lebar_label = f_label.getlength(baris["label"])
    lebar_isi = f_isi.getlength(nilai) + 2 * baris["pad_isi"]
    total = lebar_label + baris["jarak"] + lebar_isi
    kiri = tengah - total / 2
    dasar = baris["top"] + _GARIS_DASAR * ukuran
    gambar.text((kiri, dasar), baris["label"], font=f_label, fill=warna, anchor="ls")
    x_isi = kiri + lebar_label + baris["jarak"] + baris["pad_isi"]
    gambar.text((x_isi, dasar), nilai, font=f_isi, fill=warna, anchor="ls")


def render(foto_path: str, nama_hewan: str, jenis: str, pemilik: str,
           tujuan: Path, nama_berkas: str) -> tuple[str, str]:
    """Buat PNG dan PDF sertifikat. Mengembalikan (path_png, path_pdf)."""
    lay = _layout()
    kanvas = Image.new("RGBA", tuple(lay["ukuran"]), (255, 255, 255, 255))
    kotak = lay["foto"]
    kanvas.paste(_foto_isi(foto_path, kotak["w"], kotak["h"]), (kotak["x"], kotak["y"]))
    kanvas.alpha_composite(_template())

    nilai = {"jenis": jenis, "nama_hewan": nama_hewan, "pemilik": pemilik}
    gambar = ImageDraw.Draw(kanvas)
    for baris in lay["baris"]:
        _tulis_baris(gambar, baris, (nilai[baris["isi"]] or "").strip(), lay)

    hasil = kanvas.convert("RGB")
    tujuan.mkdir(parents=True, exist_ok=True)
    png = tujuan / f"{nama_berkas}.png"
    pdf = tujuan / f"{nama_berkas}.pdf"
    for path, format_, opsi in ((png, "PNG", {"dpi": (lay["dpi"], lay["dpi"])}),
                                (pdf, "PDF", {"resolution": lay["dpi"]})):
        sementara = path.with_name(path.name + ".tmp")
        hasil.save(sementara, format_, **opsi)
        os.replace(sementara, path)
    return str(png), str(pdf)


# ================================================================== alur
# Foto pilihan operator → render → Drive "3. Sertifikat" → tautan ke database
# pendaftaran. Tiap langkah menyimpan hasilnya di tabel `sertifikat`, jadi
# kalau wifi putus langkah berikutnya disusulkan penjaga latar (watcher).

import logging  # noqa: E402
import threading  # noqa: E402

from . import db, drive_client, peristiwa, petblessing, watcher  # noqa: E402

log = logging.getLogger(__name__)

FOLDER_HASIL = watcher.ARCHIVE_DIR / "_sertifikat"
_kunci = threading.Lock()
_sedang: set[int] = set()


def _kirim(jenis: str, srt: dict) -> None:
    peristiwa.kirim({"jenis": jenis, "session_id": srt["session_id"], "sertifikat": srt},
                    ke_tamu=False)


def mulai(sesi: dict, foto: dict) -> dict:
    """Catat sertifikat baru dan render di latar. Validasi di pemanggil."""
    pb = sesi["pb"]
    awal = pb.get("label") or f"{int(pb.get('nomor') or 0):03d}"
    dasar = f"{awal}_{db._slug(pb['hewan'])}_{db._slug(pb['pemilik'])}"
    ke = len(db.sertifikat_sesi(sesi["id"])) + 1
    srt = db.buat_sertifikat(sesi["id"], foto["id"], dasar if ke == 1 else f"{dasar}_{ke}")
    log.info("Sertifikat diminta: %s", srt["nama_berkas"])
    _kirim("sertifikat_mulai", srt)
    watcher._jadwalkan(_render, srt["id"])
    return srt


def _render(sertifikat_id: int) -> None:
    srt = db.ambil_sertifikat(sertifikat_id)
    sesi = db.ambil_sesi(srt["session_id"])
    foto = db.ambil_foto(srt["photo_id"])
    pb = sesi["pb"]
    try:
        png, pdf = render(foto["local_path"], pb["hewan"], pb["jenis"], pb["pemilik"],
                          FOLDER_HASIL, srt["nama_berkas"])
    except Exception as e:
        log.exception("Render sertifikat %s gagal", srt["nama_berkas"])
        _kirim("sertifikat_gagal", db.ubah_sertifikat(sertifikat_id, status="failed", pesan=str(e)[:200]))
        return
    srt = db.ubah_sertifikat(sertifikat_id, png_path=png, pdf_path=pdf, status="menunggu", pesan=None)
    log.info("Sertifikat dirender: %s", srt["nama_berkas"])
    _kirim("sertifikat_siap", srt)
    peristiwa.kirim({"jenis": "sertifikat_siap", "session_id": srt["session_id"]}, ke_operator=False)
    _upload(sertifikat_id)


def _upload(sertifikat_id: int) -> None:
    with _kunci:
        if sertifikat_id in _sedang:
            return
        _sedang.add(sertifikat_id)
    try:
        srt = db.ambil_sertifikat(sertifikat_id)
        # Sertifikat masuk folder hewannya (di dalam folder pemilik). Kalau
        # folder sesi belum terpasang (Drive sempat putus), tunggu disusulkan.
        sesi = db.ambil_sesi(srt["session_id"])
        folder = folder_hewan = sesi.get("drive_folder_id")
        if folder and srt["status"] == "menunggu" and drive_client.terhubung():
            pb = sesi["pb"]
            folder = drive_client.folder_sertifikat(petblessing.folder_pemilik(pb), folder,
                                                    petblessing.folder_pemilik(pb, daftar=True))
        if srt["status"] == "menunggu" and folder and drive_client.terhubung():
            ulang = bool(srt.get("pesan"))
            png = srt["drive_png_id"] and {"id": srt["drive_png_id"], "link": srt["link_png"]} \
                or drive_client.upload_sertifikat(srt["png_path"], cek_dulu=ulang, folder_id=folder)
            pdf = png and (srt["drive_pdf_id"] and {"id": srt["drive_pdf_id"], "link": srt["link_pdf"]}
                           or drive_client.upload_sertifikat(srt["pdf_path"], cek_dulu=ulang, folder_id=folder))
            # Folder sertifikat panitia terpisah: salinannya juga masuk folder foto hewan,
            # supaya QR di layar tamu (dan hasil.html) membuka foto + sertifikat sekaligus.
            if png and pdf and folder != folder_hewan:
                salin = all(drive_client.upload_sertifikat(p, cek_dulu=True, folder_id=folder_hewan)
                            for p in (srt["png_path"], srt["pdf_path"]))
                pdf = pdf if salin else None
            if png and pdf:
                srt = db.ubah_sertifikat(sertifikat_id, drive_png_id=png["id"], link_png=png["link"],
                                         drive_pdf_id=pdf["id"], link_pdf=pdf["link"],
                                         status="uploaded", pesan=None)
                _kirim("sertifikat_uploaded", srt)
            else:
                # Sebagian mungkin sudah sampai; simpan yang ada supaya tidak dobel.
                srt = db.ubah_sertifikat(sertifikat_id,
                                         drive_png_id=png and png["id"], link_png=png and png["link"],
                                         pesan="Upload ke Drive belum berhasil, dicoba lagi otomatis.")
                _kirim("sertifikat_tertunda", srt)
        if srt["status"] == "uploaded" and not srt["tercatat"]:
            _catat(srt)
    finally:
        with _kunci:
            _sedang.discard(sertifikat_id)


def _catat(srt: dict) -> None:
    sesi = db.ambil_sesi(srt["session_id"])
    ok = petblessing.tulis_hewan(sesi["pb"]["pet_id"], {
        "certificate_url": srt["link_pdf"], "mcfbooth_session_code": sesi["session_code"],
        "photo_folder_url": sesi.get("drive_folder_link"),
    })
    if ok:
        _kirim("sertifikat_tercatat", db.ubah_sertifikat(srt["id"], tercatat=1))


def susulkan() -> int:
    """Dipanggil penjaga latar: lanjutkan sertifikat yang tertahan."""
    tertunda = db.sertifikat_tertunda()
    for srt in tertunda:
        watcher._jadwalkan(_upload, srt["id"])
    return len(tertunda)
