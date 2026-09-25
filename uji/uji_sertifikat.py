"""Verifikasi mode Pet Blessing: scan QR → sesi per hewan → foto pilihan →
sertifikat PNG+PDF → Drive "3. Sertifikat" → tautan ke database pendaftaran.

Database pendaftaran (PostgREST) digantikan server tiruan di proses ini, Drive
memakai tiruan MCF_DRIVE_PALSU. Tidak ada jaringan yang disentuh.

    python3 uji/uji_sertifikat.py
"""

from __future__ import annotations

import json
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
                {"id": OWNER, "queue_number": 88, "name": "Felicia Cynthia", "is_test": False,
                 "pets": [{"id": PET_B, "name": "Mochi", "type": "Kucing"},
                          {"id": PET_A, "name": "Candy", "type": "Anjing"}]},
                {"id": "9b000000-2222-4a2b-8c3d-000000000002", "queue_number": 1,
                 "name": "Testing Nomor 1", "is_test": True, "pets": []},
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
    os.environ.update({"MCF_MODE": "petblessing", "PETBLESSING_API_URL": f"http://127.0.0.1:{pg_port}",
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
            u.cek("hewan diurutkan per nama dan membawa jenis", [h["nama"] for h in o["hewan"]] == ["Candy", "Mochi"] and o["hewan"][0]["jenis"] == "Anjing")
            u.cek("kode 8 huruf dari WhatsApp juga dikenali", c.get("/api/pb/pemilik", params={"kode": "3F2A91C4"}).status_code == 200)
            u.cek("kode tak dikenal = 404", c.get("/api/pb/pemilik", params={"kode": "deadbeef"}).status_code == 404)
            u.cek("token booth terkirim di tiap permintaan", PostgRESTTiruan.auth_salah == 0)

            print("== 2. Sesi per hewan ==")
            r = c.post("/api/sessions", json={"owner_id": OWNER, "pet_id": PET_A})
            s = r.json()
            u.cek("sesi dibuat dari data pendaftaran", r.status_code == 201 and s["guest_name"] == "Candy (Felicia Cynthia)", r.text[:200])
            u.cek("data hewan tersimpan di sesi", s.get("pb", {}).get("jenis") == "Anjing" and s["pb"]["nomor"] == 88)
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
                u.cek("nama berkas nomor_hewan_pemilik", png.name == "088_Candy_Felicia_Cynthia.png", png.name)
                with Image.open(png) as im:
                    u.cek("PNG berukuran A4 300 dpi", im.size == (3508, 2480), im.size)
                u.cek("PDF valid", pdf.read_bytes()[:5] == b"%PDF-")
                stat = c.get("/api/pengaturan").json()["drive"]["statistik_palsu"]
                u.cek("PNG dan PDF ada di folder 3. Sertifikat",
                      sorted(stat.get("berkas_sertifikat", [])) == ["088_Candy_Felicia_Cynthia.pdf", "088_Candy_Felicia_Cynthia.png"],
                      stat.get("berkas_sertifikat"))
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
            u.cek("sesi hewan kedua tetap bisa dimulai saat offline", s2.get("guest_name") == "Mochi (Felicia Cynthia)", s2)
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
