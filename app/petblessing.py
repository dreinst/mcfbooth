"""Sambungan ke database pendaftaran Pet Blessing (PostgREST di VPS).

Aktif hanya kalau `MCF_MODE=petblessing`. Tanpa itu photobooth berjalan
seperti biasa dan modul ini tidak pernah memanggil jaringan.

Yang dilakukan:
* Mencari pemilik dari isi QR pendaftaran (UUID polos) atau kode 8 huruf yang
  tercetak di pesan WhatsApp, beserta daftar hewannya.
* Menulis balik `pets.mcfbooth_session_code` dan `pets.certificate_url`.

Daftar pemilik disalin utuh ke tabel `pengaturan` tiap kali berhasil diambil,
jadi scan ulang tetap jalan walau wifi venue putus sebentar. Token memakai
peran `booth_worker` yang hanya boleh membaca nama/nomor antrean/hewan dan
menulis dua kolom di atas.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

from . import db
from .jalur import env_float

log = logging.getLogger(__name__)

AKTIF = os.environ.get("MCF_MODE", "").strip().lower() == "petblessing"
API = os.environ.get("PETBLESSING_API_URL", "").strip().rstrip("/")
TOKEN = os.environ.get("PETBLESSING_BOOTH_TOKEN", "").strip()
TIMEOUT = env_float("PETBLESSING_TIMEOUT", 6)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_KUNCI_CACHE = "pb_pemilik_cache"
_PILIHAN = "select=id,queue_number,name,is_test,pets(id,name,type)"


def siap() -> bool:
    return AKTIF and bool(API) and bool(TOKEN)


def _minta(metode: str, jalur: str, badan: dict | None = None) -> object:
    data = json.dumps(badan).encode() if badan is not None else None
    req = urllib.request.Request(f"{API}/{jalur}", data=data, method=metode, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        isi = res.read()
        return json.loads(isi) if isi else None


def _bentuk(o: dict) -> dict:
    hewan = sorted(o.get("pets") or [], key=lambda p: (p.get("name") or "").lower())
    return {
        "id": o["id"], "nomor": o.get("queue_number"), "nama": (o.get("name") or "").strip(),
        "uji": bool(o.get("is_test")),
        "hewan": [{"id": p["id"], "nama": (p.get("name") or "").strip(),
                   "jenis": (p.get("type") or "").strip()} for p in hewan],
    }


def segarkan() -> list[dict] | None:
    """Ambil semua pemilik sekaligus (ratusan baris, kecil) dan simpan salinan."""
    if not siap():
        return None
    try:
        data = _minta("GET", f"owners?{_PILIHAN}&order=queue_number")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.warning("Daftar pemilik Pet Blessing tidak terjangkau: %s", str(e)[:160])
        return None
    semua = [_bentuk(o) for o in data or []]
    db.simpan_pengaturan(_KUNCI_CACHE, json.dumps(semua, ensure_ascii=False))
    return semua


def _cache() -> list[dict]:
    try:
        return json.loads(db.ambil_pengaturan(_KUNCI_CACHE) or "[]")
    except ValueError:
        return []


def _cocok(daftar: list[dict], kode: str) -> dict | None:
    if _UUID.match(kode):
        return next((o for o in daftar if o["id"].lower() == kode.lower()), None)
    # Kode 8 huruf di caption WhatsApp = awal UUID tanpa tanda hubung.
    pendek = kode.replace("-", "").lower()
    if len(pendek) == 8:
        calon = [o for o in daftar if o["id"].replace("-", "").lower().startswith(pendek)]
        return calon[0] if len(calon) == 1 else None
    return None


def cari_pemilik(kode: str) -> tuple[dict | None, bool]:
    """(pemilik, dari_salinan). Data segar diutamakan; salinan dipakai kalau
    jaringan putus supaya antrean di booth tidak berhenti."""
    kode = (kode or "").strip()
    segar = segarkan()
    if segar is not None:
        return _cocok(segar, kode), False
    return _cocok(_cache(), kode), True


def pemilik_dari_id(owner_id: str) -> dict | None:
    pemilik, _ = cari_pemilik(owner_id)
    return pemilik


def tulis_hewan(pet_id: str, kolom: dict) -> bool:
    """PATCH satu baris pets. False kalau gagal; pemanggil yang mengulang."""
    if not siap():
        return False
    try:
        _minta("PATCH", f"pets?id=eq.{pet_id}", kolom)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.warning("Gagal menulis ke pets %s: %s", pet_id, str(e)[:160])
        return False
