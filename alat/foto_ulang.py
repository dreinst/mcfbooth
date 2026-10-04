"""Penjaga "Foto ulang": membatalkan pemilahan yang ditandai salah oleh superadmin di rekap pendaftaran.

Rekap (pendaftaran-masuk.html, repo petblessings) mengisi kolom pets.foto_ulang di VPS dengan kode sesi booth.
Skrip ini membacanya tiap 10 detik, memanggil Batalkan di booth laptop ini (foto kembali ke kotak masuk Meja
pilah, sertifikat dan PDF siap cetak dibuang), lalu mengosongkan kolomnya. Sesi milik booth laptop lain tidak
disentuh: permintaannya dibiarkan untuk penjaga di laptop itu. Kalau booth sedang mati, dicoba lagi nanti.

Pakai: python3 alat/foto_ulang.py   (token booth dibaca dari .env dan tidak pernah dicetak)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
VPS = "https://petblessing-api.187.53.129.205.sslip.io"
BOOTH = "http://127.0.0.1:8000"
JEDA = 10


def token() -> str:
    for baris in (AKAR / ".env").read_text(encoding="utf-8-sig").splitlines():
        if baris.startswith("PETBLESSING_BOOTH_TOKEN="):
            return baris.split("=", 1)[1].strip()
    sys.exit("PETBLESSING_BOOTH_TOKEN tidak ada di .env")


def panggil(url: str, metode: str = "GET", data=None, kepala: dict | None = None):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json", **(kepala or {})}, method=metode)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            isi = r.read()
            return r.status, json.loads(isi) if isi else None
    except urllib.error.HTTPError as e:
        isi = e.read()
        try:
            return e.code, json.loads(isi)
        except ValueError:
            return e.code, None


def catat(teks: str) -> None:
    print(time.strftime("%H.%M.%S"), teks, flush=True)


def sekali(vps: str, booth: str, kepala: dict) -> None:
    kode, daftar = panggil(vps + "/pets?foto_ulang=not.is.null&select=id,name,foto_ulang,mcfbooth_session_code", kepala=kepala)
    if kode != 200:
        raise RuntimeError(f"VPS menjawab {kode}")
    for hewan in daftar:
        diminta = hewan["foto_ulang"]
        if hewan["mcfbooth_session_code"] != diminta:
            ket = "sertifikatnya sudah dibatalkan atau diganti, permintaan dihapus"
        else:
            kode, hasil = panggil(booth + "/api/sessions?limit=5&q=" + urllib.parse.quote(diminta))
            if kode != 200:
                raise RuntimeError(f"booth menjawab {kode}")
            sesi = next((s for s in hasil["sesi"] if s["session_code"] == diminta), None)
            if not sesi:
                continue        # dipilah di booth laptop lain
            kode, hasil = panggil(f"{booth}/api/pilah/batalkan/{sesi['id']}", "POST")
            if kode != 200:
                catat(f"{hewan['name']} ({diminta}): Batalkan gagal, {(hasil or {}).get('pesan') or kode}. Dicoba lagi.")
                continue
            ket = f"dibatalkan, {hasil.get('dikembalikan', 0)} foto kembali ke kotak masuk"
        kode, _ = panggil(vps + "/pets?id=eq." + hewan["id"], "PATCH", {"foto_ulang": None},
                          {**kepala, "Prefer": "return=minimal"})
        catat(f"{hewan['name']} ({diminta}): {ket}" + ("" if kode in (200, 204) else f", TAPI kolom foto_ulang gagal dikosongkan ({kode})"))


if __name__ == "__main__":
    # Dua argumen (alamat API, alamat booth) hanya dipakai rangkaian uji.
    vps, booth = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else (VPS, BOOTH)
    kepala = {"Authorization": "Bearer " + (os.environ.get("PETBLESSING_BOOTH_TOKEN") or token())}
    catat(f"Penjaga Foto ulang jalan: {vps} -> {booth}")
    gagal = ""
    while True:
        try:
            sekali(vps, booth, kepala)
            gagal = ""
        except (OSError, RuntimeError) as e:
            if str(e) != gagal:         # kesalahan yang sama tidak dicatat berulang
                gagal = str(e)
                catat(f"Belum bisa: {e}")
        time.sleep(JEDA)
