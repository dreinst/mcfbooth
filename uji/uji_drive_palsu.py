"""Verifikasi jalur Google Drive dengan Drive tiruan (MCF_DRIVE_PALSU=1).

Yang tidak bisa dibuktikan uji_v1 karena berhenti di `pending`: folder per
sesi, upload, QR sungguhan di layar tamu, retry, balapan saat Drive pulih,
penjaga latar, dan restart di tengah sesi. Tidak ada jaringan yang disentuh.

    python3 uji/uji_drive_palsu.py
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
FOTO_CONTOH = sorted((AKAR / "simulasi/local_archive/Budi_Ani_20260811_115043").glob("*.JPG"))

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


def tunggu(fn, timeout: float = 15, jeda: float = 0.1):
    batas = time.time() + timeout
    while time.time() < batas:
        hasil = fn()
        if hasil:
            return hasil
        time.sleep(jeda)
    return None


class Server:
    def __init__(self, kerja: Path, port: int, gagal_sekali: bool = False):
        self.kerja, self.port, self.gagal_sekali = kerja, port, gagal_sekali
        self.proc: subprocess.Popen | None = None
        self.log: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "Server":
        k = self.kerja
        env = {
            **os.environ,
            "MCF_DB": str(k / "sessions.db"), "TETHER_DROPBOX": str(k / "tether"),
            "LOCAL_ARCHIVE": str(k / "archive"), "THUMBS": str(k / "thumbs"), "QR_CODES": str(k / "qr"),
            "MCF_DRIVE_PALSU": "1", "MCF_DRIVE_PALSU_SAKLAR": str(k / "drive-mati"),
            "MCF_DRIVE_PALSU_JEDA": "0.3", "MCF_DRIVE_PALSU_GAGAL": "1" if self.gagal_sekali else "0",
            "STABILITAS_DETIK": "0.3", "TENGGANG_SETELAH_SELESAI": "4", "PENJAGA_DETIK": "3",
            "UPLOAD_PARALEL": "4",
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--log-level", "info"],
            cwd=AKAR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        threading.Thread(target=lambda: [self.log.append(l.rstrip()) for l in self.proc.stdout], daemon=True).start()
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
    def __init__(self, base: str, path: str):
        self.base, self.path = base, path
        self.peristiwa: list[dict] = []
        self.siap = threading.Event()
        threading.Thread(target=self._jalan, daemon=True).start()

    def _jalan(self) -> None:
        try:
            with httpx.Client(base_url=self.base, timeout=None) as c:
                with c.stream("GET", self.path) as r:
                    self.siap.set()
                    for line in r.iter_lines():
                        if line.startswith("data:"):
                            self.peristiwa.append(json.loads(line[5:].strip()))
        except Exception:
            pass

    def hitung(self, jenis: str) -> int:
        return sum(1 for d in self.peristiwa if d.get("jenis") == jenis)


def jatuhkan(tether: Path, n: int, awal: int = 41) -> None:
    for i in range(n):
        shutil.copy2(FOTO_CONTOH[i % len(FOTO_CONTOH)], tether / f"IMG_{awal + i:04d}.JPG")
        time.sleep(0.15)


def foto(c, sid):
    return c.get(f"/api/sessions/{sid}/photos").json()


def semua_uploaded(c, sid, n):
    return lambda: (lambda fs: len(fs) == n and all(f["status"] == "uploaded" for f in fs))(foto(c, sid))


def statistik(c):
    return c.get("/api/pengaturan").json()["drive"]["statistik_palsu"]


def main() -> int:
    kerja = Path(tempfile.mkdtemp(prefix="mcf-uji-drive-"))
    tether = kerja / "tether"
    saklar = kerja / "drive-mati"

    print("\n== 1. Sesi dengan Drive tersambung: folder, QR, upload (1 kegagalan disengaja) ==")
    with Server(kerja, port_bebas(), gagal_sekali=True) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        op = PendengarSSE(srv.url, "/api/peristiwa"); op.siap.wait(5); time.sleep(0.3)
        pf = c.get("/api/preflight").json()
        cek("preflight: Drive palsu terhubung & boleh mulai", pf["drive_terhubung"] and pf["boleh_mulai"], pf["alasan_tidak_boleh"])
        cek("struktur Drive: induk, QR, Result", pf["drive_struktur"] and pf["drive_struktur"]["qr"] and pf["drive_struktur"]["result"])

        t0 = time.time()
        a = c.post("/api/sessions", json={"guest_name": "Andi & Tia"}).json()
        cek("POST /api/sessions kembali seketika (< 1 detik)", time.time() - t0 < 1.0)
        cek("folder dipasang di latar → sesi_drive_terpasang", tunggu(lambda: op.hitung("sesi_drive_terpasang") >= 1, 8))
        a = c.get(f"/api/sessions/{a['id']}").json()
        cek("sesi punya link Drive & qr_path", a["drive_folder_link"] and a["qr_path"], a)
        cek("gambar QR tersaji", c.get(f"/api/qr/{a['session_code']}").status_code == 200)
        cek("QR ikut diupload ke folder '1. QR'", statistik(c)["upload_sukses"] >= 1)

        jatuhkan(tether, 2)
        cek("dua foto terupload (satu setelah retry)", tunggu(semua_uploaded(c, a["id"], 2), 20), foto(c, a["id"]))
        fs = foto(c, a["id"])
        cek("foto yang gagal sekali punya retry_count 1, bukan diulang tanpa henti",
            sorted(f["retry_count"] for f in fs) == [0, 1], [f["retry_count"] for f in fs])
        st = statistik(c)
        cek("tepat satu folder sesi dibuat", st["folder_sesi_dibuat"] == 1, st)
        cek("tidak ada berkas ganda di folder sesi",
            all(len(v) == len(set(v)) for v in st["berkas_per_folder_sesi"].values()), st["berkas_per_folder_sesi"])
        tt = c.get("/api/tampilan-tamu").json()
        cek("layar tamu memotret dengan 2 thumbnail", tt["keadaan"] == "memotret" and len(tt["fotos"]) == 2, tt)

        c.post(f"/api/sessions/{a['id']}/finish")
        tt = c.get("/api/tampilan-tamu").json()
        cek("setelah Selesai layar tamu = qr dengan QR ada & foto_count total",
            tt["keadaan"] == "qr" and tt["qr_ada"] and tt["foto_count"] == 2, tt)
        Path(a["qr_path"]).unlink()
        cek("PNG QR yang hilang dibuat ulang saat diminta",
            c.get(f"/api/qr/{a['session_code']}").status_code == 200 and Path(a["qr_path"]).exists())

        print("\n== 2. Drive putus saat Mulai Sesi, pulih → satu folder walau upload paralel ==")
        saklar.touch()
        pf = c.get("/api/preflight").json()
        cek("offline: Mulai Sesi tidak dihalangi, hanya peringatan",
            pf["drive"]["keadaan"] == "offline" and pf["boleh_mulai"] and pf["peringatan_mulai"], pf["alasan_tidak_boleh"])
        b = c.post("/api/sessions", json={"guest_name": "Bima"}).json()
        time.sleep(1.0)
        cek("sesi tanpa folder Drive", c.get(f"/api/sessions/{b['id']}").json()["drive_folder_id"] is None)
        jatuhkan(tether, 6, awal=51)
        cek("6 foto pending menunggu Drive", tunggu(lambda: len(foto(c, b["id"])) == 6 and all(f["status"] == "pending" for f in foto(c, b["id"])), 15))
        cek("operator diberi tahu foto menunggu Drive", tunggu(lambda: op.hitung("foto_menunggu_drive") >= 1, 5))
        sebelum = statistik(c)["folder_sesi_dibuat"]

        saklar.unlink()
        # Dua pemicu sekaligus: tombol "Coba lagi semuanya" dan penjaga latar.
        r = c.post(f"/api/sessions/{b['id']}/retry-failed").json()
        cek("retry-failed mengantrekan foto pending", r["ok"])
        cek("semua 6 foto terupload", tunggu(semua_uploaded(c, b["id"], 6), 30), foto(c, b["id"]))
        st = statistik(c)
        cek("HANYA SATU folder Drive dibuat untuk sesi itu", st["folder_sesi_dibuat"] == sebelum + 1, st["folder_sesi_dibuat"])
        b = c.get(f"/api/sessions/{b['id']}").json()
        isi = st["berkas_per_folder_sesi"].get(b["drive_folder_id"], [])
        cek("keenam foto ada di folder yang ditunjuk QR", len(isi) == 6, isi)

        print("\n== 3. Penjaga latar: upload gagal di tengah sesi diulang sendiri saat Drive pulih ==")
        saklar.touch()
        jatuhkan(tether, 2, awal=61)
        cek("2 foto baru menunggu (Drive mati)",
            tunggu(lambda: len(foto(c, b["id"])) == 8 and sum(f["status"] == "pending" for f in foto(c, b["id"])) == 2, 15))
        saklar.unlink()
        cek("penjaga mengupload tanpa klik operator", tunggu(semua_uploaded(c, b["id"], 8), 30), [f["status"] for f in foto(c, b["id"])])
        cek("tetap satu folder untuk sesi itu", statistik(c)["folder_sesi_dibuat"] == sebelum + 1)

        print("\n== 4. Tenggang dibatalkan saat operator mengetik nama berikutnya ==")
        c.post(f"/api/sessions/{b['id']}/finish")
        c.post("/api/sessions/bersiap")
        shutil.copy2(FOTO_CONTOH[0], tether / "IMG_0070.JPG")
        cek("jepretan uji tidak masuk ke folder tamu sebelumnya",
            tunggu(lambda: (kerja / "archive" / "_tanpa_sesi" / "IMG_0070.JPG").exists(), 10)
            and len(foto(c, b["id"])) == 8)

        print("\n== 5. Restart di tengah sesi: berkas yang mendarat saat server mati ikut sesi ==")
        d = c.post("/api/sessions", json={"guest_name": "Dewi"}).json()
        tunggu(lambda: c.get(f"/api/sessions/{d['id']}").json()["drive_folder_id"], 8)
        d_id = d["id"]

    time.sleep(0.5)
    jatuhkan(tether, 2, awal=81)
    with Server(kerja, port_bebas()) as srv, httpx.Client(base_url=srv.url, timeout=10) as c:
        cek("pemulihan memproses berkas yang mendarat saat server mati",
            tunggu(lambda: len(foto(c, d_id)) == 2, 15), [f["status"] for f in foto(c, d_id)])
        cek("dan mengupload keduanya", tunggu(semua_uploaded(c, d_id, 2), 20))
        cek("foto lama di tether (sesi sebelumnya) tidak ikut ditempel ke sesi Dewi", len(foto(c, d_id)) == 2)
        galat = [l for l in srv.log if "Traceback" in l or "ERROR:    " in l]
        cek("tidak ada traceback di log server", not galat, galat[:3])

    shutil.rmtree(kerja, ignore_errors=True)
    print("\n" + (f"SEMUA LULUS ({lulus})" if not gagal else f"{gagal} GAGAL, {lulus} lulus"))
    return 0 if not gagal else 1


if __name__ == "__main__":
    sys.exit(main())
