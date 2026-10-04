"""Penjaga acara Pet Blessing: memeriksa semua bagian sekali (bawaan) atau terus-menerus sampai ada masalah (--jaga).

    ~/.venvs/mcfbooth/bin/python alat/jaga_acara.py            # satu kali, cetak ringkasan
    ~/.venvs/mcfbooth/bin/python alat/jaga_acara.py --jaga 60  # ulang tiap 60 detik, berhenti (kode 2) saat ada masalah

Yang diperiksa: server reg ulang lokal, nomor urut ganda atau salah pos, booth Mac, booth Windows (lewat SSH), kotak
masuk Drive, sertifikat gagal, terowongan VPS, alamat web Meja pilah, dan galat baru di log booth Mac.
"""
import json, ssl, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
LOG = AKAR / "logs" / "booth.log"
TANPA_TLS = ssl._create_unverified_context()


def ambil(url, batas=20):
    return json.loads(urllib.request.urlopen(url, timeout=batas, context=TANPA_TLS).read())


def sh(cmd, batas=40):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=batas).stdout.strip()
    except Exception as e:
        return f"(gagal: {str(e)[:60]})"


def psql(sql):
    return sh(["docker", "exec", "pblokal-db", "sh", "-c", f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "|" -c "{sql}"'])


def periksa(posisi_log):
    masalah, info = [], []
    # 1. Server reg ulang lokal
    try:
        s = ambil("https://127.0.0.1:8443/lokal/status")
        info.append(f"reg ulang: pemberi {s['pemberi']}, VPS {'tersambung' if s['vps_ok'] else 'PUTUS'}, {s['pesan']}")
        if not s["lokal_ok"]:
            masalah.append("server reg ulang lokal melaporkan lokal_ok = false")
        if s["pemberi"] != "lokal":
            masalah.append(f"pemberi nomor bukan lokal ({s['pemberi']})")
        if s["konflik"]:
            masalah.append(f"ada konflik sinkron: {str(s['konflik'])[:120]}")
        if not s["vps_ok"]:
            info.append("PERHATIAN: VPS tidak tersambung dari Mac (reg ulang lokal tetap jalan)")
    except Exception as e:
        masalah.append(f"server reg ulang lokal tidak menjawab: {str(e)[:80]}")
    # 2. Nomor urut
    try:
        a = psql("select desk, count(*), max(arrival_number) from api.checkins where post='reg_ulang' and checked_in_at > now() - interval '14 hours' group by 1 order by 1")
        info.append("check-in: " + a.replace("\n", " ; "))
        ganda = psql("select arrival_number from api.checkins where arrival_number is not null and checked_in_at > now() - interval '14 hours' group by 1 having count(*) > 1")
        if ganda:
            masalah.append(f"nomor urut ganda: {ganda.replace(chr(10), ', ')}")
        salah = psql("select count(*) from api.checkins where checked_in_at > now() - interval '14 hours' and ((desk='A' and arrival_number % 2 = 0) or (desk='B' and arrival_number % 2 = 1))")
        if salah not in ("0", ""):
            masalah.append(f"{salah} nomor urut tidak cocok ganjil genap dengan posnya")
    except Exception as e:
        masalah.append(f"basis data lokal tidak terbaca: {str(e)[:80]}")
    # 3. Booth Mac + Drive
    try:
        p = ambil("http://127.0.0.1:8000/api/pilah/papan", 40)
        kotak = ", ".join(f"{k['nama']} {k['jumlah']}" for k in p["kotak"])
        gagal = [b["label"] for b in p["sesi"] if b["sertifikat"] == "failed" or b["foto_gagal"]]
        macet = [b["label"] for b in p["sesi"] if b["sertifikat"] in ("render", "menunggu") and time.time() - datetime.fromisoformat(b["waktu"]).timestamp() > 240]
        info.append(f"booth Mac: Drive {'tersambung' if p['drive_ok'] else 'PUTUS'}, kotak masuk [{kotak}], dipilah {len(p['sesi'])}, siap cetak {p['cetak']['jumlah'] if p.get('cetak') else '-'}")
        if not p["drive_ok"]:
            masalah.append("booth Mac: Drive tidak terjangkau")
        if gagal:
            masalah.append(f"booth Mac: sertifikat atau foto gagal untuk {', '.join(gagal)}")
        if macet:
            masalah.append(f"booth Mac: sertifikat belum naik lebih dari 4 menit untuk {', '.join(macet)}")
    except Exception as e:
        masalah.append(f"booth Mac tidak menjawab: {str(e)[:80]}")
    # 4. Booth Windows
    # Skrip kecil di laptop Windows (C:\\Users\\Public\\jaga-booth.ps1): papan booth, baterai, dan Imaging Edge.
    w = sh(["ssh", "-o", "ConnectTimeout=10", "windows", "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\Public\\jaga-booth.ps1"], 60)
    try:
        baris = w.split("\n")
        pw = json.loads(baris[0])
        lok = pw.get("lokal") or {}
        gagal = [b["label"] for b in pw["sesi"] if b["sertifikat"] == "failed" or b["foto_gagal"]]
        bat = next((b for b in baris if b.startswith("BATERAI")), "BATERAI ? ?").split()
        remote = next((b for b in baris if b.startswith("REMOTE")), "REMOTE ?").split()[1]
        info.append(f"booth Windows: Drive {'tersambung' if pw['drive_ok'] else 'PUTUS'}, antre naik {lok.get('pending', 0)}, gagal {lok.get('failed', 0)}, dipilah {len(pw['sesi'])}, baterai {bat[1]}%{'' if bat[2] == '2' else ' TANPA CHARGER'}, Imaging Edge {remote}")
        if not pw["drive_ok"]:
            masalah.append("booth Windows: Drive tidak terjangkau")
        if lok.get("failed"):
            masalah.append(f"booth Windows: {lok['failed']} foto gagal naik ke Drive")
        if lok.get("pending", 0) > 8:
            masalah.append(f"booth Windows: {lok['pending']} foto mengantre naik (internet lambat?)")
        if gagal:
            masalah.append(f"booth Windows: sertifikat atau foto gagal untuk {', '.join(gagal)}")
        if bat[2] != "2" and bat[1].isdigit() and int(bat[1]) < 40:
            masalah.append(f"laptop Windows tanpa charger, baterai {bat[1]}%")
        if remote != "True":
            masalah.append("Imaging Edge Remote di Windows tertutup")
    except Exception:
        masalah.append(f"booth Windows tidak terbaca: {w[:120]}")
    # 5. Jalur internet
    for nama, url in (("terowongan reg ulang", "https://petblessing-lokal.187.53.129.205.sslip.io/lokal/status"),
                      ("halaman reg ulang online", "https://petblessings.vercel.app/checkin.html")):
        try:
            t = time.time()
            urllib.request.urlopen(url, timeout=20).read(200)
            info.append(f"{nama}: {time.time() - t:.2f} dtk")
        except Exception as e:
            masalah.append(f"{nama} gagal: {str(e)[:70]}")
    try:
        urllib.request.urlopen("https://pilah-pb.187.53.129.205.sslip.io/pilah.html", timeout=20)
        masalah.append("alamat web Meja pilah terbuka TANPA kata sandi")
    except urllib.error.HTTPError as e:
        if e.code != 401:
            masalah.append(f"alamat web Meja pilah menjawab {e.code}")
    except Exception as e:
        masalah.append(f"alamat web Meja pilah gagal: {str(e)[:70]}")
    # 6. Galat baru di log booth Mac (uji otomatis dengan Drive tiruan dilewati)
    try:
        ukuran = LOG.stat().st_size
        if ukuran < posisi_log:
            posisi_log = 0
        with open(LOG, errors="replace") as f:
            f.seek(posisi_log)
            baru = f.read()
        galat = [l for l in baru.split("\n") if " ERROR" in l and "/T/tmp" not in l]
        if galat:
            masalah.append(f"{len(galat)} galat baru di log booth Mac, terakhir: {galat[-1][24:170]}")
        posisi_log = ukuran
    except Exception:
        pass
    return masalah, info, posisi_log


def main():
    jaga = "--jaga" in sys.argv
    jeda = int(sys.argv[sys.argv.index("--jaga") + 1]) if jaga and len(sys.argv) > sys.argv.index("--jaga") + 1 else 60
    posisi = LOG.stat().st_size if jaga and LOG.exists() else max(0, LOG.stat().st_size - 20000) if LOG.exists() else 0
    putaran = 0
    while True:
        masalah, info, posisi = periksa(posisi)
        putaran += 1
        if not jaga or masalah or putaran % 10 == 1:
            print(f"== {datetime.now():%H.%M.%S} (putaran {putaran})")
            for i in info:
                print("  ", i)
        if masalah:
            print("MASALAH:")
            for m in masalah:
                print("  -", m)
            sys.stdout.flush()
            if jaga:
                sys.exit(2)
        elif not jaga:
            print("Tidak ada masalah.")
        if not jaga:
            return
        sys.stdout.flush()
        time.sleep(jeda)


main()
