# Sistem Photobooth MCF

Operator memotret tamu di acara. Foto naik ke Google Drive sendiri, dan begitu operator
menekan Selesai, tamu memindai QR di monitor sebelahnya lalu mengunduh fotonya. Tidak ada
kirim manual, tidak ada tunggu sampai acara bubar.

## Status hari ini — v1.1

🟡 **Semua komponen sudah ada dan bekerja di uji lokal. Belum diuji dengan akun Drive dan
kamera sungguhan.** Server, database, klien Drive, pemantau folder, QR, aliran SSE, dan
tampilan operator + layar tamu di `web/` sudah tersambung satu sama lain. Tiga suite uji otomatis
lulus (`uji/`): sesi & pencarian, alur penuh tanpa Drive, dan alur Drive dengan Drive tiruan
(folder per sesi, upload & retry, QR di layar tamu, balapan saat Drive pulih, penjaga latar,
restart di tengah sesi).

Dua hal yang hanya bisa dibuktikan di lapangan, dan harus dicoba **sebelum** acara pertama:

1. **Google Drive dengan kredensial asli.** Login, pembuatan folder, izin anyone-with-link,
   dan upload belum pernah dijalankan terhadap akun nyata. Caranya di seksi Google Drive.
2. **Kamera dan aplikasi tethering.** Watcher hanya melihat berkas yang jatuh ke
   `tether_dropbox/`; bagaimana Imaging Edge menulis berkas itu (langsung, atau lewat nama
   sementara lalu rename) baru ketahuan dengan kamera terpasang. Keduanya ditangani, tapi
   colok dan coba lima menit lebih dulu.

## Yang harus kamu isi sendiri

Tiga berkas ini sengaja tidak ada di repo dan tidak akan pernah ikut ter-push (`.gitignore`).
Tanpa ketiganya aplikasi tetap jalan untuk dicoba, tapi foto tidak akan sampai ke Drive.

| Berkas | Isi | Cara mendapatkannya |
|---|---|---|
| `.env` | konfigurasi: label kamera, folder, nama folder Drive | `copy .env.example .env` lalu ubah yang perlu — bawaannya sudah bisa dipakai |
| `credentials.json` | OAuth client (jenis **Desktop app**) dari Google Cloud Console | seksi **Persiapan Google Drive → Kredensial** di bawah; taruh di akar folder repo |
| `token.json` | token akun Drive yang menampung foto | dibuat otomatis oleh tombol **Pengaturan → Login Google**; jangan dibuat manual |

Urutannya: pasang, salin `.env`, taruh `credentials.json`, jalankan server, buka Pengaturan,
tekan Login Google. Setelah itu baris Google Drive di pemeriksaan awal hijau.

## Isi folder

| Berkas | Isi | Baca kalau |
|---|---|---|
| `prd-sistem-photobooth.md` | Lingkup, user story, requirement, risiko | mau tahu apa yang dibangun dan apa yang sengaja tidak |
| `architecture.md` | Komponen, skema database, alur data, tech stack | mau tahu bagaimana sistemnya tersusun |
| `design.md` | Prinsip tampilan, tiap layar, keadaan galat, tuntutan ke arsitektur | mau mengubah tampilan atau menilai keputusannya |
| `app/` | Server FastAPI, SQLite, klien Drive, watcher, QR, SSE | mau memakai atau melanjutkan backend-nya |
| `web/` | Tampilan operator (4 halaman) dan layar tamu, disajikan server di `/` | mau mengubah tampilan |
| `uji/` | Tiga skrip verifikasi: sesi & pencarian, alur penuh tanpa Drive, alur Drive dengan tiruan | mau memastikan yang sudah jadi memang jalan |
| `simulasi/` | Kerangka folder kerja + dua foto contoh untuk uji | mau melihat bentuk `tether_dropbox/` dan `local_archive/` |
| `.env.example` | Semua variabel konfigurasi beserta bawaannya | mau mengubah folder, kamera, atau folder Drive |

Urutan baca untuk orang baru: PRD, lalu arsitektur, lalu `design.md`.

---

## Instalasi di Windows

Target produksi sistem ini Windows — Imaging Edge Desktop dan digiCamControl hanya ada di
sana. Yang perlu dipasang cuma Python dan Git; sisanya ikut lewat `pip`.

1. Pasang **Python 3.11 atau lebih baru** dari [python.org](https://www.python.org/downloads/).
   Di layar pertama installer, centang **"Add python.exe to PATH"**.
2. Pasang **Git for Windows** dari [git-scm.com](https://git-scm.com/download/win), atau
   unduh ZIP repo dari GitHub (Code → Download ZIP) lalu ekstrak.
3. Buka PowerShell:

   ```powershell
   git clone https://github.com/dreinst/mcfbooth.git
   cd mcfbooth
   py -m pip install -r requirements.txt
   copy .env.example .env
   ```

4. Jalankan dan verifikasi dari folder itu:

   ```powershell
   py -m uvicorn app.server:app          # aplikasi → http://127.0.0.1:8000/
   py uji/uji_langkah1.py                # sesi & pencarian
   py uji/uji_v1.py                      # alur penuh tanpa Drive
   py uji/uji_drive_palsu.py             # alur Drive dengan Drive tiruan
   ```

`py` adalah peluncur Python bawaan Windows; kalau tidak ada, ganti dengan `python`.
Server mengikat ke `127.0.0.1`, jadi Windows Firewall tidak bertanya apa-apa dan laptop
tidak membuka port ke luar (arsitektur §7, PRD NFR4).

**Pindah laptop.** Kode dan dokumen lewat GitHub. Yang sengaja tidak ikut ter-push dan
harus dibawa manual (USB/drive pribadi) kalau dibutuhkan: `sessions.db` (riwayat sesi),
`credentials.json` + `token.json` (kredensial Google), `.env`, dan — kalau ingin QR dan
thumbnail lama tetap ada tanpa dibuat ulang — `qr_codes/` dan `thumbs/` (`local_archive/`
tentu saja ikut kalau arsipnya mau dibawa).

---

## Menjalankan

Di macOS/Linux (di Windows lihat seksi instalasi di atas):

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app.server:app
```

Buka `http://127.0.0.1:8000/`. Dokumentasi endpoint yang bisa diklik ada di `/docs`.
Port bakunya **8000**; kalau terpakai, tambahkan `--port 8001`.

Saat start pertama server membuat sendiri `sessions.db`, `tether_dropbox/`,
`local_archive/`, `thumbs/`, dan `qr_codes/` di akar folder (atau di path yang diatur `.env`).
Path relatif di `.env` selalu dihitung dari akar repo. Di Windows tulis path tanpa tanda
kutip, atau pakai garis miring biasa (`D:/Foto Acara/tether`).

### Endpoint

| | |
|---|---|
| `POST /api/sessions` | mulai sesi — `{"guest_name": "Budi & Ani"}`; folder Drive + QR dibuat saat itu juga |
| `GET /api/sessions?q=budi` | cari sesi; tanpa `q` jadi daftar Riwayat |
| `GET /api/sessions/active` | sesi yang belum diakhiri, kalau ada |
| `GET /api/sessions/ringkasan` · `GET /api/sessions/nama-serupa?q=` | total sesi, hari ini, yang punya foto tertinggal; nama yang sudah dipakai hari ini |
| `POST /api/sessions/bersiap` · `POST /api/tanpa-sesi/akui` | operator mulai mengetik nama berikutnya (tenggang batal); pita foto tanpa sesi sudah dibaca |
| `GET /api/sessions/{id}` · `/photos` · `/foto-terakhir` | satu sesi, daftar foto, foto terakhir |
| `POST /api/sessions/{id}/finish` | akhiri sesi — QR tampil di layar tamu |
| `POST /api/sessions/{id}/drive` | pasang folder Drive ke sesi yang dimulai saat Drive putus |
| `POST /api/sessions/{id}/retry-failed` | upload ulang foto gagal/menggantung satu sesi |
| `POST /api/sessions/{id}/tampilkan-qr` · `DELETE /api/tampilan-tamu/qr` | paksa layar tamu menampilkan QR sesi lama, dan batalkan |
| `POST /api/photos/{id}/retry` | upload ulang satu foto |
| `GET /api/thumb/{kode}/{nama}` · `GET /api/qr/{kode}` | thumbnail dan gambar QR |
| `GET /api/preflight` | enam pemeriksaan awal + ringkasan kesehatan |
| `GET /api/pengaturan` | konfigurasi yang berlaku |
| `GET /api/drive/status` · `POST`/`GET /api/drive/login` · `POST /api/drive/logout` | keadaan Drive, mulai/pantau login OAuth di browser, ganti akun |
| `GET /api/tampilan-tamu` | keadaan layar tamu: `sambutan` / `memotret` / `qr` |
| `GET /api/peristiwa` · `GET /api/peristiwa-tamu` | Server-Sent Events untuk jendela operator dan jendela tamu |
| `GET /tamu` | halaman layar tamu, tanpa navigasi |

---

## Persiapan Google Drive

### Kredensial (`credentials.json`)

1. Buka [console.cloud.google.com](https://console.cloud.google.com), buat proyek baru —
   nama bebas, misalnya `mcf-photobooth`.
2. **APIs & Services → Library**, cari **Google Drive API**, tekan **Enable**.
3. **APIs & Services → OAuth consent screen**: pilih External, isi nama aplikasi dan
   email. Di **Test users**, tambahkan alamat Gmail akun Drive yang akan menampung foto.
   Mode testing cukup — pemakainya hanya akun itu sendiri.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**, jenis
   **Desktop app**. Unduh JSON-nya, taruh di akar folder proyek dengan nama
   `credentials.json`.

### Login

Buka **Pengaturan → Login Google**. Browser bawaan laptop terbuka; pilih akun, izinkan.
`token.json` ditulis otomatis dan sambungan langsung diuji. Login hanya pernah terjadi
lewat tombol ini — tidak ada permintaan ke Drive yang tiba-tiba membuka browser di tengah
sesi. Kalau token ditolak Google, barisnya merah di pemeriksaan awal dan tombolnya berbunyi
"Login ulang".

**Penting soal umur token.** Selama consent screen berstatus *Testing*, Google mematikan
refresh token setelah **7 hari**. Dua pilihan: (a) di **OAuth consent screen** tekan
**Publish app** — untuk scope `drive.file` tidak perlu verifikasi Google, tokennya lalu
bertahan; atau (b) tetap Testing, tapi login ulang paling lambat malam sebelum acara.
Jangan login seminggu sebelumnya lalu berangkat tanpa mengecek.

### Folder di Drive

Scope yang dipakai `drive.file` saja: aplikasi hanya bisa melihat folder dan berkas yang
ia buat sendiri (arsitektur §7). Konsekuensinya penting: **folder yang kamu buat sendiri
lewat browser tidak terlihat aplikasi**, jadi ID-nya tidak bisa dipakai sebagai induk.

Karena itu aplikasi membuat strukturnya sendiri saat pertama kali terhubung:

```
MCF Photobooth/              ← folder induk, dibuat aplikasi di akar Drive
├── 1. QR/                   ← salinan gambar QR tiap sesi
└── 2. Result/
    └── Budi_Ani_20260902_143052/   ← satu folder per sesi, anyone-with-link viewer
```

Nama-namanya bisa diganti di `.env` (`DRIVE_ROOT_NAME`, `DRIVE_FOLDER_QR`,
`DRIVE_FOLDER_RESULT`). `DRIVE_PARENT_FOLDER_ID` hanya berguna kalau ID itu milik folder
yang pernah dibuat aplikasi ini; kalau ditolak Drive, aplikasi mencatat peringatan di log
dan memakai folder induknya sendiri. Struktur yang berlaku terlihat di Pengaturan.

Kuota: satu JPEG 24 MP sekitar 12 MB (RAW ARW 24 MB), jadi 400 foto JPEG butuh sekitar
5 GB. Angka di Pengaturan memakai asumsi yang sama (±80 foto per GB).

---

## Integrasi kamera

Pemantau folder tidak peduli aplikasi tethering apa yang dipakai — ia hanya memantau
berkas foto yang jatuh ke `tether_dropbox/`. Integrasi kamera berarti satu hal: jepretan
harus mendarat ke folder itu secara otomatis. Label kamera dan aplikasi yang tampil di
Pengaturan diatur lewat `CAMERA_MODEL` dan `TETHERING_APP` di `.env`.

### Jalur utama: Imaging Edge Desktop (aplikasi resmi Sony, Windows)

1. Pasang **Imaging Edge Desktop** dari situs Sony, buka modul **Remote**.
2. Di kamera: **Menu → Setup → USB Connection → PC Remote**.
3. Sambungkan kamera ke laptop lewat USB; kamera muncul di Remote.
4. Di Remote, arahkan folder penyimpanan ke folder yang dipantau aplikasi — path
   persisnya tertulis di Pengaturan → Folder tethering. Subfolder otomatis (per tanggal
   atau per sesi) boleh tetap menyala: pemantau melihat seluruh isi folder itu.
5. Jepret sekali. Kalau berkasnya muncul di grid halaman Sesi dan di layar tamu dalam
   beberapa detik, integrasi beres.

Sony ZV-E10 didukung Imaging Edge Remote. Untuk bodi lama seperti a6000, daftar dukungan
berubah antar versi — verifikasi sendiri, jangan percaya dokumen ini. PRD §12 menaruh
dukungan tethering sebagai risiko nomor satu.

### Kalau jalur utama gagal

- **digiCamControl**: dukungan Sony-nya eksperimental — layak dicoba, jangan diandalkan
  sebelum terbukti.
- **qDslrDashboard** mendukung sebagian bodi Sony.
- Wifi bawaan kamera tidak dipakai: lambat dan gampang putus di venue yang ramai sinyal.

### Setelan kamera yang disarankan

- Format **JPEG** (atau RAW+JPEG kalau RAW-nya mau tetap di kartu SD). ARW tetap diupload
  kalau jatuh ke folder, tapi tanpa thumbnail dan tiga kali lebih berat di wifi venue.
- Auto power-off dimatikan — kamera yang tidur memutus tethering di tengah sesi.
- Baterai dummy / AC adapter untuk acara panjang.

---

## Panduan operator

### Sebelum acara, di rumah

Buka aplikasi, masuk **Pengaturan**, pastikan Drive **Terhubung** dan kuotanya cukup.
Sambungkan kamera, buka aplikasi tethering, pastikan jepretan jatuh ke folder tethering.

Kembali ke halaman **Sesi**: enam baris di panel **Sebelum mulai** harus hijau. Yang
kuning boleh dilewati; yang merah menghalangi Mulai Sesi dan alasannya tertulis di bawah
tombol.

### Sebelum acara, di venue

Pasang monitor kedua, putar ke **Portrait** di pengaturan tampilan Windows. Buka halaman
**Layar tamu**, tekan Buka jendela layar tamu, seret jendelanya ke monitor itu, tekan F11.
Chip "Layar tamu terhubung" di bilah atas menyala hijau begitu jendelanya hidup.

Arahkan monitornya ke tempat tamu berdiri, bukan ke arah operator.

### Per tamu — tiga aksi

1. **Ketik nama tamu**, tekan Mulai Sesi. Folder Drive dan QR dibuat saat itu juga.
2. **Motret seperti biasa.** Foto naik sendiri. Angka di layar naik, monitor tamu
   menampilkan fotonya satu per satu.
3. **Tekan Selesai** setelah yakin semua foto masuk. QR muncul di monitor tamu dan
   bertahan sampai kamu memulai sesi berikutnya.

Sebelum menekan Selesai, lihat tiga angka: **Sudah di Drive**, **Sedang diupload**,
**Gagal**. Kalau dua yang terakhir nol, dialognya hijau dan aman. Kalau tidak, dialognya
menyebut foto mana yang tertinggal dan apa akibatnya.

Angka keempat yang lebih penting: **foto terakhir masuk berapa lama lalu**. Ketiga angka
di atas dihitung dari berkas yang dilihat pemantau folder. Kalau tethering tersendat dan
satu jepretan tidak pernah sampai ke folder, ketiganya tetap cocok satu sama lain dan
ketiganya salah. Kalau kamu baru menjepret lima detik lalu tapi tulisannya "3 menit sejak
foto terakhir", masalahnya di kabel kamera, bukan di upload.

---

## Mode Pet Blessing (sertifikat otomatis)

Untuk acara Pet Blessing 2026 (Paroki St. Vincentius a Paulo, Malang). Satu sesi foto =
satu hewan. Dari foto terbaik, aplikasi menyusun sertifikat A4 lalu mengirim PNG dan PDF
ke Google Drive dan mencatat tautannya di database pendaftaran.

Desain sertifikat tetap dibuat di Figma (file "Pet Blessing 2026", frame sertifikat).
Figma tidak bisa diotomasi tanpa orang di depannya, jadi desainnya diekspor sekali ke
`assets/sertifikat/template.png` (area foto transparan, nama dan jenis hewan serta nama
pemilik dikosongkan). Posisi dan ukuran tulisan ada di `assets/sertifikat/layout.json`,
diambil dari Figma. Huruf Poppins (lisensi OFL) ada di `assets/fonts/`. Kalau desain di
Figma berubah, ekspor ulang template dan sesuaikan `layout.json`.

### Menyalakan

Tambahkan ke `.env`:

```
PHOTOBOOTH_MODE=petblessing
PETBLESSING_API_URL=http://<IP Mac server lokal>:8080/rest
PETBLESSING_BOOTH_TOKEN=<JWT peran booth_worker, minta ke admin>
DRIVE_FOLDER_RAW_ID=1sAZVYbKXhEhs_-QQCWcKIaQPdVAeQeNH
DRIVE_FOLDER_SERTIFIKAT_ID=1qc76GuiSbHvmZMnUuXt4cRJoLLsyGerq
```

Hari H, API menunjuk server lokal di Mac (lihat `lokal/` di repo petblessings); VPS
(`https://petblessing-api.187.53.129.205.sslip.io`) hanya cadangan. Booth memakai nomor
kedatangan dari reg ulang dan menolak peserta yang belum reg ulang.

Dua ID folder di atas adalah folder panitia di Drive "Hari H": foto masuk
`Raw Photo Pet Blessings/028 Nama Pemilik/028A Nama Hewan (Jenis)/`, sertifikat masuk
`Sertifikat Pet Blessing/028 Nama Pemilik/028A_Hewan_Pemilik.pdf` (028 = nomor urut di stiker).
Sebelum hari-H folder sudah disiapkan dengan nomor pendaftaran (nomor di QR), misalnya
`088 Nama Pemilik/A Nama Hewan (Jenis)`; saat sesi foto dimulai booth mengganti namanya ke nomor urut.
Folder ini bisa disiapkan sebelum hari-H dari database: `python -m app.siapkan_folder_pb`
(di Mac dijalankan launchd `com.dpro.pb-folder-drive` tiap 30 menit). Booth memakai folder yang sudah ada. Karena folder itu bukan
buatan aplikasi, booth meminta izin Drive penuh saat ID diisi: login Google di Pengaturan
harus diulang, memakai akun yang punya akses edit ke folder "Hari H". Tanpa dua ID itu,
semuanya masuk folder aplikasi `MCF Photobooth/2. Result/027 Nama Pemilik/027A Nama Hewan/`.

Peran `booth_worker` dibuat oleh migrasi `vps-db/init/18-booth-worker.sql` di repo
petblessings. Token itu hanya bisa membaca nama pemilik, nomor antrean, dan data hewan,
lalu menulis dua kolom: `pets.mcfbooth_session_code` dan `pets.certificate_url`. Nomor HP,
donasi, dan bukti transfer tidak terlihat dari booth.

Bawaan repo ini `PHOTOBOOTH_MODE=mcfbooth`: aplikasi berjalan seperti photobooth biasa.

### Meja pilah: jepret dulu, pilah belakangan

Dipakai kalau fotografer tidak sempat mengoperasikan laptop. Tambahkan ke `.env` tiap laptop receiver:

```
BOOTH_ID=Ganjil
```

(`Genap` untuk laptop kamera kedua.) Sejak itu foto yang datang tanpa sesi aktif naik ke
`Raw Photo Pet Blessings/!Need Organized/Camera Ganjil/` dengan nama `Ganjil_093512_DSC00012.JPG`
(jam mendarat di laptop), tanpa perlu operator.

Admin membuka **Meja pilah** (`http://127.0.0.1:8000/pilah.html`) di laptop utama:

1. Klik foto terakhir milik hewan ini. Semua foto sebelumnya ikut terpilih. Urutan aman untuk
   fotografer: foto stiker nomor urut dulu, lalu foto hewannya.
2. Ketik nomor urut di stiker, misalnya `27a`.
3. Tekan **Cetak sertifikat**. Foto pindah ke `027 Nama Pemilik/027A Nama Hewan (Jenis)/`, sertifikat
   dibuat dari foto terakhir (atau foto yang diberi tanda "Pakai untuk sertifikat") dan naik ke folder
   Sertifikat.

Salah pilih hewan: tekan **Batalkan** di tabel "Sudah dipilah", fotonya kembali ke kotak masuk.
Jepretan uji atau foto yang bukan foto hewan: **Sisihkan foto terpilih**.

Monitor kedua menampilkan **Papan pantau** (`http://127.0.0.1:8000/pantau.html`): urutan sesi, jumlah
foto di Drive, status sertifikat, dan nama folder untuk dicocokkan dengan Drive.

Laptop receiver yang tidak punya Python: salin folder paket portabel (Python ikut di dalamnya), lalu klik
dua kali `Nyalakan Photobooth.cmd`. Tidak ada yang dipasang di laptop itu.

### Per hewan

1. **Scan QR pendaftaran** di HP pemilik: lewat kamera laptop (tombol Scan dengan kamera
   laptop, hanya tampil di browser yang punya pemindai QR bawaan), scanner USB, atau
   ketik kode 8 huruf dari pesan WhatsApp lalu Enter.
2. **Tap hewan** yang akan difoto. Hewan yang sudah punya sertifikat diberi keterangan.
3. **Motret seperti biasa.**
4. **Tap foto terbaik** (bingkai biru "Dipilih"), lalu **Buat sertifikat**. Pratinjau
   muncul beberapa detik kemudian. Kalau kurang pas, pilih foto lain dan buat ulang.
5. **Tekan Selesai.** Setelah itu, daftar hewan milik pemilik yang sama tampil lagi, jadi
   hewan berikutnya tidak perlu scan ulang.

Sertifikat tersimpan di `local_archive/_sertifikat/` dengan nama
`<nomor antrean>_<hewan>_<pemilik>.png/.pdf`, lalu diupload ke Drive
`MCF Photobooth/3. Sertifikat/`. Tiap berkas dibuka untuk siapa saja yang punya tautannya.
Tautan PDF dicatat di data pendaftaran.

Kalau wifi putus: sertifikat tetap dibuat di laptop, dan upload serta pencatatannya
disusulkan penjaga latar begitu tersambung. Pencarian QR memakai salinan daftar pemilik
terakhir yang tersimpan di laptop.

Foto dipotong otomatis memenuhi bingkai (bagian tengah dipertahankan). Posisikan hewan di
tengah frame kamera. Bingkai sertifikat tegak (1205 × 1795), jadi foto portrait paling pas.

---

## Kalau ada masalah

**Wifi venue mati.** Terus motret. Foto tetap tersimpan di kartu SD dan di `local_archive/`.
Tiap foto dicoba empat kali (jeda 1, 5, 15 detik), lalu berstatus Gagal; penjaga latar
mencobanya lagi tiap 30 detik begitu Drive terjangkau, jadi biasanya semuanya menyusul
sendiri. Kalau ingin lebih cepat, tekan Coba lagi semuanya. Jangan akhiri sesi selama
antrean masih besar — QR menunjuk ke folder yang belum lengkap.

**Drive putus saat Mulai Sesi.** Tombol Mulai Sesi tetap hidup dengan peringatan kuning.
Sesi dibuat dan fotonya diarsipkan; pita "Sesi ini belum punya folder Drive" muncul. Penjaga
latar memasang foldernya dan mengupload semua foto yang menunggu begitu Drive terjangkau
lagi (paling lama 30 detik), atau tekan tombol di pita itu. Yang menghalangi Mulai Sesi hanya
keadaan yang tidak pulih sendiri: belum login, kredensial tidak ada, token ditolak.

**Ada foto berstatus Gagal.** Tekan Coba lagi di foto itu, atau Coba lagi semuanya di pita
merah. Berkasnya masih utuh di laptop. Kalau tetap gagal, biasanya kuota Drive habis atau
token kedaluwarsa — keduanya kelihatan di sidebar.

**Terlanjur menekan Selesai padahal masih ada yang tertinggal.** Foto yang masih antre
tetap menyusul ke folder yang benar. Jepretan yang mendarat dalam 45 detik setelah Selesai
juga masih dihitung milik sesi itu (`TENGGANG_SETELAH_SELESAI`) — tenggang itu batal begitu
kamu mulai mengetik nama tamu berikutnya, supaya jepretan uji tidak masuk ke folder tamu
sebelumnya. Yang berstatus Gagal diulang penjaga latar; bisa juga cari sesinya di
**Riwayat** dan tekan Upload sisanya.

**Foto masuk saat tidak ada sesi.** Berkas diamankan ke `local_archive/_tanpa_sesi/` dan
pita kuning muncul di halaman Sesi. Tidak diupload ke mana pun — pindahkan manual ke
folder Drive tamu yang benar, lalu tekan "Mengerti, sembunyikan". Jepretan uji sebelum
tamu pertama juga berakhir di sini; itu normal.

**QR fisik hilang atau tamu belum sempat memindai.** Buka **Riwayat**, ketik namanya,
tekan Tampilkan QR — monitor tamu langsung menampilkannya (hanya saat tidak ada sesi yang
sedang berjalan; kalau ada, pakai Salin tautan lalu kirim lewat pesan). Gambar QR dibuat
ulang dari tautan yang tersimpan kalau berkasnya hilang, misalnya setelah pindah laptop.

**Aplikasi tertutup di tengah sesi.** Buka lagi. Kalau sesinya masih hangat, halaman Sesi
langsung melanjutkannya; kalau sudah lama dingin, pita di atas menawarkan lanjutkan atau
akhiri sekarang. Foto yang masih pending diupload ulang otomatis saat server naik.

**Monitor kedua tercabut atau jendelanya tertutup.** Sesi tetap jalan. Di halaman Layar
tamu, tekan "Tampilkan di laptop ini" lalu F11. Keluar dari layar itu dengan menekan-tahan
pojok kanan bawah dua detik, atau tekan Esc (di mode F11, Esc pertama keluar dari layar
penuh, Esc kedua kembali ke panel).

**Layar operator berhenti berubah.** Chip merah "Terputus dari server" muncul, angka di
layar ditandai basi, dan tombol Selesai dimatikan dengan alasannya. Sesinya kemungkinan
besar masih berjalan di latar. Tekan Coba sambung ulang, atau nyalakan ulang server.

---

## Yang sengaja tidak ada

Tidak ada tombol hapus arsip lokal di aplikasi. `local_archive/` adalah lapis backup kedua
setelah kartu SD, dan satu klik yang salah menghapusnya lebih mahal daripada repot
membersihkannya lewat Explorer.

Tidak ada login. Aplikasi hanya diakses dari laptop operator dan tidak membuka port ke
internet publik (PRD NFR4).

Tidak ada pencetakan foto, pembayaran, multi-kamera, dan dukungan Mac di v1 — tercatat di
PRD §5 sebagai kandidat versi berikutnya. (Kode ini berjalan di macOS untuk pengembangan,
tapi aplikasi tethering Sony tidak.)

Aplikasi tidak pernah memutuskan sendiri kapan sesi selesai.

## Yang masih terbuka

Uji dengan akun Drive dan kamera sungguhan — lihat Status di atas.

Tema kembali terang di v1.2 (lihat `design.md` §11) — kanvas diturunkan ke `#f4f5f7`,
bukan putih murni, supaya layar besar di ballroom remang tidak menyilaukan. Tangkapan
layar Chrome headless untuk palet ini belum diulang di venue nyata; itu risiko yang
sama seperti versi gelap sebelumnya, hanya berpindah arah.

Foto di `local_archive/_tanpa_sesi/` belum bisa dipindahkan ke sesi lewat aplikasi.

## Riwayat perubahan

**v1.1** — Perbaikan: SSE tidak pernah mengirim event (pelanggan dicabut sebelum stream
mulai), bus peristiwa tidak thread-safe, sesi tanpa Drive tidak bisa diperbaiki, foto
setelah Selesai dibuang, watcher melewatkan rename dan tidak memulihkan pending setelah
restart, foto lama di folder tether ikut sesi baru, retry bisa menduplikasi foto yang
sudah terupload, login OAuth membuka browser di tengah request, path traversal di
`/api/thumb`, frontend menganggap 409 sebagai sukses, favicon hilang. Dari review lanjutan:
pemasangan folder Drive dikunci per sesi (sebelumnya upload paralel bisa membuat banyak
folder untuk satu sesi), foto yang menunggu ikut terupload begitu folder terpasang,
penjaga latar mengulang upload saat Drive pulih, Mulai Sesi tidak lagi diblokir wifi
putus, refresh token dan panggilan Drive punya batas waktu, login OAuth punya batas waktu,
QR dibuat ulang kalau PNG-nya hilang, POST lintas situs ditolak. Baru: tampilan `web/`
(gelap, font lokal), Riwayat dan Pengaturan nyata, pemeriksaan awal nyata, layar tamu
digerakkan server, tiga suite uji termasuk Drive tiruan, `.env.example`.

**v1.2** — Kurasi ulang tampilan dari paket Stitch baru (`design.md` §11): kembali ke
palet terang yang sudah didokumentasikan §2.4 (kontras dihitung ulang untuk latar chip
status), aksen oranye dibatasi ke dua momen bermakna tunggal (mulai sesi, sesi selesai),
shadow dekoratif di luar dialog/toast dibuang. Baru: filter Semua/Lengkap/Perlu tindakan
di Riwayat (hanya berlaku pada baris yang sudah dimuat), tombol Buka folder Drive per
sesi, tombol Uji ulang koneksi di Pengaturan, penomoran urutan foto di grid operator.
Ditolak dari paket sumber dan dicatat alasannya di `design.md` §11.2: paket cetak dan
printer, kamera Canon/RAW `.CR3`, nomor sesi generik, label paket/tier tamu, klaim ZIP/4K/
kedaluwarsa di layar tamu, saklar manual keadaan layar tamu, dan label berbahasa Inggris.

**v1.3** (25 Sep 2026): mode Pet Blessing. Scan QR pendaftaran, satu sesi per hewan,
pilih foto terbaik, sertifikat PNG + PDF A4 dari template Figma, upload ke Drive
"3. Sertifikat", tautan dicatat di database pendaftaran, penjaga latar menyusulkan yang
tertunda. Suite uji baru `uji/uji_sertifikat.py`.

**v1.0.0** — Drive, watcher, QR, SSE, integrasi awal frontend.
