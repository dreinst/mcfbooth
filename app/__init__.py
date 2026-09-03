"""Aplikasi photobooth MCF.

Komponen di arsitektur §3, semuanya ada di paket ini:

    db.py             Session Log (SQLite)          — §3.3
    server.py         Session Manager (UI operator) — §3.1
    drive_client.py   Klien Google Drive            — §3
    watcher.py        Folder Watcher                — §3.2
    qr.py             QR Generator                  — §3.4
    peristiwa.py      Bus peristiwa SSE             — design.md §8

Konfigurasi (kamera, folder, ID folder Drive) dibaca dari `.env` di akar
repo — lihat `.env.example`. Tidak ada nilai lapangan yang ditulis di kode.
"""
