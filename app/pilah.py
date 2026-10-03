"""Meja pilah Pet Blessing: foto dijepret dulu, dipilah belakangan.

Tiap laptop receiver mengirim foto yang datang tanpa sesi ke Drive
'<Raw>/!Need Organized/Camera <booth>' (lihat watcher.kotak_masuk). Di meja
pilah, admin memilih deretan foto dan hewannya, lalu:

* foto pindah ke folder hewan di Drive (ID dan tautannya tetap),
* sertifikat dibuat dari foto pilihan dan naik ke folder Sertifikat,
* tautannya dicatat di database pendaftaran.

Pembatalan mengembalikan foto ke kotak masuk dan membuang sertifikatnya, jadi
salah pilih hewan cukup dibatalkan lalu dipilah ulang. Meja pilah membaca kotak
masuk dari Drive, jadi satu meja bisa memilah foto dari semua kamera.
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
from pathlib import Path

from . import db, drive_client, peristiwa, petblessing, sertifikat, watcher

log = logging.getLogger(__name__)

FOLDER_SISIH = "Disisihkan"
EKST_SERTIFIKAT = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
_ID_AMAN = re.compile(r"^[A-Za-z0-9_-]{5,120}$")

_kunci = threading.Lock()            # satu pemilahan pada satu waktu
_cache: tuple[float, list] | None = None


def _jam(nama: str) -> str:
    """'Ganjil_093512_DSC0001.JPG' -> '09.35.12' (jam foto mendarat di laptop)."""
    for bagian in nama.split("_")[:2]:
        if len(bagian) == 6 and bagian.isdigit():
            return f"{bagian[:2]}.{bagian[2:4]}.{bagian[4:]}"
    return ""


def kotak(segar: bool = False) -> list[dict] | None:
    """Isi kotak masuk per kamera, urut nama (sama dengan urut jam mendarat).
    None kalau Drive tidak terjangkau."""
    global _cache
    if not segar and _cache and time.time() - _cache[0] < 3:
        return _cache[1]
    kamera = drive_client.kamera_kotak()
    if kamera is None:
        return None
    hasil = []
    for k in kamera:
        isi = drive_client.isi_folder(k["id"])
        if isi is None:
            return None
        hasil.append({"nama": k["nama"], "folder_id": k["id"],
                      "berkas": [{"id": b["id"], "nama": b["name"], "jam": _jam(b["name"])} for b in isi]})
    _cache = (time.time(), hasil)
    return hasil


def _lupakan_cache() -> None:
    global _cache
    _cache = None


def thumb(file_id: str) -> Path | None:
    """Thumbnail satu foto di kotak masuk: dari laptop ini kalau fotonya ada di
    sini, kalau tidak dari Drive (disimpan supaya tidak diambil dua kali)."""
    if not _ID_AMAN.match(file_id):
        return None
    baris = db.foto_dari_drive_id(file_id)
    if baris:
        lokal = Path(baris["local_path"])
        kandidat = watcher.THUMBS_DIR / lokal.parent.name / (lokal.stem + ".jpg")
        if kandidat.exists():
            return kandidat
    simpan = watcher.THUMBS_DIR / "_pilah" / f"{file_id}.jpg"
    if simpan.exists():
        return simpan
    isi = drive_client.thumb_berkas(file_id)
    if not isi:
        return None
    simpan.parent.mkdir(parents=True, exist_ok=True)
    sementara = simpan.with_suffix(".tmp")
    sementara.write_bytes(isi)
    sementara.replace(simpan)
    return simpan


def _pindah_lokal(local_path: str, kode_baru: str) -> Path:
    """Pindahkan berkas arsip dan thumbnail-nya ke folder sesi lain."""
    src = Path(local_path)
    tujuan = watcher.ARCHIVE_DIR / kode_baru
    tujuan.mkdir(parents=True, exist_ok=True)
    dest = watcher._nama_bebas(tujuan / src.name)
    shutil.move(str(src), str(dest))
    t_lama = watcher.THUMBS_DIR / src.parent.name / (src.stem + ".jpg")
    if t_lama.exists():
        t_baru = watcher.THUMBS_DIR / kode_baru / (dest.stem + ".jpg")
        t_baru.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(t_lama), str(t_baru))
    return dest


def _peta_kotak() -> dict[str, tuple[dict, dict]]:
    isi = kotak(segar=True)
    if isi is None:
        raise db.GalatDB("Drive belum bisa dijangkau. Coba lagi sebentar.", "drive_tidak_siap")
    return {b["id"]: (b, k) for k in isi for b in k["berkas"]}


def tetapkan(file_ids: list[str], owner_id: str, pet_id: str, terbaik: str | None = None) -> dict:
    """Deretan foto di kotak masuk menjadi milik satu hewan: foto pindah ke
    folder hewan, sertifikat dibuat dari foto `terbaik` (bawaan: foto terakhir).
    Hewan yang sudah punya sertifikat hanya mendapat sertifikat baru kalau
    `terbaik` disebut: menambah foto tidak boleh diam-diam mengganti sertifikat."""
    if not file_ids:
        raise db.GalatDB("Pilih dulu fotonya.", "foto_tidak_cocok")
    pemilik = petblessing.pemilik_dari_id(owner_id)
    hewan = next((h for h in (pemilik or {}).get("hewan", []) if h["id"] == pet_id), None)
    if not pemilik or not hewan:
        raise db.GalatDB("Data pemilik atau hewan tidak ditemukan. Cari ulang nomornya.", "data_tidak_cocok")
    if not pemilik.get("nomor"):
        raise db.GalatDB("Peserta ini belum reg ulang, jadi belum punya nomor urut. "
                         "Arahkan ke meja reg ulang dulu.", "belum_reg_ulang")
    pb = {"owner_id": pemilik["id"], "pet_id": hewan["id"], "nomor": pemilik["nomor"],
          "nomor_daftar": pemilik.get("nomor_daftar"), "huruf": hewan["huruf"], "label": hewan["label"],
          "pemilik": pemilik["nama"], "hewan": hewan["nama"], "jenis": hewan["jenis"], "pilah": True}
    if terbaik is None and db.sertifikat_per_hewan([pet_id]):
        pb["tambahan"] = True      # hanya menambah foto, sertifikat yang ada dipertahankan

    with _kunci:
        peta = _peta_kotak()
        if any(f not in peta for f in file_ids):
            raise db.GalatDB("Sebagian foto sudah tidak ada di kotak masuk (mungkin sudah dipilah). "
                             "Daftarnya dimuat ulang, pilih lagi.", "foto_tidak_cocok")
        urut = sorted(dict.fromkeys(file_ids), key=lambda f: peta[f][0]["nama"])
        pb["asal"] = {f: peta[f][1]["nama"] for f in urut}

        folder = drive_client.buat_folder_sesi(
            petblessing.folder_hewan(pb), induk=petblessing.folder_pemilik(pb),
            lama=petblessing.folder_hewan(pb, daftar=True), induk_lama=petblessing.folder_pemilik(pb, daftar=True))
        if not folder:
            raise db.GalatDB("Folder Drive hewan belum bisa disiapkan. Coba lagi sebentar.", "drive_tidak_siap")

        sesi = db.buat_sesi_selesai(f"{hewan['label']} {hewan['nama']} ({pemilik['nama']})", pb)
        db.simpan_drive_info(sesi["id"], folder["id"], folder["link"])
        dipindah: list[tuple[str, int, str]] = []
        gagal: list[str] = []
        for fid in urut:
            berkas, kam = peta[fid]
            if not drive_client.pindah_berkas(fid, kam["folder_id"], folder["id"]):
                gagal.append(berkas["nama"])
                continue
            baris = db.foto_dari_drive_id(fid)
            if baris and Path(baris["local_path"]).exists():
                db.pindah_foto(baris["id"], sesi["id"], str(_pindah_lokal(baris["local_path"], sesi["session_code"])))
                foto_id = baris["id"]
            elif baris:
                db.pindah_foto(baris["id"], sesi["id"])
                foto_id = baris["id"]
            else:
                # Foto dari laptop lain: hanya ada di Drive.
                foto_id = db.catat_foto_drive(sesi["id"], f"drive:{fid}/{berkas['nama']}", fid)
            dipindah.append((fid, foto_id, berkas["nama"]))
        _lupakan_cache()
        if not dipindah:
            db.hapus_sesi(sesi["id"])
            raise db.GalatDB("Foto tidak bisa dipindah di Drive. Coba lagi sebentar.", "drive_tidak_siap")

        fid, foto_id, nama = next((d for d in dipindah if d[0] == terbaik), dipindah[-1])
        foto = None if pb.get("tambahan") else db.ambil_foto(foto_id)
        if foto and not Path(foto["local_path"]).exists():
            tujuan = watcher.ARCHIVE_DIR / sesi["session_code"] / nama
            if drive_client.unduh_berkas(fid, tujuan):
                db.pindah_foto(foto_id, sesi["id"], str(tujuan))
                watcher._buat_thumbnail(tujuan, sesi["session_code"])
                foto = db.ambil_foto(foto_id)
            else:
                foto = None

    watcher._jadwalkan(petblessing.tulis_hewan, pet_id,
                       {"mcfbooth_session_code": sesi["session_code"], "photo_folder_url": folder["link"]})
    sesi = db.ambil_sesi(sesi["id"])
    bisa = bool(foto) and Path(foto["local_path"]).suffix.lower() in EKST_SERTIFIKAT
    if bisa:
        sertifikat.mulai(sesi, foto)
    log.info("Pilah: %d foto -> %s (%d gagal dipindah, sertifikat %s)", len(dipindah), sesi["guest_name"],
             len(gagal), "dibuat" if bisa else "TIDAK dibuat")
    peristiwa.kirim({"jenis": "pilah", "session_id": sesi["id"]}, ke_tamu=False)
    return {"sesi": db.ambil_sesi(sesi["id"]), "dipindah": len(dipindah), "gagal": gagal, "sertifikat": bisa,
            "tambahan": bool(pb.get("tambahan"))}


def sisihkan(file_ids: list[str]) -> dict:
    """Foto yang bukan foto hewan (jepretan uji, salah jepret) dipindah ke
    'Camera <booth>/Disisihkan' supaya tidak menghalangi pemilahan. Tidak dihapus."""
    with _kunci:
        peta = _peta_kotak()
        n = 0
        for fid in file_ids:
            if fid not in peta:
                continue
            _, kam = peta[fid]
            tujuan = drive_client.folder_kotak(kam["nama"], FOLDER_SISIH)
            if tujuan and drive_client.pindah_berkas(fid, kam["folder_id"], tujuan):
                baris = db.foto_dari_drive_id(fid)
                if baris:
                    db.hapus_foto(baris["id"])   # berkasnya tetap ada di arsip laptop
                n += 1
        _lupakan_cache()
    log.info("Pilah: %d foto disisihkan", n)
    return {"disisihkan": n}


def _sertifikat_lain(pet_id: str, kecuali: int) -> dict | None:
    """Sesi lain hewan yang sama yang sertifikatnya sudah di Drive (paling baru)."""
    for s in db.sesi_pb():
        if s["id"] != kecuali and s["pb"].get("pet_id") == pet_id and (s.get("sertifikat") or {}).get("link_pdf"):
            return s
    return None


def batalkan(sesi_id: int) -> dict:
    """Balikkan satu pemilahan: foto kembali ke kotak masuk, sertifikat dibuang,
    catatan di database pendaftaran dikembalikan."""
    sesi = db.ambil_sesi(sesi_id)
    pb = sesi.get("pb") or {}
    if not pb.get("pilah"):
        raise db.GalatDB("Sesi ini bukan hasil pemilahan, jadi tidak bisa dibatalkan dari sini.", "data_tidak_cocok")
    asal = pb.get("asal") or {}
    with _kunci:
        kembali, tertinggal = 0, 0
        for foto in db.daftar_foto(sesi_id):
            fid = foto.get("drive_file_id")
            kam = asal.get(fid) or watcher.BOOTH_ID
            tujuan = drive_client.folder_kotak(kam) if fid and kam else None
            if not tujuan or not drive_client.pindah_berkas(fid, sesi["drive_folder_id"], tujuan):
                tertinggal += 1
                continue
            kembali += 1
            if kam == watcher.BOOTH_ID and Path(foto["local_path"]).exists():
                kotak_sesi = watcher.kotak_masuk()
                db.pindah_foto(foto["id"], kotak_sesi["id"],
                               str(_pindah_lokal(foto["local_path"], kotak_sesi["session_code"])))
            else:
                db.hapus_foto(foto["id"])
        if tertinggal:
            _lupakan_cache()
            raise db.GalatDB(f"{tertinggal} foto belum bisa dikembalikan ke kotak masuk (Drive tidak menjawab). "
                             "Coba batalkan lagi sebentar.", "drive_tidak_siap")
        lain = _sertifikat_lain(pb.get("pet_id"), sesi_id)
        for srt in db.sertifikat_sesi(sesi_id):
            for berkas_id in (srt.get("drive_png_id"), srt.get("drive_pdf_id")):
                if berkas_id:
                    drive_client.buang_berkas(berkas_id)
            # Salinan di folder hewan bernama sama untuk semua sesi hewan itu:
            # dibiarkan kalau sesi lain masih punya sertifikat yang berlaku.
            for akhiran in ((".png", ".pdf") if not lain else ()):
                salinan = drive_client.cari_berkas(sesi["drive_folder_id"], srt["nama_berkas"] + akhiran)
                if salinan and salinan != "ada":
                    drive_client.buang_berkas(salinan)
        db.hapus_sesi(sesi_id)
        _lupakan_cache()
    kolom = ({"certificate_url": lain["sertifikat"]["link_pdf"], "mcfbooth_session_code": lain["session_code"],
              "photo_folder_url": lain.get("drive_folder_link")} if lain
             else {"certificate_url": None, "mcfbooth_session_code": None})
    watcher._jadwalkan(petblessing.tulis_hewan, pb.get("pet_id"), kolom)
    log.info("Pilah dibatalkan: %s, %d foto kembali ke kotak masuk", sesi["guest_name"], kembali)
    peristiwa.kirim({"jenis": "pilah", "session_id": sesi_id}, ke_tamu=False)
    return {"dikembalikan": kembali}


def papan(limit: int = 300) -> dict:
    """Papan pantau: sesi Pet Blessing di laptop ini (terbaru dulu) dan keadaan
    kotak masuk. Dipakai meja pilah dan monitor kedua."""
    baris = []
    for s in db.sesi_pb(limit):
        pb = s["pb"]
        if not pb.get("label"):
            continue
        srt = s.get("sertifikat") or {}
        baris.append({
            "id": s["id"], "label": pb["label"], "hewan": pb.get("hewan"), "jenis": pb.get("jenis"),
            "pemilik": pb.get("pemilik"), "kamera": sorted(set((pb.get("asal") or {}).values())) or [watcher.BOOTH_ID or ""],
            "foto": s["foto"]["total"], "foto_drive": s["foto"]["uploaded"], "foto_gagal": s["foto"]["failed"],
            "sertifikat": srt.get("status"), "tercatat": bool(srt.get("tercatat")), "sertifikat_id": srt.get("id"),
            "folder": f"{petblessing.folder_pemilik(pb)} / {petblessing.folder_hewan(pb)}",
            "folder_link": s.get("drive_folder_link"), "pilah": bool(pb.get("pilah")), "tambahan": bool(pb.get("tambahan")),
            "berjalan": s["status"] == "active", "waktu": s.get("finished_at") or s["started_at"],
        })
    isi = kotak()
    lokal = db.sesi_dari_kode(f"{watcher.KODE_KOTAK}_{watcher.BOOTH_ID}") if watcher.BOOTH_ID else None
    return {
        "booth": watcher.BOOTH_ID, "drive_ok": isi is not None, "sesi": baris,
        "kotak": [{"nama": k["nama"], "jumlah": len(k["berkas"])} for k in (isi or [])],
        # Foto kamera laptop ini yang belum dipilah: sudah masuk laptop, sudah naik, masih antre, gagal.
        "lokal": lokal["foto"] if lokal else None,
    }
