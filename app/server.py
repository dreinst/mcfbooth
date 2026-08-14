"""Session Manager — web server dan routing (arsitektur-sistem-photobooth.md §3.1).

Langkah 1 dari rencana di README: kerangka server dan database saja. Belum
menyentuh Google Drive (langkah 2) maupun folder tethering (langkah 3), jadi
`drive_folder_id`, `drive_folder_link`, dan `qr_path` selalu null di sini —
itu bukan bug, itu batas langkah ini. Tampilan menyusul di langkah 4;
`prototipe/` masih berdiri sendiri dengan data karangan.

Jalankan:
    python3 -m uvicorn app.server:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db

# Galat yang sudah diduga dipetakan ke kode status di satu tempat, supaya
# db.py tidak perlu tahu apa-apa soal HTTP.
STATUS = {
    "nama_kosong": 422,
    "tidak_ada": 404,
    "sesi_masih_aktif": 409,
    "sudah_selesai": 409,
}


@asynccontextmanager
async def daur_hidup(app: FastAPI):
    db.siapkan()
    yield


app = FastAPI(
    title="MCF Photobooth — Session Manager",
    version="0.1.0",
    summary="Kerangka server dan database. Belum tersambung ke Drive atau kamera.",
    lifespan=daur_hidup,
)


@app.exception_handler(db.GalatDB)
async def tangani_galat_db(request, exc: db.GalatDB):
    return JSONResponse(
        status_code=STATUS.get(exc.kode, 400),
        content={"galat": exc.kode, "pesan": exc.pesan, **exc.data},
    )


class SesiBaru(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)


@app.post("/api/sessions", status_code=201)
def buat_sesi(muatan: SesiBaru):
    """Mulai Sesi. Di langkah 2 folder Drive dibuat di sini juga — sebelum
    jepretan pertama, bukan sesudahnya — supaya tautannya sudah ada sejak awal
    dan QR bisa dibuat ulang kapan saja (§1)."""
    return db.buat_sesi(muatan.guest_name)


@app.get("/api/sessions")
def cari_sesi(
    q: str = Query("", description="Cari di nama tamu atau kode sesi"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Tanpa `q`, ini daftar Riwayat: terbaru di atas."""
    return db.cari_sesi(q, limit, offset)


# Harus di atas /{sesi_id} — kalau tidak, "active" ditelan sebagai id.
@app.get("/api/sessions/active")
def sesi_aktif():
    sesi = db.sesi_aktif()
    if sesi is None:
        # Lewat GalatDB, bukan HTTPException, supaya bentuk badannya sama
        # dengan semua galat lain ({"galat", "pesan"}) — UI langkah 4 cukup
        # punya satu parser galat.
        raise db.GalatDB("Tidak ada sesi yang berjalan.", "tidak_ada")
    return sesi


@app.get("/api/sessions/{sesi_id}")
def ambil_sesi(sesi_id: int):
    return db.ambil_sesi(sesi_id)


@app.post("/api/sessions/{sesi_id}/finish")
def akhiri_sesi(sesi_id: int):
    """Selesai. Foto yang masih antre tidak dibatalkan — di langkah 3 Folder
    Watcher tetap menyelesaikan uploadnya ke folder yang sama."""
    return db.akhiri_sesi(sesi_id)


if __name__ == "__main__":
    import uvicorn

    # 127.0.0.1, bukan 0.0.0.0. Laptop tidak membuka port apa pun ke luar (§7,
    # PRD NFR4). Kalau nanti butuh diakses dari HP di LAN, itu keputusan sadar
    # yang ditulis eksplisit — bukan bawaan.
    uvicorn.run(app, host="127.0.0.1", port=8000)
