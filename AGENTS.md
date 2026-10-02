# Panduan untuk asisten AI (debugging photobooth)

Baca ini dulu sebelum mengubah apa pun. Isinya: bagian sistem, tempat log, dan
gejala yang biasa muncul beserta berkas yang perlu dibuka. Bahasa kerja tim:
Indonesia.

## Sistem dalam satu paragraf

Booth adalah server FastAPI lokal (`app/`) + tampilan web (`web/`) di laptop
Windows. Kamera menulis JPG ke `tether_dropbox/`, watcher menyalinnya ke
`local_archive/<kode sesi>/`, lalu mengupload ke Google Drive. Operator membuka
`http://127.0.0.1:8000/`, layar tamu membuka `/tamu` dan menampilkan QR folder
Drive. Mode Pet Blessing (`PHOTOBOOTH_MODE=petblessing` di `.env`) menambah:
cari peserta dari database pendaftaran, satu sesi per hewan, sertifikat A4
otomatis, dan folder Drive panitia.

## Menjalankan dan melihat log (Windows, PowerShell, dari folder repo)

```powershell
py -m uvicorn app.server:app          # server, buka http://127.0.0.1:8000/
Get-Content logs\booth.log -Tail 100  # log terbaru (juga tampil di jendela server)
Get-Content logs\booth.log -Wait      # ikuti log langsung
```

Pemeriksaan cepat tanpa membaca kode:
- `http://127.0.0.1:8000/api/preflight` : pemeriksaan awal (Drive, folder, internet, disk, layar tamu).
- `http://127.0.0.1:8000/api/drive/status` : status login Google.
- `http://127.0.0.1:8000/api/pengaturan` : nilai `.env` yang sedang berlaku.

## Peta gejala ke berkas

| Gejala | Lihat dulu | Berkas |
|---|---|---|
| Foto dari kamera tidak muncul di layar | apakah JPG benar-benar masuk `tether_dropbox/`; log `watcher` | `app/watcher.py`, `.env` (`TETHER_DROPBOX`, `STABILITAS_DETIK`) |
| Foto muncul tapi tidak sampai Drive / status gagal | log `drive_client`, `/api/drive/status` | `app/drive_client.py` (upload, retry), `app/watcher.py` (`_antre_sisa`, penjaga latar) |
| "Token ditolak" / Drive merah | token kedaluwarsa atau scope salah | login ulang di Pengaturan. `token.json`, `credentials.json` jangan diedit tangan |
| QR di layar tamu tidak muncul atau tidak update | jendela `/tamu` terbuka? log `peristiwa` | `app/peristiwa.py` (SSE), `web/app.js` (bagian layar tamu), `app/qr.py` |
| Cari nama / scan QR peserta Pet Blessing gagal | `PETBLESSING_API_URL` dan `PETBLESSING_BOOTH_TOKEN` di `.env`; internet ke server lokal hari-H | `app/petblessing.py` (`cari_nama`, `cari_pemilik`, `_bentuk`), `app/server.py` (`/api/pb/*`) |
| "Belum reg ulang" padahal sudah | data checkins belum tersinkron ke server yang ditunjuk `PETBLESSING_API_URL` | cek server lokal hari-H (repo petblessings, `lokal/server.js`) |
| Sertifikat salah tulisan / posisi | template dan layout | `app/sertifikat.py` (render), `assets/sertifikat/layout.json`, `assets/sertifikat/template.png` |
| Sertifikat tidak terupload / tidak tercatat | log `sertifikat`; status di tabel `sertifikat` | `app/sertifikat.py` (`_upload`, `_catat`, `susulkan`) |
| Folder Drive dobel / nama folder salah | aturan nama di satu tempat | `app/petblessing.py` (`folder_pemilik`, `folder_hewan`), `app/drive_client.py` (`buat_folder_sesi`, `_folder_pemilik`, `_ganti_nama`) |
| Tampilan / tombol tidak sesuai | konsol browser (F12) | `web/*.html`, `web/app.js`, `web/ui.css`, tema Pet Blessing `web/pb/tema.css` |
| Data sesi / riwayat aneh | SQLite lokal | `app/db.py`, berkas `sessions.db` |

## Aturan nama (Pet Blessing)

- Nomor pendaftaran = nomor di QR pendaftaran. Menentukan pos reg ulang (ganjil Pos A, genap Pos B).
- Nomor urut = nomor di stiker, dibagikan saat reg ulang. Dipakai booth, label sesi `028A`, nama sertifikat.
- Folder Drive disiapkan sebelum hari-H sebagai `088 Pemilik/A Hewan (Jenis)` (`app/siapkan_folder_pb.py`),
  lalu booth mengganti namanya ke `028 Pemilik/028A Hewan (Jenis)` saat sesi dimulai.
- Sertifikat ada di folder Sertifikat panitia dan salinannya di folder foto hewan.
  Link folder foto dicatat ke `pets.photo_folder_url`, sertifikat ke `pets.certificate_url`,
  dan keduanya tampil di `https://petblessings.vercel.app/hasil.html` (QR poster).

## Menguji perubahan

```powershell
py uji/uji_langkah1.py      # sesi & pencarian
py uji/uji_v1.py            # alur penuh tanpa Drive
py uji/uji_sertifikat.py    # mode Pet Blessing + sertifikat (PostgREST tiruan)
py uji/uji_ganti_nama.py    # ganti nama folder ke nomor urut
$env:MCF_DRIVE_PALSU=1; py uji/uji_drive_palsu.py   # Drive tiruan
```

Kalau `.env` laptop berisi `DRIVE_FOLDER_RAW_ID`, kosongkan dulu untuk uji:
`$env:DRIVE_FOLDER_RAW_ID=""; $env:DRIVE_FOLDER_SERTIFIKAT_ID=""`.
Seksi 5 `uji_drive_palsu` kadang gagal karena waktu; ulangi sebelum menyalahkan perubahan.

## Jangan dilakukan tanpa izin panitia

- Menghapus atau mengganti `sessions.db`, `local_archive/`, `token.json`, `credentials.json`, `.env`.
- Mengubah aturan nama folder atau nomor (lihat bagian di atas): folder di Drive sudah disiapkan dengan aturan itu.
- `git push`, atau mengubah database pendaftaran di luar kolom yang memang ditulis booth (`mcfbooth_session_code`, `certificate_url`, `photo_folder_url`).
- Mematikan server saat ada sesi berjalan. Foto yang masuk saat server mati tetap diproses saat server hidup lagi.
