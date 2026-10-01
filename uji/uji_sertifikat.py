"""Verifikasi mode Pet Blessing: scan QR → sesi per hewan → foto pilihan →
sertifikat PNG+PDF → Drive "2. Result/027 Pemilik/027A Hewan" → tautan ke database pendaftaran.

Database pendaftaran (PostgREST) digantikan server tiruan di proses ini, Drive
memakai tiruan MCF_DRIVE_PALSU. Tidak ada jaringan yang disentuh.

    python3 uji/uji_sertifikat.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uji_drive_palsu as u  # noqa: E402  (Server, cek, tunggu, jatuhkan, port_bebas)

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

OWNER = "3f2a91c4-1111-4a2b-8c3d-000000000001"
PET_A = "aaaaaaaa-0000-4000-8000-000000000001"
PET_B = "aaaaaaaa-0000-4000-8000-000000000002"
TOKEN = "token-uji-booth"


class PostgRESTTiruan(BaseHTTPRequestHandler):
    mati = False
    patch: list[tuple[str, dict]] = []
    auth_salah = 0

    def log_message(self, *a):  # senyap
        pass

    def _jawab(self, kode: int, isi=None):
        badan = json.dumps(isi).encode() if isi is not None else b""
        self.send_response(kode)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(badan)))
        self.end_headers()
        self.wfile.write(badan)

    def _pagar(self) -> bool:
        if PostgRESTTiruan.mati:
            self._jawab(503, {"message": "mati"})
            return False
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            PostgRESTTiruan.auth_salah += 1
            self._jawab(401, {"message": "JWT"})
            return False
        return True

    def do_GET(self):
        if not self._pagar():
            return
        if self.path.startswith("/owners?"):
            self._jawab(200, [
                {"id": OWNER, "queue_number": 88, "name": "felicia CYNTHIA", "is_test": False,
                 "checkins": [{"post": "reg_ulang", "arrival_number": 27}],
                 "pets": [{"id": PET_B, "name": "mochi", "type": "Kucing", "sticker_letter": "B", "hadir": True},
                          {"id": PET_A, "name": "Candy", "type": "Anjing", "sticker_letter": "A", "hadir": True},
                          {"id": "9b000000-3333-4a2b-8c3d-000000000003", "name": "Tidakikut", "type": "Kucing",
                           "sticker_letter": "C", "hadir": False}]},
                {"id": "9b000000-2222-4a2b-8c3d-000000000002", "queue_number": 1,
                 "name": "Testing Nomor 1", "is_test": True, "checkins": [],
                 "pets": [{"id": "9b000000-4444-4a2b-8c3d-000000000004", "name": "Uji", "type": "Anjing", "sticker_letter": "A"}]},
            ])
        else:
            self._jawab(404, {})

    def do_PATCH(self):
        if not self._pagar():
            return
        n = int(self.headers.get("Content-Length") or 0)
        PostgRESTTiruan.patch.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
        self._jawab(204)


def patch_untuk(pet: str, kolom: str) -> list[dict]:
    return [b for p, b in PostgRESTTiruan.patch if p == f"/pets?id=eq.{pet}" and kolom in b]


def main() -> int:
    pg_port = u.port_bebas()
    pg = ThreadingHTTPServer(("127.0.0.1", pg_port), PostgRESTTiruan)
    threading.Thread(target=pg.serve_forever, daemon=True).start()

    import os
    os.environ.update({"PHOTOBOOTH_MODE": "petblessing", "PETBLESSING_API_URL": f"http://127.0.0.1:{pg_port}",
                       "PETBLESSING_BOOTH_TOKEN": TOKEN, "PETBLESSING_TIMEOUT": "2"})

    with tempfile.TemporaryDirectory() as tmp:
        kerja = Path(tmp)
        (kerja / "tether").mkdir()
        with u.Server(kerja, u.port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=20) as c:
            print("== 1. Mode dan pencarian pemilik ==")
            pf = c.get("/api/preflight").json()
            u.cek("mode petblessing terbaca di preflight", pf.get("mode") == "petblessing" and pf.get("pb_siap"), pf.get("mode"))
            r = c.get("/api/pb/pemilik", params={"kode": OWNER})
            o = r.json()
            u.cek("UUID dari QR menemukan pemilik", r.status_code == 200 and o["nama"] == "Felicia Cynthia", r.text[:200])
            u.cek("hewan urut huruf stiker, membawa jenis dan label", [h["label"] for h in o["hewan"]] == ["027A", "027B"] and o["hewan"][0]["jenis"] == "Anjing", o["hewan"])
            u.cek("nomor = nomor kedatangan, nomor pendaftaran disimpan terpisah", o["nomor"] == 27 and o["nomor_daftar"] == 88)
            u.cek("hewan yang tidak dibawa tidak ditawarkan", all(h["nama"] != "Tidakikut" for h in o["hewan"]))
            belum = c.post("/api/sessions", json={"owner_id": "9b000000-2222-4a2b-8c3d-000000000002", "pet_id": "9b000000-4444-4a2b-8c3d-000000000004"})
            u.cek("peserta yang belum reg ulang ditolak dengan pesan jelas", belum.status_code in (409, 422) and "reg ulang" in belum.text, belum.text[:200])
            u.cek("kode 8 huruf dari WhatsApp juga dikenali", c.get("/api/pb/pemilik", params={"kode": "3F2A91C4"}).status_code == 200)
            u.cek("kode tak dikenal = 404", c.get("/api/pb/pemilik", params={"kode": "deadbeef"}).status_code == 404)
            u.cek("nama pemilik dan hewan dirapikan jadi kapital tiap kata", o["nama"] == "Felicia Cynthia" and o["hewan"][1]["nama"] == "Mochi", o)
            r = c.get("/api/pb/cari", params={"q": "cynthia fel"}).json()
            u.cek("cari nama: semua kata harus ada, urutan bebas", [x["id"] for x in r["hasil"]] == [OWNER] and r["hasil"][0]["hewan"] == ["Candy", "Mochi"], r)
            r = c.get("/api/pb/cari", params={"q": "027"}).json()
            u.cek("cari nomor kedatangan (nol di depan boleh)", [x["id"] for x in r["hasil"]] == [OWNER], r)
            u.cek("nama tak dikenal = daftar kosong", c.get("/api/pb/cari", params={"q": "zzz"}).json()["hasil"] == [])
            js = c.get("/tema.js").text
            u.cek("tema Pet Blessing dipasang lewat /tema.js", "data-pb" in js, js)
            u.cek("token booth terkirim di tiap permintaan", PostgRESTTiruan.auth_salah == 0)

            print("== 2. Sesi per hewan ==")
            r = c.post("/api/sessions", json={"owner_id": OWNER, "pet_id": PET_A})
            s = r.json()
            u.cek("sesi dibuat dari data pendaftaran", r.status_code == 201 and s["guest_name"] == "027A Candy (Felicia Cynthia)", r.text[:200])
            u.cek("data hewan tersimpan di sesi", s.get("pb", {}).get("jenis") == "Anjing" and s["pb"]["nomor"] == 27 and s["pb"]["label"] == "027A")
            u.cek("kode sesi ditulis ke pets.mcfbooth_session_code",
                  u.tunggu(lambda: patch_untuk(PET_A, "mcfbooth_session_code"), 10) and
                  patch_untuk(PET_A, "mcfbooth_session_code")[0]["mcfbooth_session_code"] == s["session_code"])
            salah = c.post("/api/sessions", json={"owner_id": OWNER, "pet_id": "bukan-hewan-ini"})
            u.cek("hewan yang bukan milik pemilik ditolak", salah.status_code in (409, 422), salah.status_code)

            u.jatuhkan(kerja / "tether", 2)
            fs = u.tunggu(lambda: (lambda x: x if len(x) == 2 and all(f["status"] == "uploaded" for f in x) else None)(
                c.get(f"/api/sessions/{s['id']}/photos").json()), 30)
            u.cek("dua foto masuk dan terupload", bool(fs))

            print("== 3. Sertifikat dari foto pilihan ==")
            r = c.post(f"/api/sessions/{s['id']}/sertifikat", json={"photo_id": fs[1]["id"]})
            u.cek("permintaan sertifikat diterima (202)", r.status_code == 202, r.text[:200])
            srt = u.tunggu(lambda: (lambda d: d[-1] if d and d[-1]["status"] == "uploaded" and d[-1]["tercatat"] else None)(
                c.get(f"/api/sessions/{s['id']}/sertifikat").json()), 40)
            u.cek("sertifikat sampai Drive dan tercatat", bool(srt), c.get(f"/api/sessions/{s['id']}/sertifikat").json())
            if srt:
                png, pdf = Path(srt["png_path"]), Path(srt["pdf_path"])
                u.cek("nama berkas label_hewan_pemilik", png.name == "027A_Candy_Felicia_Cynthia.png", png.name)
                with Image.open(png) as im:
                    u.cek("PNG berukuran A4 300 dpi", im.size == (3508, 2480), im.size)
                u.cek("PDF valid", pdf.read_bytes()[:5] == b"%PDF-")
                stat = c.get("/api/pengaturan").json()["drive"]["statistik_palsu"]
                pohon = [j for j in stat.get("pohon", []) if "027" in j]
                if os.environ.get("DRIVE_FOLDER_SERTIFIKAT_ID"):
                    # Folder panitia: foto di Raw/pemilik/hewan, sertifikat di Sertifikat/pemilik.
                    u.cek("foto di folder Raw panitia, per pemilik lalu per hewan",
                          sum(1 for j in pohon if j.startswith("palsu-raw/027 Felicia Cynthia/027A Candy/")) == 2, pohon)
                    u.cek("sertifikat di folder Sertifikat panitia, per pemilik",
                          sorted(j for j in pohon if j.startswith("palsu-sert/")) ==
                          ["palsu-sert/027 Felicia Cynthia/027A_Candy_Felicia_Cynthia.pdf",
                           "palsu-sert/027 Felicia Cynthia/027A_Candy_Felicia_Cynthia.png"], pohon)
                else:
                    u.cek("foto + sertifikat di folder pemilik lalu folder hewan",
                          sum(1 for j in pohon if "/027 Felicia Cynthia/027A Candy/" in j) == 4 and
                          any(j.endswith("/027A Candy/027A_Candy_Felicia_Cynthia.pdf") for j in pohon), pohon)
                tulis = patch_untuk(PET_A, "certificate_url")
                u.cek("tautan PDF ditulis ke pets.certificate_url", tulis and tulis[-1]["certificate_url"] == srt["link_pdf"], tulis)
                u.cek("pratinjau PNG tersaji", c.get(f"/api/sertifikat/{srt['id']}/berkas.png").headers["content-type"] == "image/png")
            lain = c.post(f"/api/sessions/{s['id']}/sertifikat", json={"photo_id": 99999})
            u.cek("foto dari luar sesi ditolak", lain.status_code == 422, lain.status_code)
            c.post(f"/api/sessions/{s['id']}/finish")

            r = c.get("/api/pb/pemilik", params={"kode": OWNER}).json()
            u.cek("scan ulang menunjukkan Candy sudah punya sertifikat",
                  r["hewan"][0]["sertifikat"] and r["hewan"][0]["sertifikat"]["status"] == "uploaded" and r["hewan"][1]["sertifikat"] is None)

            print("== 4. Wifi putus: sertifikat menunggu, lalu disusulkan ==")
            (kerja / "drive-mati").touch()
            PostgRESTTiruan.mati = True
            r = c.get("/api/pb/pemilik", params={"kode": OWNER})
            u.cek("pencarian tetap jalan dari salinan lokal", r.status_code == 200 and r.json()["dari_salinan"], r.text[:200])
            s2 = c.post("/api/sessions", json={"owner_id": OWNER, "pet_id": PET_B}).json()
            u.cek("sesi hewan kedua tetap bisa dimulai saat offline", s2.get("guest_name") == "027B Mochi (Felicia Cynthia)", s2)
            u.jatuhkan(kerja / "tether", 1, awal=60)
            f2 = u.tunggu(lambda: c.get(f"/api/sessions/{s2['id']}/photos").json(), 20)
            c.post(f"/api/sessions/{s2['id']}/sertifikat", json={"photo_id": f2[0]["id"]})
            srt2 = u.tunggu(lambda: (lambda d: d[-1] if d and d[-1]["status"] == "menunggu" else None)(
                c.get(f"/api/sessions/{s2['id']}/sertifikat").json()), 30)
            u.cek("sertifikat tetap dirender, status menunggu upload", bool(srt2) and Path(srt2["png_path"]).exists())
            (kerja / "drive-mati").unlink()
            PostgRESTTiruan.mati = False
            akhir = u.tunggu(lambda: (lambda d: d[-1] if d and d[-1]["status"] == "uploaded" and d[-1]["tercatat"] else None)(
                c.get(f"/api/sessions/{s2['id']}/sertifikat").json()), 40)
            u.cek("penjaga latar menyusulkan upload dan pencatatan", bool(akhir))
            u.cek("tautan Mochi tercatat", bool(patch_untuk(PET_B, "certificate_url")))
            pohon = c.get("/api/pengaturan").json()["drive"]["statistik_palsu"]["pohon"]
            pemilik = {j.split("/")[-3] for j in pohon if "/027A " in j or "/027B " in j}
            u.cek("hewan kedua masuk folder pemilik yang sama (tidak ada folder kembar)",
                  pemilik == {"027 Felicia Cynthia"} and any(j.endswith("027B_Mochi_Felicia_Cynthia.pdf") for j in pohon), pohon)
            u.cek("tidak ada traceback di log server", not any("Traceback" in l for l in srv.log),
                  [l for l in srv.log if "Traceback" in l or "Error" in l][:5])

    pg.shutdown()
    print()
    if u.gagal:
        print(f"{u.gagal} GAGAL, {u.lulus} lulus")
        return 1
    print(f"SEMUA LULUS ({u.lulus})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
