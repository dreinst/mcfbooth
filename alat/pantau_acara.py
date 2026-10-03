"""Ringkasan keadaan photobooth Pet Blessing, dijalankan di Mac panitia.

Dipakai untuk memantau semua laptop dari satu tempat, termasuk laptop receiver
yang tidak bisa dimasuki dari jauh (yang terlihat hanya hasil uploadnya di Drive).

    ~/.venvs/mcfbooth/bin/python alat/pantau_acara.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import server  # noqa: E402,F401  (memuat .env)
from app import drive_client as d  # noqa: E402


def jalankan(cmd: list[str], batas: int = 25) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=batas).stdout.strip()
    except Exception as e:
        return f"(gagal: {str(e)[:80]})"


def lalu(iso: str) -> str:
    detik = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()
    return f"{int(detik // 60)} menit lalu" if detik >= 90 else f"{int(detik)} detik lalu"


print(f"== Photobooth Pet Blessing, {datetime.now():%H.%M.%S} ==")

print("\n-- Kotak masuk di Drive (!Need Organized) --")
svc = d._svc()
for kam in d.kamera_kotak() or []:
    isi = svc.files().list(q=f"'{kam['id']}' in parents and trashed=false and mimeType!='{d.MIME_FOLDER}'",
                           fields="files(name,createdTime)", orderBy="createdTime desc", pageSize=200).execute()["files"]
    akhir = f", upload terakhir {isi[0]['name']} ({lalu(isi[0]['createdTime'])})" if isi else ""
    print(f"Camera {kam['nama']}: {len(isi)} foto belum dipilah{akhir}")

print("\n-- Server reg ulang di Mac --")
try:
    st = json.loads(jalankan(["curl", "-sk", "-m", "6", "https://127.0.0.1:8443/lokal/status"]))
    print(f"pemberi nomor: {st['pemberi']} | VPS: {'tersambung' if st['vps_ok'] else 'TIDAK tersambung'} | {st['pesan']}")
    if st["konflik"]:
        print("KONFLIK:", st["konflik"])
except Exception:
    print("server lokal TIDAK menjawab")
sql = ("select (select count(*) from api.checkins where post='reg_ulang'), "
       "(select count(*) from api.pets where certificate_url is not null), "
       "(select count(*) from api.pets where mcfbooth_session_code is not null and certificate_url is null), "
       "(select count(*) from api.owners where is_test)")
angka = jalankan(["docker", "exec", "pblokal-db", "psql", "-U", "petblessing", "-d", "petblessing", "-Atc", sql]).split("|")
if len(angka) == 4:
    print(f"sudah reg ulang: {angka[0]} pemilik | hewan bersertifikat: {angka[1]} | sudah dipilah tapi sertifikat belum tercatat: {angka[2]}"
          + (f" | PESERTA UJI MASIH ADA: {angka[3]}" if angka[3] != "0" else ""))

print("\n-- Laptop utama (Windows, lewat Tailscale) --")
ps = ("try { $p = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 http://127.0.0.1:8000/api/pilah/papan).Content; $p } "
      "catch { 'TIDAK MENJAWAB' }")
mentah = jalankan(["ssh", "-o", "ConnectTimeout=8", "windows", ps], 40)
try:
    p = json.loads(mentah)
    lok = p.get("lokal") or {}
    print(f"Camera {p['booth']}: {lok.get('total', 0)} foto belum dipilah di laptop, {lok.get('pending', 0)} sedang naik, {lok.get('failed', 0)} gagal")
    # Sesi "tambahan" hanya menambah foto ke hewan yang sertifikatnya sudah ada.
    soal = [s for s in p["sesi"] if s["foto_gagal"] or not (s.get("tambahan") or (s["sertifikat"] == "uploaded" and s["tercatat"]))]
    print(f"sudah dipilah: {len(p['sesi'])} hewan, {len(soal)} belum beres")
    for s in soal[:15]:
        print(f"  {s['label']} {s['hewan']}: foto {s['foto_drive']}/{s['foto']}, sertifikat {s['sertifikat'] or 'belum ada'}"
              f"{'' if s['tercatat'] else ', belum tercatat'}")
except Exception:
    print(mentah[:200] or "tidak terjangkau (laptop mati, tidur, atau Tailscale putus)")
