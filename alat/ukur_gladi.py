"""Ukur kecepatan gladi dari log booth di laptop ini (laptop yang menerima foto kamera).

    py alat/ukur_gladi.py            # kejadian 2 jam terakhir
    py alat/ukur_gladi.py 03:40      # kejadian sejak jam itu, hari ini

Per foto: kapan berkasnya mulai muncul di folder tether, kapan selesai diterima dari
kamera, kapan masuk arsip laptop, kapan sampai di Drive. Per sertifikat: diminta,
selesai dirender, sampai di Drive. "Telat dari jepret" membandingkan jam EXIF kamera
dengan jam masuk laptop, relatif terhadap foto tercepat (jam kamera jarang persis sama
dengan jam laptop, jadi yang bermakna selisih antar foto, bukan angka mutlaknya).
"""

import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
POLA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) \[app\.(\w+)\] \w+: (.*)$")
sejak = datetime.now() - timedelta(hours=2)
if len(sys.argv) > 1:
    j, m = sys.argv[1].split(":")
    sejak = datetime.now().replace(hour=int(j), minute=int(m), second=0, microsecond=0)

foto: dict[str, dict] = {}          # nama berkas kamera -> waktu tiap tahap
arsip_ke_kamera: dict[str, str] = {}
sert: dict[str, dict] = {}
pilah: list[tuple[datetime, str]] = []
for berkas in sorted((AKAR / "logs").glob("booth.log*"), key=lambda p: p.stat().st_mtime):
    for baris in berkas.read_text(encoding="utf-8", errors="replace").splitlines():
        m = POLA.match(baris)
        if not m:
            continue
        t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") + timedelta(milliseconds=int(m.group(2)))
        if t < sejak:
            continue
        pesan = m.group(4)
        if pesan.startswith("Foto baru terdeteksi: "):
            foto[pesan.split(": ", 1)[1]] = {"deteksi": t}
        elif pesan.startswith("Berkas selesai diterima dari kamera: "):
            foto.setdefault(pesan.split(": ", 1)[1], {})["terima"] = t
        elif pesan.startswith("Disalin ke arsip: "):
            p = Path(pesan.split(": ", 1)[1].replace("\\", "/"))
            kamera = p.name.split("_", 1)[1] if "_kotak_masuk_" in str(p) and "_" in p.name else p.name
            if kamera in foto:
                foto[kamera].update(arsip=t, nama_arsip=p.name)
                arsip_ke_kamera[p.name] = kamera
        elif pesan.startswith("Diupload: "):
            nama = pesan[len("Diupload: "):].split(" ", 1)[0]
            if nama.lower().endswith((".png", ".pdf")):
                sert.setdefault(Path(nama).stem, {}).setdefault("drive_" + nama[-3:].lower(), t)
            else:
                kamera = arsip_ke_kamera.get(nama) or arsip_ke_kamera.get(nama.split("_", 1)[-1])
                if kamera:
                    foto[kamera].setdefault("drive", t)
        elif pesan.startswith("Sertifikat diminta: "):
            sert.setdefault(pesan.split(": ", 1)[1], {})["diminta"] = t
        elif pesan.startswith("Sertifikat dirender: "):
            sert.setdefault(pesan.split(": ", 1)[1], {})["render"] = t
        elif pesan.startswith("Pilah"):
            pilah.append((t, pesan))


def exif(nama_arsip: str) -> datetime | None:
    try:
        from PIL import Image
        p = next((AKAR / "local_archive").rglob(nama_arsip), None)
        if not p:
            return None
        with Image.open(p) as im:
            teks = im.getexif().get_ifd(0x8769).get(36867) or im.getexif().get(306)
        return datetime.strptime(teks, "%Y:%m:%d %H:%M:%S") if teks else None
    except Exception:
        return None


def d(a, b) -> str:
    return f"{(b - a).total_seconds():6.1f}" if a and b else "     ?"


selisih = {}
for nama, f in foto.items():
    e = exif(f.get("nama_arsip", ""))
    if e and f.get("terima"):
        selisih[nama] = (f["terima"] - e).total_seconds()
dasar = min(selisih.values()) if selisih else 0

print(f"== Kecepatan sejak {sejak:%H:%M} ({len(foto)} foto, {len(sert)} sertifikat) ==\n")
print("FOTO                 muncul    terima(dtk)  arsip(dtk)  ke Drive(dtk)  telat dari jepret(dtk)")
for nama, f in foto.items():
    telat = f"{selisih[nama] - dasar:6.1f}" if nama in selisih else "     ?"
    print(f"{nama:<20} {f['deteksi']:%H:%M:%S}  {d(f.get('deteksi'), f.get('terima'))}       {d(f.get('terima'), f.get('arsip'))}      "
          f"{d(f.get('arsip'), f.get('drive'))}         {telat}")
for label, a, b in (("terima dari kamera", "deteksi", "terima"), ("upload ke Drive", "arsip", "drive")):
    nilai = [(f[b] - f[a]).total_seconds() for f in foto.values() if f.get(a) and f.get(b)]
    if nilai:
        print(f"\n{label}: tengah {statistics.median(nilai):.1f} dtk, paling lama {max(nilai):.1f} dtk, {len(nilai)} foto")
if selisih:
    nilai = [v - dasar for v in selisih.values()]
    print(f"telat dari jepret (dibanding foto tercepat): tengah {statistics.median(nilai):.1f} dtk, paling lama {max(nilai):.1f} dtk")

print("\nSERTIFIKAT                               diminta   render(dtk)  PNG di Drive(dtk)  PDF di Drive(dtk)")
for nama, s in sert.items():
    if s.get("diminta"):
        print(f"{nama:<40} {s['diminta']:%H:%M:%S}  {d(s.get('diminta'), s.get('render'))}       "
              f"{d(s.get('render'), s.get('drive_png'))}             {d(s.get('render'), s.get('drive_pdf'))}")
if pilah:
    print("\nPEMILAHAN")
    for t, pesan in pilah:
        print(f"{t:%H:%M:%S}  {pesan}")
