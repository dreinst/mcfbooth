"""Aplikasi photobooth MCF.

Empat komponen di arsitektur §3, semuanya sudah ada:

    db.py             Session Log (SQLite)          — §3.3   ✅
    server.py         Session Manager (UI operator) — §3.1   ✅
    drive_client.py   Klien Google Drive            — §3     ✅
    watcher.py        Folder Watcher                — §3.2   ✅
    qr.py             QR Generator                  — §3.4   ✅
    peristiwa.py      SSE Event Bus                 — §8     ✅

Kamera: Sony ZV-E10 via Imaging Edge Desktop.
Folder Drive: 1mrTvuwAWrq0mv6raIjXOOyjAR5VcrzKm
"""
