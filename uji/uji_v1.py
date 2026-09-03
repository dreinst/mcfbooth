"""Verifikasi v1.1 tanpa Google Drive: watcher, arsip, thumbnail, SSE, layar tamu,
riwayat, dan pemulihan setelah restart.

Server dijalankan sungguhan di subprocess dengan folder kerja sementara, jadi
skrip ini tidak menyentuh sessions.db, tether_dropbox, atau arsip milikmu.
Google Drive sengaja tidak disentuh: tanpa credentials.json semua foto berhenti
di `pending`, dan itu yang diuji.

    python3 uji/uji_v1.py
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

AKAR = Path(__file__).resolve().parent.parent
FOTO_CONTOH = AKAR / "simulasi/local_archive/Budi_Ani_20260811_115043/IMG_0041.JPG"

lulus = gagal = 0


def cek(nama: str, syarat: bool, detail: object = "") -> None:
    global lulus, gagal
    if syarat:
        lulus += 1
        print(f"  ok    {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}" + (f"  → {detail}" if detail != "" else ""))


def port_bebas() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, kerja: Path, port: int):
        self.kerja, self.port = kerja, port
        self.proc: subprocess.Popen | None = None
        self.log: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "Server":
        k = self.kerja
        env = {
            **os.environ,
            "MCF_DB": str(k / "sessions.db"),
            "TETHER_DROPBOX": str(k / "tether"),
            "LOCAL_ARCHIVE": str(k / "archive"),
            "THUMBS": str(k / "thumbs"),
            "QR_CODES": str(k / "qr"),
            "GOOGLE_CREDENTIALS": str(k / "tidak-ada.json"),
            "GOOGLE_TOKEN": str(k / "tidak-ada-token.json"),
            "STABILITAS_DETIK": "0.4",
            "TENGGANG_SETELAH_SELESAI": "3",
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.server:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "info"],
            cwd=AKAR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        threading.Thread(target=lambda: [self.log.append(l.rstrip()) for l in self.proc.stdout],
                         daemon=True).start()
        batas = time.time() + 30
        while time.time() < batas:
            if self.proc.poll() is not None:
                raise RuntimeError("server mati saat start:\n" + "\n".join(self.log[-30:]))
            try:
                httpx.get(f"{self.url}/api/sessions", timeout=1)
                return self
            except httpx.HTTPError:
                time.sleep(0.15)
        raise RuntimeError("server tidak siap dalam 30 detik")

    def __exit__(self, *_) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class PendengarSSE:
    """Menyimpan tiap peristiwa SSE beserta waktunya."""

    def __init__(self, base: str, path: str):
        self.base, self.path = base, path
        self.peristiwa: list[tuple[float, dict]] = []
        self.halo: dict | None = None
        self.siap = threading.Event()
        threading.Thread(target=self._jalan, daemon=True).start()

    def _jalan(self) -> None:
        try:
            with httpx.Client(base_url=self.base, timeout=None) as c:
                with c.stream("GET", self.path) as r:
                    self.siap.set()
                    event = None
                    for line in r.iter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data = json.loads(line[5:].strip())
                            if event == "halo":
                                self.halo = data
                            else:
                                self.peristiwa.append((time.time(), data))
                            event = None
        except Exception:
            pass

    def tunggu(self, jenis: str, timeout: float = 10) -> dict | None:
        batas = time.time() + timeout
        while time.time() < batas:
            for _, d in self.peristiwa:
                if d.get("jenis") == jenis:
                    return d
            time.sleep(0.05)
        return None

    def jenis(self) -> list[str]:
        return [d.get("jenis") for _, d in self.peristiwa]


def tunggu(fn, timeout: float = 10, jeda: float = 0.1):
    batas = time.time() + timeout
    while time.time() < batas:
        hasil = fn()
        if hasil:
            return hasil
        time.sleep(jeda)
    return None


def main() -> int:
    kerja = Path(tempfile.mkdtemp(prefix="mcf-uji-v1-"))
    port = port_bebas()

    print("\n== 1. Server naik, halaman & pemeriksaan awal ==")
    with Server(kerja, port) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        cek("GET / menyajikan halaman operator", c.get("/").status_code == 200)
        cek("GET /tamu menyajikan halaman tamu", "tamu" in c.get("/tamu").text.lower())
        cek("aset app.js & ui.css tersedia",
            c.get("/app.js").status_code == 200 and c.get("/ui.css").status_code == 200)
        cek("favicon tersedia", c.get("/favicon.svg").status_code == 200)

        pf = c.get("/api/preflight").json()
        cek("preflight: tanpa kredensial → Mulai Sesi dihalangi dengan alasan",
            pf["drive"]["keadaan"] == "tanpa_credentials" and pf["boleh_mulai"] is False and pf["alasan_tidak_boleh"], pf["drive"])
        cek("preflight: watcher aktif & folder tether ada", pf["watcher_aktif"] and pf["tether_ada"])
        cek("preflight: layar tamu belum terhubung", pf["layar_tamu"] is False)
        cek("tampilan tamu awal = sambutan", c.get("/api/tampilan-tamu").json()["keadaan"] == "sambutan")
        cek("pengaturan terbaca", c.get("/api/pengaturan").json()["drive"]["scope"] == "drive.file")

        print("\n== 2. SSE: peristiwa sampai, jendela tamu terdeteksi ==")
        op = PendengarSSE(srv.url, "/api/peristiwa")
        op.siap.wait(5); time.sleep(0.3)          # operator dulu — ia yang harus diberi tahu
        tamu = PendengarSSE(srv.url, "/api/peristiwa-tamu")
        tamu.siap.wait(5); time.sleep(0.5)
        cek("halo dikirim saat tersambung", tunggu(lambda: op.halo, 3) is not None)
        cek("preflight melihat jendela tamu lewat SSE",
            tunggu(lambda: c.get("/api/preflight").json()["layar_tamu"], 3) is True)
        cek("operator diberi tahu layar tamu tersambung", op.tunggu("layar_tamu", 3) is not None)

        t0 = time.time()
        sesi = c.post("/api/sessions", json={"guest_name": "Uji SSE"}).json()
        ev = op.tunggu("sesi_mulai", 3)
        cek("sesi_mulai sampai ke operator < 1 detik", ev is not None and time.time() - t0 < 1.5)
        cek("sesi_mulai sampai ke tamu", tamu.tunggu("sesi_mulai", 3) is not None)
        cek("tampilan tamu = memotret", c.get("/api/tampilan-tamu").json()["keadaan"] == "memotret")

        print("\n== 3. Watcher: foto jatuh → arsip, thumbnail, SSE, tampilan tamu ==")
        tether = kerja / "tether"
        t_drop = time.time()
        data = FOTO_CONTOH.read_bytes()
        with open(tether / "IMG_0041.JPG", "wb") as f:      # ditulis dua tahap seperti tethering
            f.write(data[: len(data) // 2]); f.flush(); time.sleep(0.3); f.write(data[len(data) // 2:])
        fb = op.tunggu("foto_baru", 15)
        cek("foto_baru sampai ke operator", fb is not None, op.jenis())
        cek("foto_baru terdeteksi dalam < 6 detik", fb is not None and time.time() - t_drop < 6)
        cek("peristiwa membawa data foto", fb is not None and fb["foto"]["status"] == "pending")
        kode = sesi["session_code"]
        cek("berkas disalin ke arsip", (kerja / "archive" / kode / "IMG_0041.JPG").exists())
        thumb = tunggu(lambda: (kerja / "thumbs" / kode / "IMG_0041.jpg").exists(), 5)
        cek("thumbnail dibuat", bool(thumb))
        r = c.get(f"/api/thumb/{kode}/IMG_0041.jpg")
        cek("thumbnail tersaji lewat API", r.status_code == 200 and len(r.content) > 500)
        cek("nama asli .JPG juga diterima", c.get(f"/api/thumb/{kode}/IMG_0041.JPG").status_code == 200)
        cek("path traversal ditolak (segmen ter-encode)",
            c.get("/api/thumb/%2e%2e/sessions.db").status_code == 404
            and c.get(f"/api/thumb/{kode}/..%2F..%2Fsessions.db").status_code == 404
            and c.get("/api/qr/%2e%2e%2fsessions.db").status_code == 404)
        cek("byte nul di path → 404, bukan 500", c.get("/api/qr/abc%00").status_code == 404)
        cek("POST lintas situs ditolak 403",
            c.post(f"/api/sessions/{sesi['id']}/finish", headers={"Origin": "http://jahat.example"}).status_code == 403)
        fotos = c.get(f"/api/sessions/{sesi['id']}/photos").json()
        cek("daftar foto berisi 1 pending", len(fotos) == 1 and fotos[0]["status"] == "pending")
        tt = c.get("/api/tampilan-tamu").json()
        cek("tampilan tamu memuat thumbnail", tt["keadaan"] == "memotret" and len(tt["fotos"]) == 1, tt)
        cek("operator tahu foto menunggu Drive", op.tunggu("foto_menunggu_drive", 5) is not None)
        s2 = c.get(f"/api/sessions/{sesi['id']}").json()
        cek("foto_terakhir_at terisi", bool(s2["foto_terakhir_at"]))
        cek("hitungan pending = 1", s2["foto"]["pending"] == 1)

        # Berkas yang sama dilaporkan lagi (created + modified) → tidak dobel.
        os.utime(tether / "IMG_0041.JPG")
        time.sleep(2)
        cek("berkas yang sama tidak dicatat dua kali",
            len(c.get(f"/api/sessions/{sesi['id']}/photos").json()) == 1)

        print("\n== 4. Retry tanpa Drive ==")
        r = c.post(f"/api/photos/{fotos[0]['id']}/retry")
        cek("retry foto pending diterima", r.status_code == 200, r.text)
        r = c.post(f"/api/sessions/{sesi['id']}/retry-failed")
        cek("retry-failed menghitung yang menggantung", r.json()["ok"] is True)
        r = c.post(f"/api/sessions/{sesi['id']}/drive")
        cek("pasang Drive ditolak dengan 503 yang jelas", r.status_code == 503 and r.json()["galat"] == "drive_tidak_siap")

        print("\n== 5. Selesai, tenggang, dan QR dari Riwayat ==")
        c.post(f"/api/sessions/{sesi['id']}/finish")
        cek("sesi_selesai sampai ke tamu", tamu.tunggu("sesi_selesai", 3) is not None)
        cek("tanpa Drive, tampilan tamu kembali ke sambutan",
            c.get("/api/tampilan-tamu").json()["keadaan"] == "sambutan")
        shutil.copy2(FOTO_CONTOH, tether / "IMG_0042.JPG")      # dalam tenggang 3 detik
        fb2 = tunggu(lambda: next((d for _, d in op.peristiwa
                                   if d.get("jenis") == "foto_baru" and d["foto"]["id"] != fotos[0]["id"]), None), 10)
        cek("foto sesaat setelah Selesai masih masuk ke sesi itu",
            fb2 is not None and fb2.get("setelah_selesai") is True and fb2["session_id"] == sesi["id"], fb2)
        time.sleep(4)                                            # tenggang lewat
        shutil.copy2(FOTO_CONTOH, tether / "IMG_0043.JPG")
        ts = op.tunggu("foto_tanpa_sesi", 10)
        cek("foto di luar tenggang diamankan & operator diberi tahu", ts is not None, op.jenis())
        cek("berkasnya ada di _tanpa_sesi", (kerja / "archive" / "_tanpa_sesi" / "IMG_0043.JPG").exists())
        cek("preflight menghitung foto tanpa sesi", c.get("/api/preflight").json()["foto_tanpa_sesi"] == 1)

        r = c.post(f"/api/sessions/{sesi['id']}/tampilkan-qr")
        cek("Tampilkan QR ditolak untuk sesi tanpa Drive", r.status_code == 503)
        c.post("/api/tanpa-sesi/akui")
        cek("setelah Mengerti, hitungan foto tanpa sesi kembali 0",
            c.get("/api/preflight").json()["foto_tanpa_sesi"] == 0)
        r = c.delete("/api/tampilan-tamu/qr")
        cek("Kembali ke sambutan memaksa layar tamu ke sambutan",
            r.status_code == 200 and c.get("/api/tampilan-tamu").json().get("dipaksa") is True)

        print("\n== 6. Riwayat & ringkasan ==")
        rk = c.get("/api/sessions/ringkasan").json()
        cek("ringkasan: 1 sesi, 1 bermasalah", rk["total"] == 1 and rk["bermasalah"] == 1, rk)
        cek("nama serupa hari ini terhitung", c.get("/api/sessions/nama-serupa", params={"q": "uji sse"}).json()["jumlah"] == 1)
        riwayat = c.get("/api/sessions").json()
        cek("riwayat memuat hitungan foto", riwayat["sesi"][0]["foto"]["total"] == 2, riwayat["sesi"][0]["foto"])

        print("\n== 7. Restart: pending diulang, tidak ada yang hilang ==")
        sesi_id = sesi["id"]

    with Server(kerja, port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        time.sleep(1.5)
        cek("server naik lagi dengan data utuh", c.get(f"/api/sessions/{sesi_id}").status_code == 200)
        cek("pemulihan mengulang foto pending",
            any("Pemulihan" in l and "pending diulang" in l for l in srv.log), srv.log[-8:])
        cek("foto tetap pending, bukan hilang atau dianggap terupload",
            c.get(f"/api/sessions/{sesi_id}").json()["foto"]["pending"] == 2)
        galat = [l for l in srv.log if "Traceback" in l or "ERROR:    " in l]
        cek("tidak ada traceback di log server", not galat, galat[:3])

    shutil.rmtree(kerja, ignore_errors=True)
    print("\n" + (f"SEMUA LULUS ({lulus})" if not gagal else f"{gagal} GAGAL, {lulus} lulus"))
    return 0 if not gagal else 1


if __name__ == "__main__":
    sys.exit(main())
