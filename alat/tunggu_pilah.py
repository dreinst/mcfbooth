"""Menunggu sampai ada hewan yang baru dipilah (di booth Mac atau booth Windows), lalu mencetak daftarnya dan berhenti.
Dipakai untuk pengecekan wajah: tiap pemilahan baru dibandingkan dengan foto pendaftaran hewannya.

    ~/.venvs/mcfbooth/bin/python alat/tunggu_pilah.py [detik_jeda]
"""
import json, subprocess, sys, time, urllib.request
from pathlib import Path

CATAT = Path("/tmp/kw-pindah/wajah/sudah-dicek.json")
jeda = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def papan():
    hasil = {}
    try:
        for b in json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/pilah/papan", timeout=40).read())["sesi"]:
            hasil[f"mac:{b['id']}:{b['label']}"] = b
    except Exception:
        pass
    try:
        w = subprocess.run(["ssh", "-o", "ConnectTimeout=10", "windows", "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\Public\\jaga-booth.ps1"],
                           capture_output=True, text=True, timeout=60).stdout.split("\n")[0]
        for b in json.loads(w)["sesi"]:
            hasil[f"win:{b['id']}:{b['label']}"] = b
    except Exception:
        pass
    return hasil


sudah = set(json.load(open(CATAT))) if CATAT.exists() else set()
while True:
    kini = papan()
    baru = {k: b for k, b in kini.items() if k not in sudah and b.get("sertifikat") in ("uploaded", "failed", None) and not b.get("berjalan")}
    if baru:
        for k, b in baru.items():
            print(f"BARU {k} | {b['label']} {b['hewan']} ({b['jenis']}) | {b['pemilik']} | {b['foto']} foto | sertifikat {b['sertifikat']} | {b['folder_link']}")
        sys.exit(0)
    time.sleep(jeda)
