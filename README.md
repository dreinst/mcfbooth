# Sistem Photobooth MCF

Operator memotret tamu di acara. Foto naik ke Google Drive sendiri, dan begitu operator
menekan Selesai, tamu memindai QR di monitor sebelahnya lalu mengunduh fotonya. Tidak ada
kirim manual, tidak ada tunggu sampai acara bubar.

## Status hari ini

🟠 **Belum bisa dipakai di acara.** Langkah 1 dari lima sudah jadi: server dan database
di `app/` menyimpan sesi dan bertahan setelah restart. Yang belum ada masih tiga —
koneksi ke Google Drive, pemantau folder tethering, dan tampilan yang tersambung ke
server. Foto belum tersentuh sama sekali oleh kode mana pun.

Prototipe di `prototipe/` masih berdiri sendiri dengan data karangan; ia belum berbicara
ke `app/`. Menyambungkannya adalah langkah 4.

Panduan operator di bagian bawah menjelaskan sistem yang **dirancang**, bukan yang sudah
bisa dipakai. Jangan jadwalkan acara berdasarkan dokumen ini.

## Isi folder

| Berkas | Isi | Baca kalau |
|---|---|---|
| `prd-sistem-photobooth.md` | Lingkup, user story, requirement, risiko | mau tahu apa yang dibangun dan apa yang sengaja tidak |
| `arsitektur-sistem-photobooth.md` | Komponen, skema database, alur data, tech stack | mau tahu bagaimana sistemnya tersusun |
| `design.md` | Token visual, tiap layar, keadaan galat, tuntutan ke arsitektur | mau membangun tampilannya atau menilai keputusannya |
| `app/` | Server dan database — langkah 1, satu-satunya kode yang berjalan | mau memakai atau melanjutkan backend-nya |
| `prototipe/` | Lima halaman HTML yang bisa diklik, tanpa backend | mau melihat hasilnya sekarang |
| `simulasi/` | Kerangka folder kerja, statis | mau melihat bentuk `tether_dropbox/` dan `local_archive/` |
| `uji/` | Skrip verifikasi tiap langkah | mau memastikan yang sudah jadi memang jalan |

Desain lama hasil Stitch (`design md.zip`, 200 KB) tidak ada di repo — ia cuma dibutuhkan
kalau kamu mau menelusuri rujukan `photobooth_*/code.html` di `design.md`.

Urutan baca untuk orang baru: PRD, lalu arsitektur, lalu `design.md`. Prototipenya dibuka
sambil membaca `design.md`.

---

## Instalasi di Windows

Target produksi sistem ini memang Windows — digiCamControl dan Imaging Edge hanya ada
di sana, dan panduan operator di bawah memakai pengaturan tampilan Windows. Yang perlu
dipasang cuma Python dan Git; sisanya ikut lewat `pip`.

1. Pasang **Python 3.11 atau lebih baru** dari [python.org](https://www.python.org/downloads/).
   Di layar pertama installer, centang **"Add python.exe to PATH"** — tanpa ini perintah
   `py`/`python` tidak dikenal di terminal.
2. Pasang **Git for Windows** dari [git-scm.com](https://git-scm.com/download/win)
   (pengaturan bawaan semua oke). Kalau tidak mau memasang Git, unduh ZIP repo dari
   GitHub (Code → Download ZIP) lalu ekstrak — langkah 3 tinggal `cd` ke folder hasilnya.
3. Buka PowerShell:

   ```powershell
   git clone https://github.com/dreinst/mcfbooth.git
   cd mcfbooth
   py -m pip install -r requirements.txt
   ```

4. Jalankan dan verifikasi dari folder itu:

   ```powershell
   py -m uvicorn app.server:app --reload    # server → http://127.0.0.1:8000/docs
   py uji/uji_langkah1.py                   # 32 uji, semuanya harus lulus
   ```

   Untuk prototipe, di jendela PowerShell kedua:

   ```powershell
   cd prototipe
   py -m http.server 8080                   # → http://localhost:8080/
   ```

`py` adalah peluncur Python bawaan Windows; kalau tidak ada, ganti semua `py` dengan
`python`. Server mengikat ke `127.0.0.1`, jadi Windows Firewall tidak bertanya apa-apa.
Yang memunculkan dialog firewall hanya `http.server` prototipe kalau mau dibuka dari HP —
izinkan untuk jaringan Private saja.

**Pindah dari laptop lama.** Kode dan dokumen lewat GitHub. Dua hal yang sengaja tidak
ikut ter-push dan harus dibawa manual (USB/drive pribadi) kalau memang dibutuhkan:
`sessions.db` (riwayat sesi — biarkan saja kalau mau mulai bersih) dan, mulai langkah 2,
`credentials.json` + `token.json` (kredensial Google — tidak boleh lewat GitHub, lihat
seksi Google Drive di bawah).

---

## Menjalankan server

Di macOS/Linux (di Windows lihat seksi instalasi di atas):

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.server:app --reload
```

Dokumentasi endpoint yang bisa diklik ada di `http://127.0.0.1:8000/docs`. Database
`sessions.db` dibuat sendiri di akar folder saat start pertama.

Port bakunya **8000** — semua contoh di dokumen ini memakainya. Kalau di mesinmu port
8000 sedang dipakai proses lain, tambahkan `--port 8001` (atau port bebas lain) dan baca
semua contoh dengan port itu; tidak ada yang perlu diubah di kode.

Empat endpoint langkah 1, plus satu yang dibutuhkan alur "sesi tertinggal" (`design.md` §4):

| | |
|---|---|
| `POST /api/sessions` | mulai sesi — `{"guest_name": "Budi & Ani"}` |
| `GET /api/sessions?q=budi` | cari sesi; tanpa `q` jadi daftar Riwayat |
| `GET /api/sessions/active` | sesi yang belum diakhiri, kalau ada |
| `GET /api/sessions/{id}` | satu sesi |
| `POST /api/sessions/{id}/finish` | akhiri sesi |

Servernya mengikat ke `127.0.0.1`, bukan `0.0.0.0` — laptop tidak membuka port ke luar
(arsitektur §7, PRD NFR4).

Dua hal yang sengaja belum ada di sini: `drive_folder_link` dan `qr_path` selalu null
sampai langkah 2, dan tabel `photo_uploads` sudah berdiri tapi belum ada yang mengisinya
sampai langkah 3. Keduanya batas langkah, bukan kerusakan.

Verifikasinya:

```bash
python3 uji/uji_langkah1.py
```

Skrip itu menjalankan uvicorn sungguhan di subprocess, mematikannya, lalu menjalankannya
lagi — karena syarat selesai langkah 1 menyebut restart, dan restart hanya berarti sesuatu
kalau prosesnya memang mati.

---

## Menjalankan prototipe

Prototipe belum berbicara ke server di atas; ia masih berdiri sendiri dengan data karangan.
Butuh Python 3 (sudah ada di macOS dan Linux; di Windows pasang dari python.org).

```bash
cd "prototipe"
python3 -m http.server 8080
```

Buka `http://localhost:8080/`.

Harus lewat HTTP, bukan klik dua kali berkasnya. Sinkronisasi antara jendela operator dan
jendela tamu memakai BroadcastChannel, dan itu tidak bekerja di `file://`.

Untuk mencobanya di HP yang satu wifi, ganti `localhost` dengan IP laptop
(`ipconfig getifaddr en0` di macOS, `ipconfig` di Windows). Server-nya terbuka ke seluruh
jaringan selama hidup — matikan dengan Ctrl-C kalau kamu di wifi umum.

### Yang bisa dicoba

Ketik nama di halaman Sesi, tekan Mulai Sesi. Foto berdatangan sendiri tiap 1,7 detik,
dua di antaranya sengaja gagal supaya jalur kegagalannya kelihatan. Tekan Selesai;
dialognya berubah bentuk tergantung masih ada antrean atau tidak.

Buka jendela kedua lewat tombol **Buka jendela layar tamu**, seret ke monitor lain.
Tekan Selesai di jendela operator — QR muncul di jendela tamu. Itu alur dua layar yang
sebenarnya, cuma sumber datanya masih karangan.

Tombol **Simulasi gagal** dan **Reset** di pojok kanan bawah adalah perkakas prototipe,
bukan bagian produk.

### Yang belum nyata di prototipe

Foto "masuk" dari timer, bukan dari folder tethering. QR-nya gambar contoh dan tidak bisa
dipindai. Font Hanken Grotesk dan JetBrains Mono belum ada berkasnya, jadi tampilannya
jatuh ke font sistem. Tidak ada database — tutup tab, semuanya hilang.

---

## Tahapan sampai bisa dipakai

Satu dari empat komponen di `arsitektur-sistem-photobooth.md` §3 sudah ditulis. Urutan di
bawah menaruh yang paling berisiko lebih dulu, supaya kalau ada yang tidak bisa dikerjakan,
ketahuannya sekarang bukan seminggu sebelum acara.

**1. Kerangka server dan database.** ✅ **Selesai.** FastAPI plus SQLite dengan dua tabel
dari arsitektur §3.3, di `app/db.py` dan `app/server.py`. Syarat selesainya — sesi dibuat
lewat API dan masih ada setelah server di-restart — diverifikasi `uji/uji_langkah1.py`.

Tiga keputusan yang diambil saat menulisnya, karena dokumennya tidak menyebutkan:
hanya boleh ada **satu sesi `active`** pada satu waktu, dan sesi kedua ditolak dengan
409 alih-alih menutup yang lama sendiri — menutup sesi tetap keputusan manusia.
Tabrakan `session_code` di detik yang sama diberi akhiran `_2`, bukan ditolak, karena
operator yang menekan Mulai Sesi di tengah acara tidak boleh dapat galat. Dan hitungan
foto diturunkan dari `photo_uploads`, bukan dibaca dari kolom `photo_count`, supaya
angka di layar tidak bisa menyimpang dari tabel sumbernya.

**2. Klien Google Drive.** OAuth dengan scope `drive.file` saja, buat folder per sesi, set
izin *anyone with link = viewer*, upload satu berkas. Ini bagian yang paling sering
tersandung urusan kredensial, jadi didahulukan. Selesai kalau satu foto uji muncul di
Drive dan tautannya bisa dibuka dari HP yang tidak login.

**3. Pemantau folder.** `watchdog` memantau `tether_dropbox/`, menunggu ukuran berkas
stabil, menyalin ke `local_archive/<session_code>/`, mengupload, mencatat hasilnya. Retry
1, 5, lalu 15 detik; setelah itu ditandai `failed`. Selesai kalau mencabut wifi di tengah
upload tidak menghilangkan satu foto pun.

**4. Tampilan.** Pasang `prototipe/` di atas endpoint yang sudah nyata. Endpoint tambahan
yang dibutuhkan tampilan ada di `design.md` §8 — pemeriksaan awal, daftar foto, thumbnail,
retry per foto, halaman layar tamu, dan aliran SSE.

**5. Uji lapangan.** Satu acara kecil dulu dengan tiga lapis backup aktif, bukan langsung
acara besar.

Persiapan untuk langkah 2 dan 3 tidak butuh kode dan bisa dicicil sekarang — rinciannya
di dua seksi berikut.

---

## Persiapan Google Drive — dipakai mulai langkah 2

Langkah 2 belum ditulis; seksi ini menyiapkan bahannya supaya begitu kodenya ada,
tinggal jalan. Semuanya gratis untuk skala photobooth.

### Kredensial (`credentials.json`)

1. Buka [console.cloud.google.com](https://console.cloud.google.com), buat proyek baru —
   nama bebas, misalnya `mcf-photobooth`.
2. **APIs & Services → Library**, cari **Google Drive API**, tekan **Enable**.
3. **APIs & Services → OAuth consent screen**: pilih External, isi nama aplikasi dan
   email. Di bagian **Test users**, tambahkan alamat Gmail akun Drive yang akan
   menampung foto. Aplikasi tidak perlu diverifikasi Google — mode testing cukup,
   karena pemakainya hanya akun itu sendiri.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**, jenis
   **Desktop app**. Unduh JSON-nya, taruh di akar folder proyek dengan nama
   `credentials.json`.

`credentials.json` dan `token.json` (dibuat otomatis saat login pertama) sudah masuk
`.gitignore` — keduanya tidak akan pernah ikut ter-push, dan memang tidak boleh. Pindah
laptop berarti menyalinnya lewat USB/drive pribadi, bukan lewat GitHub.

Scope yang dipakai `drive.file` saja: aplikasi hanya bisa melihat folder dan berkas
yang ia buat sendiri, bukan seluruh isi Drive (arsitektur §7).

### ID folder Drive

Folder per sesi dibuat otomatis oleh aplikasi saat operator menekan Mulai Sesi
(arsitektur §3.2) — tidak ada yang perlu dibuat satu-satu. Yang bisa kamu tentukan
adalah **folder induknya**, supaya semua sesi terkumpul di satu tempat, misalnya
`MCF Photobooth/`. Buat foldernya di Drive, buka di browser, dan ID-nya ada di URL:

```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz12345
                                       └──────────── ini ID-nya ───────┘
```

Simpan ID itu — di langkah 2 ia masuk konfigurasi sebagai folder induk. Kalau kosong,
folder sesi dibuat di akar Drive; fungsinya sama, cuma kurang rapi.

---

## Integrasi kamera — Sony a6000, dipakai mulai langkah 3

Pemantau folder (langkah 3) tidak peduli aplikasi tethering apa yang dipakai — ia hanya
memantau berkas yang jatuh ke `tether_dropbox/`. Integrasi kamera berarti satu hal:
jepretan a6000 harus mendarat ke folder itu secara otomatis. Struktur foldernya bisa
dilihat di `simulasi/`.

### Jalur utama: Imaging Edge Desktop (aplikasi resmi Sony, Windows)

1. Pasang **Imaging Edge Desktop** dari situs Sony, buka modul **Remote**.
2. Di kamera: **Menu → Setup → USB Connection → PC Remote**.
3. Sambungkan a6000 ke laptop lewat USB; kamera muncul di Remote.
4. Di Remote, arahkan folder penyimpanan ke folder yang akan dipantau aplikasi
   (`tether_dropbox/`).
5. Jepret sekali. Berkas muncul di folder itu → integrasi beres; sisanya urusan
   pemantau folder di langkah 3.

**Verifikasi sendiri, jangan percaya dokumen ini**: a6000 bodi keluaran 2014, dan
daftar kamera yang didukung Imaging Edge Remote berubah antar versi. Colok dan coba —
lima menit — sebelum ada kode yang dibangun di atasnya. PRD §12 memang menaruh dukungan
tethering sebagai risiko nomor satu.

### Kalau jalur utama gagal

- **digiCamControl** (yang disebut arsitektur §3.2): dukungan Sony-nya eksperimental —
  layak dicoba, jangan diandalkan sebelum terbukti.
- **qDslrDashboard** mendukung sebagian bodi Sony.
- Wifi bawaan a6000 tidak dipakai: lambat dan gampang putus di venue yang ramai sinyal.

### Setelan kamera yang disarankan

- Format **JPEG** (atau RAW+JPEG kalau RAW-nya mau tetap di kartu SD). Yang diupload
  JPEG — RAW 24 MP a6000 sekitar 24 MB per berkas dan membuat antrean upload panjang
  di wifi venue.
- Auto power-off dimatikan atau diatur selonggar mungkin — kamera yang tidur memutus
  tethering di tengah sesi.
- Baterai dummy / AC adapter untuk acara panjang; tethering menguras baterai jauh lebih
  cepat dari pemakaian biasa.

---

## Panduan operator

Ditulis untuk sistem yang sudah jadi. Belum bisa dijalankan hari ini.

### Sebelum acara, di rumah

Cek kuota Google Drive. Satu foto DSLR sekitar 25 MB, jadi 400 foto butuh 10 GB. Kosongkan
atau siapkan akun lain kalau mepet.

Sambungkan kamera ke laptop, buka digiCamControl, pastikan hasil jepretan jatuh ke folder
`tether_dropbox`. Jepret sekali dan lihat berkasnya muncul.

Buka aplikasi, pastikan enam baris di panel **Sebelum mulai** hijau semua. Yang kuning
boleh dilewati; yang merah menghalangi Mulai Sesi dan alasannya tertulis di bawah tombol.

### Sebelum acara, di venue

Pasang monitor kedua, putar ke **Portrait** di pengaturan tampilan Windows. Buka halaman
**Layar tamu**, tekan Buka jendela layar tamu, seret jendelanya ke monitor itu, tekan F11.
Monitor itu sekarang menampilkan layar sambutan dan tidak perlu disentuh lagi sepanjang
acara.

Arahkan monitornya ke tempat tamu berdiri, bukan ke arah operator.

### Per tamu — tiga aksi

1. **Ketik nama tamu**, tekan Mulai Sesi. Folder Drive dan tautannya dibuat saat itu juga,
   bukan nanti.
2. **Motret seperti biasa.** Foto naik sendiri. Angka di layar naik, dan monitor tamu
   menampilkan fotonya satu per satu.
3. **Tekan Selesai** setelah yakin semua foto masuk. QR muncul di monitor tamu dan
   bertahan sampai kamu memulai sesi berikutnya.

Sebelum menekan Selesai, lihat tiga angka: **Sudah di Drive**, **Sedang diupload**,
**Gagal**. Kalau dua yang terakhir nol, aman. Kalau tidak, dialognya akan memberi tahu
foto mana yang tertinggal dan apa akibatnya.

Angka keempat yang lebih penting dari ketiganya: **foto terakhir masuk berapa lama lalu**.
Ketiga angka di atas dihitung dari berkas yang dilihat pemantau folder. Kalau tethering
tersendat dan satu jepretan tidak pernah sampai ke folder, ketiganya tetap cocok satu sama
lain dan ketiganya salah. Kalau kamu baru menjepret lima detik lalu tapi tulisannya "foto
terakhir masuk 3 menit lalu", masalahnya di kabel kamera, bukan di upload.

---

## Kalau ada masalah

**Wifi venue mati.** Terus motret. Foto tetap tersimpan di kartu SD dan di disk laptop,
dan uploadnya menyusul sendiri begitu koneksi kembali. Jangan akhiri sesi selama antrean
masih besar — QR yang ditampilkan sekarang menunjuk ke folder yang belum lengkap.

**Ada foto berstatus Gagal.** Tekan Coba lagi di foto itu, atau Coba lagi semuanya di pita
merah. Berkasnya masih utuh di laptop; yang gagal cuma pengirimannya. Kalau tetap gagal,
biasanya kuota Drive habis atau token kedaluwarsa — keduanya kelihatan di sidebar.

**Terlanjur menekan Selesai padahal masih ada yang tertinggal.** Foto yang masih antre
tetap menyusul ke folder yang benar dengan sendirinya. Yang berstatus Gagal tidak — cari
sesinya di **Riwayat** dan tekan Upload sisanya. Masalahnya bukan foto hilang, melainkan
waktu: tamu yang sudah memindai dan mengunduh cuma dapat isi folder saat itu. Kirim ulang
tautannya kalau sempat.

**QR fisik hilang atau tamu belum sempat memindai.** Buka **Riwayat**, ketik namanya,
tekan Tampilkan QR. Tidak ada yang diupload ulang — fotonya sudah di Drive sejak sesi
berjalan. Bisa juga Salin tautan lalu kirim lewat pesan.

**Aplikasi tertutup di tengah sesi.** Buka lagi. Kalau ada sesi yang belum diakhiri,
halaman Sesi menampilkannya di atas dengan pilihan lanjutkan atau akhiri sekarang. Tidak
ada foto yang hilang.

**Monitor kedua tercabut atau jendelanya tertutup.** Sesi tetap jalan. QR bisa ditampilkan
penuh layar di laptop. Monitor kedua perkakas, bukan syarat.

**Layar operator berhenti berubah.** Kalau chip merah "Terputus dari server" muncul, angka
di layar sudah basi dan tombol Selesai dimatikan. Jangan tutup jendelanya dan jangan mulai
sesi baru — sesinya kemungkinan besar masih berjalan di latar. Tekan Coba sambung ulang.

**Kuota Drive habis di tengah acara.** Upload berhenti, foto menumpuk di antrean, tapi
tidak ada yang hilang dari laptop. Kosongkan Drive dari HP, atau selesaikan acara dan
upload sisanya nanti lewat Riwayat.

---

## Yang sengaja tidak ada

Tidak ada tombol hapus arsip lokal di aplikasi. `local_archive/` adalah lapis backup kedua
setelah kartu SD, dan satu klik yang salah menghapusnya lebih mahal daripada repot
membersihkannya lewat Explorer.

Tidak ada login. Aplikasi hanya diakses dari laptop operator dan tidak membuka port ke
internet publik (PRD NFR4).

Tidak ada pencetakan foto, pembayaran, multi-kamera, dan dukungan Mac di v1 — semuanya
tercatat di PRD §5 sebagai kandidat versi berikutnya.

Aplikasi tidak pernah memutuskan sendiri kapan sesi selesai. Kalau tidak ada foto baru
selama beberapa menit, yang paling jauh boleh dilakukan sistem adalah memberi tahu
operator; menutup sesinya tetap keputusan manusia.

## Yang masih terbuka

Tema gelap belum dibuat. Layar putih besar di ballroom remang belum diuji di venue nyata,
dan itu perbaikan pertama kalau ada keluhan silau.

Berkas font Hanken Grotesk dan JetBrains Mono belum ada di repo. Sampai woff2-nya ditaruh
di `app/static/fonts/`, tipografi yang terlihat bukan yang dimaksud `design.md`.

Alur "Upload sisanya" dari Riwayat baru berupa tombol. Bentuk umpan baliknya saat proses
berjalan belum diputuskan.

Daftar lengkapnya ada di `design.md` §10.
