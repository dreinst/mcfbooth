"""Verifikasi meja pilah: foto tanpa sesi masuk kotak masuk '!Need Organized/Camera <booth>',
dipilah ke folder hewan, sertifikat dibuat, lalu pembatalan mengembalikan semuanya.

Database pendaftaran dan Drive memakai tiruan (lihat uji_sertifikat.py). Tidak ada
jaringan yang disentuh.

    python3 uji/uji_pilah.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uji_drive_palsu as u  # noqa: E402
import uji_sertifikat as us  # noqa: E402

import httpx  # noqa: E402

FOTO = sorted((u.AKAR / "simulasi/local_archive/Budi_Ani_20260811_115043").glob("*.JPG"))


def jatuhkan(tether: Path, nama: str) -> None:
    shutil.copy2(FOTO[0], tether / nama)
    os.utime(tether / nama)          # jam mendarat = sekarang
    time.sleep(1.1)                  # nama di kotak masuk memakai jam (detik), jaga urutannya


def ganjil(c) -> list[dict]:
    kam = c.get("/api/pilah/kotak").json()["kamera"]
    return next((k["berkas"] for k in kam if k["nama"] == "Ganjil"), [])


def pohon(c) -> list[str]:
    return c.get("/api/pengaturan").json()["drive"]["statistik_palsu"]["pohon"]


def main() -> int:
    pg_port = u.port_bebas()
    pg = ThreadingHTTPServer(("127.0.0.1", pg_port), us.PostgRESTTiruan)
    threading.Thread(target=pg.serve_forever, daemon=True).start()
    os.environ.update({"PHOTOBOOTH_MODE": "petblessing", "PETBLESSING_API_URL": f"http://127.0.0.1:{pg_port}",
                       "PETBLESSING_BOOTH_TOKEN": us.TOKEN, "PETBLESSING_TIMEOUT": "2", "BOOTH_ID": "Ganjil",
                       "DRIVE_FOLDER_RAW_ID": "palsu-raw", "DRIVE_FOLDER_SERTIFIKAT_ID": "palsu-sert"})

    with tempfile.TemporaryDirectory() as tmp:
        kerja = Path(tmp)
        tether = kerja / "tether"
        tether.mkdir()
        shutil.copy2(FOTO[0], tether / "LAMA_0001.JPG")     # foto lama sebelum mode kotak dipakai

        with u.Server(kerja, u.port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=30) as c:
            print("== 1. Foto tanpa sesi masuk kotak masuk ==")
            for n in ("DSC00001.JPG", "DSC00002.JPG", "DSC00003.JPG"):
                jatuhkan(tether, n)
            isi = u.tunggu(lambda: (lambda b: b if len(b) == 3 else None)(ganjil(c)), 20) or ganjil(c)
            u.cek("tiga foto naik ke Camera Ganjil", len(isi) == 3, isi)
            u.cek("nama: booth + jam mendarat + nama kamera, urut jepret",
                  [b["nama"].split("_", 2)[2] for b in isi] == ["DSC00001.JPG", "DSC00002.JPG", "DSC00003.JPG"]
                  and all(b["nama"].startswith("Ganjil_") and b["jam"] for b in isi), isi)
            u.cek("letaknya di '!Need Organized/Camera Ganjil'",
                  all("palsu-raw/!Need Organized/Camera Ganjil/" in p for p in pohon(c)), pohon(c))
            u.cek("foto lama di tether tidak ikut masuk", not any("LAMA_0001" in p for p in pohon(c)))
            u.cek("tidak ada yang jatuh ke _tanpa_sesi", not (kerja / "archive" / "_tanpa_sesi").exists())
            u.cek("thumbnail tersaji", c.get(f"/api/pilah/thumb/{isi[0]['id']}").headers.get("content-type") == "image/jpeg")
            pp = c.get("/api/pilah/papan").json()
            u.cek("papan: kotak Ganjil 3, laptop ini 3 masuk dan 3 naik",
                  pp["kotak"] == [{"nama": "Ganjil", "jumlah": 3}] and pp["lokal"]["total"] == 3 and pp["lokal"]["uploaded"] == 3, pp)

            print("== 2. Cari hewan dari nomor urut ==")
            r = c.get("/api/pilah/cari", params={"q": "27a"}).json()
            u.cek("'27a' menemukan pemilik nomor 27 dan menunjuk huruf A",
                  len(r["hasil"]) == 1 and r["huruf"] == "A" and [h["label"] for h in r["hasil"][0]["hewan"]] == ["027A", "027B"], r)
            u.cek("nomor lain tidak ikut", c.get("/api/pilah/cari", params={"q": "2"}).json()["hasil"] == [])

            print("== 3. Pilah: dua foto pertama milik 027A ==")
            r = c.post("/api/pilah/tetapkan", json={"file_ids": [isi[1]["id"], isi[0]["id"]], "owner_id": us.OWNER,
                                                    "pet_id": us.PET_A, "terbaik": isi[0]["id"]})
            h = r.json()
            u.cek("dua foto dipindah, sertifikat dimulai", r.status_code == 200 and h["dipindah"] == 2 and h["sertifikat"] and not h["gagal"], r.text[:300])
            sid = h["sesi"]["id"]
            u.cek("kotak masuk tinggal satu foto", [b["nama"].split("_", 2)[2] for b in ganjil(c)] == ["DSC00003.JPG"], ganjil(c))
            folder = "palsu-raw/027 Felicia Cynthia/027A Candy (Anjing)/"
            u.cek("foto ada di folder hewan dengan nama yang sama", sum(1 for p in pohon(c) if p.startswith(folder + "Ganjil_")) == 2, pohon(c))
            u.cek("berkas arsip pindah ke folder sesi", len(list((kerja / "archive" / h["sesi"]["session_code"]).glob("*.JPG"))) == 2)
            baris = u.tunggu(lambda: next((b for b in c.get("/api/pilah/papan").json()["sesi"]
                                           if b["id"] == sid and b["sertifikat"] == "uploaded" and b["tercatat"]), None), 30)
            u.cek("papan: 027A, 2 foto di Drive, sertifikat di Drive dan tercatat",
                  bool(baris) and baris["label"] == "027A" and baris["foto"] == 2 and baris["foto_drive"] == 2 and baris["kamera"] == ["Ganjil"], baris)
            u.cek("sertifikat naik ke folder Sertifikat pemilik",
                  any(p == "palsu-sert/027 Felicia Cynthia/027A_Candy_Felicia_Cynthia.pdf" for p in pohon(c)), pohon(c))
            u.cek("tautan sertifikat dan folder foto ditulis ke data pendaftaran",
                  bool(us.patch_untuk(us.PET_A, "certificate_url")) and bool(us.patch_untuk(us.PET_A, "photo_folder_url")))
            ulang = c.post("/api/pilah/tetapkan", json={"file_ids": [isi[0]["id"]], "owner_id": us.OWNER, "pet_id": us.PET_B})
            u.cek("foto yang sudah dipilah ditolak dengan pesan jelas", ulang.status_code == 422 and "kotak masuk" in ulang.text, ulang.text[:200])

            print("== 4. Jepretan sesudah pemilahan tetap ke kotak masuk ==")
            jatuhkan(tether, "DSC00004.JPG")
            u.cek("foto baru masuk kotak, bukan ke sesi yang baru dipilah",
                  bool(u.tunggu(lambda: len(ganjil(c)) == 2, 20)) and c.get(f"/api/sessions/{sid}").json()["foto"]["total"] == 2, ganjil(c))
            n_srt = sum(1 for p_ in pohon(c) if p_.startswith("palsu-sert/"))
            susulan = next(b for b in ganjil(c) if b["nama"].endswith("DSC00004.JPG"))
            h2 = c.post("/api/pilah/tetapkan", json={"file_ids": [susulan["id"]], "owner_id": us.OWNER, "pet_id": us.PET_A}).json()
            time.sleep(2)
            u.cek("foto susulan untuk hewan yang sudah bersertifikat hanya ditambahkan, sertifikat tidak diganti",
                  h2["dipindah"] == 1 and h2["tambahan"] and not h2["sertifikat"]
                  and sum(1 for p_ in pohon(c) if p_.startswith("palsu-sert/")) == n_srt, h2)
            u.cek("membatalkan foto susulan tidak mengosongkan tautan sertifikat",
                  c.post(f"/api/pilah/batalkan/{h2['sesi']['id']}").status_code == 200
                  and not any(b["certificate_url"] is None for b in us.patch_untuk(us.PET_A, "certificate_url")))

            print("== 5. Batalkan: foto kembali, sertifikat dan catatan dibersihkan ==")
            r = c.post(f"/api/pilah/batalkan/{sid}")
            u.cek("dua foto dikembalikan", r.status_code == 200 and r.json()["dikembalikan"] == 2, r.text[:200])
            u.cek("kotak masuk berisi empat foto lagi, urut", [b["nama"].split("_", 2)[2] for b in ganjil(c)]
                  == ["DSC00001.JPG", "DSC00002.JPG", "DSC00003.JPG", "DSC00004.JPG"], ganjil(c))
            u.cek("sesinya hilang dari papan", all(b["id"] != sid for b in c.get("/api/pilah/papan").json()["sesi"]))
            u.cek("tautan sertifikat di data pendaftaran dikosongkan",
                  bool(u.tunggu(lambda: any(b["certificate_url"] is None for b in us.patch_untuk(us.PET_A, "certificate_url")), 10)))
            u.cek("thumbnail foto yang kembali masih tersaji", c.get(f"/api/pilah/thumb/{isi[0]['id']}").status_code == 200)

            print("== 6. Sisihkan foto yang bukan foto hewan ==")
            r = c.post("/api/pilah/sisihkan", json={"file_ids": [isi[0]["id"]]})
            u.cek("satu foto disisihkan dan hilang dari kotak", r.json()["disisihkan"] == 1 and len(ganjil(c)) == 3, r.text)
            u.cek("letaknya di Camera Ganjil/Disisihkan", any("/Camera Ganjil/Disisihkan/" in p for p in pohon(c)), pohon(c))

            print("== 7. Alur lama (pilih hewan dulu) tetap jalan ==")
            s = c.post("/api/sessions", json={"owner_id": us.OWNER, "pet_id": us.PET_B}).json()
            jatuhkan(tether, "DSC00005.JPG")
            u.cek("foto saat sesi aktif masuk sesinya, bukan kotak masuk",
                  bool(u.tunggu(lambda: c.get(f"/api/sessions/{s['id']}").json()["foto"]["total"] == 1, 20)) and len(ganjil(c)) == 3)
            c.post(f"/api/sessions/{s['id']}/finish")
            u.cek("sertifikat otomatis saat Selesai",
                  bool(u.tunggu(lambda: (c.get(f"/api/sessions/{s['id']}/sertifikat").json() or [{}])[-1].get("status") == "uploaded", 30)))

        print("== 8. Server mati lalu hidup: tidak ada foto ganda, foto saat mati terambil ==")
        jatuhkan(tether, "DSC00006.JPG")                     # mendarat saat server mati
        db = sqlite3.connect(kerja / "sessions.db")
        sebelum = db.execute("SELECT COUNT(*) FROM photo_uploads").fetchone()[0]
        with u.Server(kerja, u.port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=30) as c:
            ada = u.tunggu(lambda: db.execute("SELECT COUNT(*) FROM photo_uploads WHERE local_path LIKE '%DSC00006.JPG'").fetchone()[0] == 1, 20)
            u.cek("foto yang mendarat saat server mati masuk kotak", bool(ada))
            time.sleep(4)                                    # satu putaran penjaga
            u.cek("foto lama tidak tercatat dua kali", db.execute("SELECT COUNT(*) FROM photo_uploads").fetchone()[0] == sebelum + 1,
                  db.execute("SELECT local_path FROM photo_uploads").fetchall())
            u.cek("tidak ada traceback di log server", not any("Traceback" in l for l in srv.log), [l for l in srv.log if "Traceback" in l][:3])

    print()
    if u.gagal:
        print(f"{u.gagal} GAGAL, {u.lulus} lulus")
        return 1
    print(f"SEMUA LULUS ({u.lulus})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
