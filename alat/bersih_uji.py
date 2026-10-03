"""Bersihkan data uji Pet Blessing sebelum acara dimulai. Dijalankan di Mac panitia.

Tanpa argumen hanya MELIHAT apa yang akan dibersihkan. Dengan `--jalankan`:

1. Peserta uji (owners.is_test) dihapus di database lokal Mac dan di VPS, beserta hewan
   dan reg ulangnya, supaya nomor urut peserta asli mulai dari 1. VPS dicadangkan dulu.
2. Folder uji di Drive panitia ("NNN Testing Nomor N", "NNN Testing Booth") dan isi kotak
   masuk '!Need Organized' dibuang ke Sampah (bisa dipulihkan 30 hari).
3. Data sesi booth di Mac dan di laptop Windows utama dipindah ke folder cadangan, lalu
   server booth dinyalakan ulang dengan papan kosong.

    ~/.venvs/mcfbooth/bin/python alat/bersih_uji.py            # lihat saja
    ~/.venvs/mcfbooth/bin/python alat/bersih_uji.py --jalankan
"""

import re
import subprocess
import sys
import time
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))
from app import server  # noqa: E402,F401  (memuat .env)
from app import drive_client as d  # noqa: E402

JALAN = "--jalankan" in sys.argv
POLA_FOLDER = re.compile(r"^\d{3} Testing (Nomor \d+|Booth)$")
CAP = time.strftime("%Y%m%d-%H%M")
VPS = "root@100.71.16.42"


def sh(cmd: list[str], batas: int = 120) -> str:
    h = subprocess.run(cmd, capture_output=True, text=True, timeout=batas)
    return (h.stdout + h.stderr).strip()


def psql_lokal(sql: str) -> str:
    return sh(["docker", "exec", "pblokal-db", "psql", "-U", "petblessing", "-d", "petblessing", "-Atc", sql])


def psql_vps(sql: str) -> str:
    return sh(["ssh", "-o", "ConnectTimeout=10", VPS,
               f"docker exec petblessing-db psql -U petblessing -d petblessing -Atc \"{sql}\""])


print("MODE:", "MEMBERSIHKAN" if JALAN else "lihat saja (tambahkan --jalankan untuk membersihkan)")

print("\n== 1. Peserta uji di database ==")
LIHAT = ("select o.queue_number, o.name, coalesce(c.arrival_number::text, 'belum reg ulang') "
         "from api.owners o left join api.checkins c on c.owner_id = o.id and c.post = 'reg_ulang' "
         "where o.is_test order by 1")
print("lokal:", psql_lokal(LIHAT).replace("\n", " ; ") or "(tidak ada)")
print("VPS  :", psql_vps(LIHAT).replace("\n", " ; ") or "(tidak ada)")
if JALAN:
    print("cadangan VPS:", sh(["ssh", VPS, f"docker exec petblessing-db pg_dump -U petblessing -d petblessing | gzip > "
                               f"/root/petblessing-backup-sebelum-bersih-uji-{CAP}.sql.gz && ls -la /root/petblessing-backup-sebelum-bersih-uji-{CAP}.sql.gz"], 300))
    print("lokal dihapus:", psql_lokal("delete from api.owners where is_test"))
    print("VPS dihapus  :", psql_vps("delete from api.owners where is_test"))
    print("sisa reg ulang lokal:", psql_lokal("select count(*) from api.checkins where post = 'reg_ulang'"),
          "| VPS:", psql_vps("select count(*) from api.checkins where post = 'reg_ulang'"))

# Pengaman: kalau peserta asli sudah ada yang reg ulang, acara sudah berjalan. Kotak masuk
# dan data sesi booth mungkin berisi foto sungguhan, jadi tidak disentuh.
nyata = psql_lokal("select count(*) from api.checkins c join api.owners o on o.id = c.owner_id "
                   "where not o.is_test and c.post = 'reg_ulang'")
ACARA_JALAN = nyata.isdigit() and int(nyata) > 0
if ACARA_JALAN:
    print(f"\nPERHATIAN: sudah ada {nyata} peserta asli yang reg ulang. Kotak masuk dan data sesi booth "
          "TIDAK akan disentuh, hanya peserta uji dan folder uji.")

print("\n== 2. Drive panitia ==")
svc = d._svc()


def isi(folder: str, q: str = "") -> list[dict]:
    return svc.files().list(q=f"'{folder}' in parents and trashed=false {q}", fields="files(id,name,mimeType)",
                            pageSize=500).execute()["files"]


buang: list[dict] = []
for label, akar in (("Raw", d.FOLDER_RAW_ID), ("Sertifikat", d.FOLDER_SERTIFIKAT_ID)):
    for f in isi(akar, "and name contains 'Testing'"):
        if POLA_FOLDER.match(f["name"]):
            buang.append(f)
            print(f"folder uji: {label} / {f['name']}")
for kam in ([] if ACARA_JALAN else d.kamera_kotak() or []):
    for f in isi(kam["id"]):
        if f["mimeType"] == d.MIME_FOLDER:
            for g in isi(f["id"]):
                buang.append(g)
                print(f"kotak masuk: Camera {kam['nama']} / {f['name']} / {g['name']}")
        else:
            buang.append(f)
            print(f"kotak masuk: Camera {kam['nama']} / {f['name']}")
if not buang:
    print("(tidak ada yang perlu dibuang)")
if JALAN:
    for f in buang:
        svc.files().update(fileId=f["id"], body={"trashed": True}).execute()
    print(f"{len(buang)} folder/berkas dibuang ke Sampah Drive")

print("\n== 3. Data sesi booth ==")
print("Mac    :", sh(["sqlite3", str(AKAR / "sessions.db"), "select count(*) || ' sesi' from sessions"]))
PS_LIHAT = "cd 'E:\\Photobooth System'; (Get-ChildItem local_archive -Directory).Count.ToString() + ' folder arsip, ' + (Get-ChildItem tether_dropbox -File).Count + ' berkas di tether'"
print("Windows:", sh(["ssh", "-o", "ConnectTimeout=10", "windows", PS_LIHAT], 60) or "(tidak terjangkau)")
if JALAN and not ACARA_JALAN:
    # Mac: hentikan booth, pindahkan data, nyalakan lagi
    sh(["pkill", "-f", "uvicorn app.server:app --port 8000"])
    time.sleep(2)
    cad = AKAR / f"_uji-{CAP}"
    cad.mkdir(exist_ok=True)
    for nama in ("sessions.db", "sessions.db-wal", "sessions.db-shm", "local_archive", "thumbs", "qr_codes", "tether_dropbox"):
        p = AKAR / nama
        if p.exists():
            p.rename(cad / nama)
    for nama in ("local_archive", "thumbs", "qr_codes", "tether_dropbox"):
        (AKAR / nama).mkdir(exist_ok=True)
    subprocess.Popen(f"cd '{AKAR}' && nohup ~/.venvs/mcfbooth/bin/python -m uvicorn app.server:app --port 8000 > /tmp/mcfbooth-server.out 2>&1 &", shell=True)
    print(f"Mac: data uji dipindah ke {cad.name}/, booth dinyalakan ulang")
    PS = (f"cd 'E:\\Photobooth System'; Stop-ScheduledTask -TaskName PhotoboothServer -ErrorAction SilentlyContinue; "
          "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'uvicorn' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; "
          f"Start-Sleep 2; $c = '_uji-{CAP}'; New-Item -ItemType Directory -Force $c | Out-Null; "
          "foreach ($n in 'sessions.db','sessions.db-wal','sessions.db-shm','local_archive','thumbs','qr_codes','tether_dropbox') { if (Test-Path $n) { Move-Item $n $c } }; "
          "foreach ($n in 'local_archive','thumbs','qr_codes','tether_dropbox') { New-Item -ItemType Directory -Force $n | Out-Null }; "
          "Start-ScheduledTask -TaskName PhotoboothServer; 'Windows: data uji dipindah ke ' + $c + ', booth dinyalakan ulang'")
    print(sh(["ssh", "-o", "ConnectTimeout=10", "windows", PS], 120) or "Windows TIDAK terjangkau: bersihkan nanti saat tersambung")
    print("\nLaptop kedua (tanpa Tailscale): kalau sempat dipakai uji, tutup jendela hitamnya, hapus berkas "
          "sessions.db di folder paket, lalu klik dua kali Nyalakan Photobooth.cmd lagi.")
