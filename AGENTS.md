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

## Alur hari-H Pet Blessing: jepret dulu, pilah belakangan

Fotografer tidak mengoperasikan laptop. Semua foto masuk kotak masuk dulu, lalu admin memilahnya.

- Tiap laptop receiver punya `BOOTH_ID` di `.env` (`Ganjil` atau `Genap`). Foto yang datang tanpa sesi
  aktif dicatat di sesi semu `_kotak_masuk_<BOOTH_ID>` dan naik ke Drive
  `Raw/!Need Organized/Camera <BOOTH_ID>/<BOOTH_ID>_<jam mendarat>_<nama kamera>.JPG`
  (`app/watcher.py`: `kotak_aktif`, `kotak_masuk`, `_sesi_tujuan`).
- Meja pilah (`/pilah.html`, `web/pilah.js`, `app/pilah.py`) membaca kotak masuk SEMUA kamera dari Drive,
  jadi satu meja memilah foto dari semua laptop. Tombol Cetak sertifikat = `POST /api/pilah/tetapkan`:
  foto pindah ke folder hewan (ID dan tautan Drive tetap), sesi `done` baru dibuat (`pb.pilah = true`),
  sertifikat dibuat dari foto pilihan (bawaan: foto terakhir di deretan).
- Salah pilih hewan: tombol Batalkan = `POST /api/pilah/batalkan/{id}`. Foto kembali ke kotak masuk,
  sertifikat dibuang, catatan di database pendaftaran dikosongkan. Lalu pilah ulang.
- Foto yang bukan foto hewan: Sisihkan = `POST /api/pilah/sisihkan`, pindah ke `Camera <booth>/Disisihkan`.
- Papan pantau (`/pantau.html`) untuk monitor kedua: urutan sesi, foto di Drive, status sertifikat, nama folder.
- Berkas di `tether_dropbox` yang sudah beres diingat di tabel `sumber_selesai`. Foto yang mendarat saat
  server mati diambil begitu server hidup lagi, dan foto lama tidak masuk dua kali.
- Alur lama (halaman Sesi: pilih hewan dulu, baru jepret) tetap jalan. Selama ada sesi aktif di laptop itu,
  foto masuk sesi tersebut, bukan kotak masuk. Jangan campur dua alur di satu laptop.
- Ringkasan semua laptop dari Mac panitia: `~/.venvs/mcfbooth/bin/python alat/pantau_acara.py`.

| Gejala | Lihat dulu | Berkas |
|---|---|---|
| Foto tidak muncul di meja pilah | ada di `tether_dropbox/`? log `Disalin ke arsip: ..._kotak_masuk_...`? `/api/pilah/papan` bagian `lokal` (pending, failed) | `app/watcher.py`, `app/drive_client.py` (`folder_kotak`) |
| Foto kamera lain tidak muncul | laptop itu menyala dan punya internet? isi folder `Camera <booth>` di Drive | paket laptop kedua, `logs/booth.log` di laptop itu |
| Cetak sertifikat ditolak "belum reg ulang" | peserta belum punya nomor urut di server pendaftaran | `app/petblessing.py`, server lokal hari-H |
| Foto masuk folder hewan yang salah | Batalkan di tabel Sudah dipilah, lalu pilah ulang | `app/pilah.py` (`batalkan`) |
| Thumbnail foto kamera lain kosong | Drive belum selesai membuat thumbnail, halaman mencoba lagi tiap 5 detik | `app/pilah.py` (`thumb`), `drive_client.thumb_berkas` |

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
py uji/uji_pilah.py         # kotak masuk, meja pilah, batalkan (BOOTH_ID diatur ujinya sendiri)
```

Kalau `.env` laptop berisi `DRIVE_FOLDER_RAW_ID`, kosongkan dulu untuk uji:
`$env:DRIVE_FOLDER_RAW_ID=""; $env:DRIVE_FOLDER_SERTIFIKAT_ID=""`.
Seksi 5 `uji_drive_palsu` kadang gagal karena waktu; ulangi sebelum menyalahkan perubahan.

## Jangan dilakukan tanpa izin panitia

- Menghapus atau mengganti `sessions.db`, `local_archive/`, `token.json`, `credentials.json`, `.env`.
- Mengubah aturan nama folder atau nomor (lihat bagian di atas): folder di Drive sudah disiapkan dengan aturan itu.
- `git push`, atau mengubah database pendaftaran di luar kolom yang memang ditulis booth (`mcfbooth_session_code`, `certificate_url`, `photo_folder_url`).
- Mematikan server saat ada sesi berjalan. Foto yang masuk saat server mati tetap diproses saat server hidup lagi.
