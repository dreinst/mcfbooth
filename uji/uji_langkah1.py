"""Verifikasi langkah 1.

README menaruh satu syarat selesai: "sesi bisa dibuat lewat API dan masih ada
setelah server di-restart". Skrip ini menagihnya secara harfiah — servernya
benar-benar dijalankan, dimatikan, lalu dijalankan lagi.

    python3 uji/uji_langkah1.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

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
    """uvicorn sungguhan di subprocess — bukan TestClient. Restart hanya berarti
    sesuatu kalau prosesnya memang mati."""

    def __init__(self, berkas_db: Path, port: int):
        self.berkas_db, self.port = berkas_db, port
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "Server":
        env = {**os.environ, "MCF_DB": str(self.berkas_db)}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.server:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "warning"],
            cwd=AKAR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        batas = time.time() + 30
        while time.time() < batas:
            if self.proc.poll() is not None:
                galat = self.proc.stderr.read().decode(errors="replace")
                raise RuntimeError(f"server mati saat start:\n{galat}")
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


def main() -> int:
    berkas_db = Path(tempfile.mkdtemp(prefix="mcf-uji-")) / "sessions.db"
    port = port_bebas()

    print("\n== 1. Buat sesi, dan satu-sesi-aktif dijaga ==")
    with Server(berkas_db, port) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        r = c.post("/api/sessions", json={"guest_name": "Budi & Ani"})
        cek("POST /api/sessions → 201", r.status_code == 201, r.status_code)
        sesi = r.json()
        sesi_id = sesi["id"]
        cek("kode sesi berpresisi detik",
            len(sesi["session_code"].rsplit("_", 1)[-1]) == 6, sesi["session_code"])
        cek("kode sesi memakai nama tamu",
            sesi["session_code"].startswith("Budi_Ani_"), sesi["session_code"])
        cek("status awal active", sesi["status"] == "active", sesi["status"])
        cek("belum menyentuh Drive",
            sesi["drive_folder_link"] is None and sesi["qr_path"] is None, sesi)
        cek("hitungan foto nol", sesi["foto"]["total"] == 0, sesi["foto"])

        r = c.post("/api/sessions", json={"guest_name": "Sarah"})
        cek("sesi kedua ditolak selagi ada yang aktif → 409", r.status_code == 409, r.status_code)
        cek("penolakan menyebut sesi yang menghalangi",
            r.json().get("sesi_aktif", {}).get("id") == sesi_id, r.json())

        r = c.post("/api/sessions", json={"guest_name": "   "})
        cek("nama kosong ditolak", r.status_code == 422, r.status_code)

        print("\n== 2. Ambil, cari, akhiri ==")
        cek("GET /api/sessions/{id}", c.get(f"/api/sessions/{sesi_id}").json()["id"] == sesi_id)
        cek("GET /api/sessions/{id} yang tidak ada → 404",
            c.get("/api/sessions/999999").status_code == 404)
        cek("GET /api/sessions/active", c.get("/api/sessions/active").json()["id"] == sesi_id)

        hasil = c.get("/api/sessions", params={"q": "budi"}).json()
        cek("cari huruf kecil menemukan 'Budi & Ani'", hasil["total"] == 1, hasil["total"])
        cek("cari yang tidak cocok kosong",
            c.get("/api/sessions", params={"q": "zzz"}).json()["total"] == 0)

        r = c.post(f"/api/sessions/{sesi_id}/finish")
        cek("POST finish → 200", r.status_code == 200, r.status_code)
        cek("status jadi done", r.json()["status"] == "done", r.json()["status"])
        cek("finished_at terisi", bool(r.json()["finished_at"]), r.json()["finished_at"])
        cek("finish dua kali ditolak → 409",
            c.post(f"/api/sessions/{sesi_id}/finish").status_code == 409)
        r = c.get("/api/sessions/active")
        cek("tidak ada lagi sesi aktif", r.status_code == 404, r.status_code)
        cek("404-nya memakai bentuk galat yang sama",
            r.json().get("galat") == "tidak_ada", r.json())

        print("\n== 3. Tabrakan kode sesi di detik yang sama ==")
        kode = []
        for _ in range(3):
            s = c.post("/api/sessions", json={"guest_name": "Budi"}).json()
            kode.append(s["session_code"])
            c.post(f"/api/sessions/{s['id']}/finish")
        cek("tiga sesi bernama sama semuanya berhasil dibuat", len(kode) == 3, kode)
        cek("kodenya tetap unik", len(set(kode)) == 3, kode)

        print("\n== 4. Klik ganda Mulai Sesi — POST serentak ==")
        # Enam POST bersamaan atas nama yang sama. Tanpa kunci tulis di
        # buat_sesi, lebih dari satu lolos cek 'active' — atau salah satunya
        # pecah di UNIQUE session_code dan operator dapat 500.
        status_race: list[int] = []
        kunci = threading.Lock()

        def tembak() -> None:
            with httpx.Client(base_url=srv.url, timeout=10) as cc:
                r = cc.post("/api/sessions", json={"guest_name": "Klik Ganda"})
                with kunci:
                    status_race.append(r.status_code)

        utas = [threading.Thread(target=tembak) for _ in range(6)]
        for t in utas:
            t.start()
        for t in utas:
            t.join()
        cek("tepat satu yang berhasil", status_race.count(201) == 1, status_race)
        cek("sisanya 409, bukan 500", sorted(set(status_race)) == [201, 409], status_race)
        c.post(f"/api/sessions/{c.get('/api/sessions/active').json()['id']}/finish")

        print("\n== 5. Pencarian: kapital non-ASCII dan wildcard LIKE ==")
        s = c.post("/api/sessions", json={"guest_name": "Élan Prima"}).json()
        cek("kapital non-ASCII ketemu lewat huruf kecil",
            c.get("/api/sessions", params={"q": "élan"}).json()["total"] == 1)
        cek("'%' dicari sebagai huruf, bukan cocok-semua",
            c.get("/api/sessions", params={"q": "%"}).json()["total"] == 0)
        cek("kode sesi utuh (ber-garis-bawah) tetap bisa dicari",
            c.get("/api/sessions", params={"q": s["session_code"]}).json()["total"] == 1)
        c.post(f"/api/sessions/{s['id']}/finish")

        print("\n== 6. Nama non-ASCII tidak menyusut jadi kosong ==")
        s = c.post("/api/sessions", json={"guest_name": "李明 🎉"}).json()
        cek("nama CJK dipertahankan di kode", s["session_code"].startswith("李明_"), s["session_code"])
        cek("nama CJK bisa dicari",
            c.get("/api/sessions", params={"q": "李明"}).json()["total"] == 1)
        c.post(f"/api/sessions/{s['id']}/finish")

    print("\n== 7. Restart server — syarat selesai langkah 1 ==")
    with Server(berkas_db, port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        r = c.get(f"/api/sessions/{sesi_id}")
        cek("sesi masih ada setelah proses server dimatikan", r.status_code == 200, r.status_code)
        cek("isinya utuh", r.json()["guest_name"] == "Budi & Ani", r.json().get("guest_name"))
        cek("seluruh riwayat utuh", c.get("/api/sessions").json()["total"] == 7,
            c.get("/api/sessions").json()["total"])

    print("\n" + (f"SEMUA LULUS ({lulus})" if not gagal else f"{gagal} GAGAL, {lulus} lulus"))
    return 0 if not gagal else 1


if __name__ == "__main__":
    sys.exit(main())
