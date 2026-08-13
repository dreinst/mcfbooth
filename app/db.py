"""Session Log — akses SQLite (arsitektur-sistem-photobooth.md §3.3).

Satu berkas database lokal. Ia yang menghubungkan keempat komponen sistem —
bukan state di memory — supaya tidak ada yang hilang kalau salah satu bagian
di-restart (§3). Modul ini sengaja tidak tahu apa-apa soal HTTP: server.py yang
menerjemahkan galat di sini jadi kode status.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
BERKAS_DB = Path(os.environ.get("MCF_DB", AKAR / "sessions.db"))

STATUS_SESI = ("active", "done")
STATUS_FOTO = ("pending", "uploaded", "failed")

SKEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                INTEGER PRIMARY KEY,
    session_code      TEXT    NOT NULL UNIQUE,
    guest_name        TEXT    NOT NULL,
    drive_folder_id   TEXT,
    drive_folder_link TEXT,
    status            TEXT    NOT NULL CHECK (status IN ('active', 'done')),
    photo_count       INTEGER NOT NULL DEFAULT 0,
    started_at        TEXT    NOT NULL,
    finished_at       TEXT,
    qr_path           TEXT
);

CREATE TABLE IF NOT EXISTS photo_uploads (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    local_path    TEXT    NOT NULL,
    drive_file_id TEXT,
    status        TEXT    NOT NULL CHECK (status IN ('pending', 'uploaded', 'failed')),
    retry_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    uploaded_at   TEXT
);

/* Riwayat dicari lewat nama tamu — itu satu-satunya jalan masuk kalau QR-nya
   hilang (PRD FR13). Indeks status dipakai mencari sesi yang masih active saat
   aplikasi dibuka. */
CREATE INDEX IF NOT EXISTS idx_sessions_guest  ON sessions (guest_name);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions (status);
CREATE INDEX IF NOT EXISTS idx_photos_session  ON photo_uploads (session_id);
"""


class GalatDB(Exception):
    """Galat yang sudah diduga dan punya arti buat operator."""

    def __init__(self, pesan: str, kode: str, data: dict | None = None):
        super().__init__(pesan)
        self.pesan = pesan
        self.kode = kode
        self.data = data or {}


def sekarang() -> str:
    """Waktu lokal ber-offset. Operator dan berkas di disk hidup di zona waktu
    venue; menyimpan UTC polos membuat jam di Riwayat tidak cocok dengan jam di
    nama berkas."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def koneksi():
    """Satu koneksi per operasi. Folder Watcher (langkah 3) menulis dari thread
    lain sementara operator membaca; WAL membuat keduanya tidak saling mengunci,
    dan koneksi yang berumur pendek menghindari urusan check_same_thread."""
    conn = sqlite3.connect(BERKAS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def siapkan() -> None:
    BERKAS_DB.parent.mkdir(parents=True, exist_ok=True)
    with koneksi() as conn:
        conn.executescript(SKEMA)


# --------------------------------------------------------------- kode sesi


def _slug(nama: str) -> str:
    """Cerminan `kodeSesi()` di prototipe/app.js. Semua huruf dan angka
    dipertahankan — bukan hanya ASCII — supaya nama CJK atau ber-emoji tidak
    menyusut jadi string kosong dan kehilangan satu-satunya penanda yang bisa
    dicari operator."""
    keluar: list[str] = []
    for ch in nama.strip():
        if ch.isalnum():
            keluar.append(ch)
        elif keluar and keluar[-1] != "_":
            keluar.append("_")
    return "".join(keluar).strip("_")


def kode_sesi(nama: str, saat: datetime | None = None) -> str:
    saat = saat or datetime.now()
    return f"{_slug(nama) or 'Tamu'}_{saat:%Y%m%d_%H%M%S}"


def _kode_bebas(conn: sqlite3.Connection, dasar: str) -> str:
    """`session_code` itu UNIQUE dan sekaligus jadi nama folder di local_archive
    dan di Drive (§5). Dengan presisi detik, tabrakan butuh dua sesi di detik
    yang sama persis — jarang, tapi bukan mustahil kalau operator salah tekan.

    Yang tidak boleh terjadi: operator menekan Mulai Sesi di tengah acara lalu
    dapat galat. Jadi kodenya diberi akhiran, bukan ditolak.
    """
    kode, n = dasar, 2
    while conn.execute(
        "SELECT 1 FROM sessions WHERE session_code = ?", (kode,)
    ).fetchone():
        kode, n = f"{dasar}_{n}", n + 1
    return kode


# ------------------------------------------------------------------- sesi


def _hitungan_foto(conn: sqlite3.Connection, sesi_id: int) -> dict[str, int]:
    baris = conn.execute(
        "SELECT status, COUNT(*) AS n FROM photo_uploads WHERE session_id = ? GROUP BY status",
        (sesi_id,),
    ).fetchall()
    hitung = {s: 0 for s in STATUS_FOTO}
    for b in baris:
        hitung[b["status"]] = b["n"]
    hitung["total"] = sum(hitung[s] for s in STATUS_FOTO)
    return hitung


def _bentuk(conn: sqlite3.Connection, baris: sqlite3.Row) -> dict:
    """Hitungan foto diturunkan dari `photo_uploads`, bukan dibaca dari kolom
    `photo_count`. Kolomnya tetap ada dan tetap dijaga (arsitektur §3.3), tapi
    yang dikirim ke layar adalah hasil hitung — kolom turunan yang menyimpang
    dari tabel sumbernya adalah cara paling sunyi untuk berbohong ke operator,
    dan tiga penghitung di layar Sesi bergantung pada angka ini."""
    d = dict(baris)
    d["foto"] = _hitungan_foto(conn, baris["id"])
    return d


def buat_sesi(nama_tamu: str) -> dict:
    nama_tamu = (nama_tamu or "").strip()
    if not nama_tamu:
        raise GalatDB("Nama tamu tidak boleh kosong.", "nama_kosong")

    with koneksi() as conn:
        # Folder Watcher mengupload ke "sesi yang sedang active" (§3.2) — bentuk
        # tunggal, dan memang cuma boleh ada satu. Sesi kedua tidak ditutup
        # otomatis: aplikasi tidak pernah memutuskan sendiri kapan sesi selesai,
        # itu keputusan manusia. Yang dikembalikan ke pemanggil adalah sesi yang
        # menghalangi, supaya UI bisa menawarkan lanjutkan atau akhiri sekarang
        # (design.md §4).
        aktif = conn.execute(
            "SELECT * FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if aktif:
            raise GalatDB(
                f"Masih ada sesi berjalan atas nama {aktif['guest_name']}. "
                "Akhiri dulu sebelum memulai yang baru.",
                "sesi_masih_aktif",
                {"sesi_aktif": _bentuk(conn, aktif)},
            )

        kode = _kode_bebas(conn, kode_sesi(nama_tamu))
        cur = conn.execute(
            """INSERT INTO sessions (session_code, guest_name, status, started_at)
               VALUES (?, ?, 'active', ?)""",
            (kode, nama_tamu, sekarang()),
        )
        baris = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _bentuk(conn, baris)


def ambil_sesi(sesi_id: int) -> dict:
    with koneksi() as conn:
        baris = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (sesi_id,)
        ).fetchone()
        if baris is None:
            raise GalatDB(f"Sesi {sesi_id} tidak ada.", "tidak_ada")
        return _bentuk(conn, baris)


def sesi_aktif() -> dict | None:
    """Dipakai saat aplikasi dibuka: kalau ada sesi yang belum diakhiri, halaman
    Sesi menampilkannya di atas dengan pilihan lanjutkan atau akhiri sekarang
    (design.md §4). Tanpa ini, sesi yang tertinggal karena aplikasi tertutup di
    tengah acara tidak akan pernah kelihatan lagi."""
    with koneksi() as conn:
        baris = conn.execute(
            "SELECT * FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _bentuk(conn, baris) if baris else None


def akhiri_sesi(sesi_id: int) -> dict:
    with koneksi() as conn:
        baris = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (sesi_id,)
        ).fetchone()
        if baris is None:
            raise GalatDB(f"Sesi {sesi_id} tidak ada.", "tidak_ada")
        if baris["status"] == "done":
            # Bukan galat yang perlu ditakuti, tapi tetap ditolak: menimpa
            # finished_at menghapus jejak kapan sesi sebenarnya ditutup.
            raise GalatDB(
                f"Sesi {baris['session_code']} sudah diakhiri.",
                "sudah_selesai",
                {"sesi": _bentuk(conn, baris)},
            )

        conn.execute(
            "UPDATE sessions SET status = 'done', finished_at = ? WHERE id = ?",
            (sekarang(), sesi_id),
        )
        baris = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (sesi_id,)
        ).fetchone()
        return _bentuk(conn, baris)


def cari_sesi(q: str = "", limit: int = 20, offset: int = 0) -> dict:
    """Pencarian nama tamu — jalan masuk kalau QR fisik hilang (PRD FR13).
    Tanpa `q`, ia jadi daftar Riwayat biasa: terbaru di atas."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = (q or "").strip()

    where, arg = "", []
    if q:
        # LIKE di SQLite tidak case-insensitive untuk non-ASCII, jadi kedua sisi
        # diturunkan dulu. Nama tamu Indonesia jarang keluar ASCII, tapi
        # `_slug()` sengaja menerima semua huruf — pencariannya harus setara.
        where = "WHERE LOWER(guest_name) LIKE ? OR LOWER(session_code) LIKE ?"
        arg = [f"%{q.lower()}%"] * 2

    with koneksi() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM sessions {where}", arg
        ).fetchone()["n"]
        baris = conn.execute(
            f"SELECT * FROM sessions {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*arg, limit, offset],
        ).fetchall()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "sesi": [_bentuk(conn, b) for b in baris],
        }
