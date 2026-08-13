# Sistem Photobooth MCF

Operator memotret tamu di acara. Foto naik ke Google Drive sendiri, dan begitu operator
menekan Selesai, tamu memindai QR di monitor sebelahnya lalu mengunduh fotonya. Tidak ada
kirim manual, tidak ada tunggu sampai acara bubar.

## Status hari ini

🔴 **Aplikasinya belum ada.** Yang ada di folder ini baru dokumen dan prototipe tampilan.
Tidak ada `server.py`, tidak ada database, tidak ada koneksi ke Google Drive, tidak ada
pemantau folder. Prototipe di `prototipe/` berjalan penuh di browser dengan data karangan.

Panduan operator di bagian bawah menjelaskan sistem yang **dirancang**, bukan yang sudah
bisa dipakai. Jangan jadwalkan acara berdasarkan dokumen ini.

## Isi folder

| Berkas | Isi | Baca kalau |
|---|---|---|
| `prd-sistem-photobooth.md` | Lingkup, user story, requirement, risiko | mau tahu apa yang dibangun dan apa yang sengaja tidak |
| `arsitektur-sistem-photobooth.md` | Komponen, skema database, alur data, tech stack | mau tahu bagaimana sistemnya tersusun |
| `design.md` | Token visual, tiap layar, keadaan galat, tuntutan ke arsitektur | mau membangun tampilannya atau menilai keputusannya |
| `prototipe/` | Lima halaman HTML yang bisa diklik, tanpa backend | mau melihat hasilnya sekarang |
| `simulasi/` | Kerangka folder kerja, statis | mau melihat bentuk `tether_dropbox/` dan `local_archive/` |

Desain lama hasil Stitch (`design md.zip`, 200 KB) tidak ada di repo — ia cuma dibutuhkan
kalau kamu mau menelusuri rujukan `photobooth_*/code.html` di `design.md`.

Urutan baca untuk orang baru: PRD, lalu arsitektur, lalu `design.md`. Prototipenya dibuka
sambil membaca `design.md`.

---

## Menjalankan prototipe

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

Empat komponen di `arsitektur-sistem-photobooth.md` §3 belum satu pun ditulis. Urutan di
bawah menaruh yang paling berisiko lebih dulu, supaya kalau ada yang tidak bisa dikerjakan,
ketahuannya sekarang bukan seminggu sebelum acara.

**1. Kerangka server dan database.** FastAPI plus SQLite dengan dua tabel dari arsitektur
§3.3 (`sessions`, `photo_uploads`). Endpoint minimal: buat sesi, ambil sesi, akhiri sesi,
cari sesi. Belum menyentuh Drive maupun kamera. Selesai kalau sesi bisa dibuat lewat API
dan masih ada setelah server di-restart.

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

Sebelum langkah 2, siapkan proyek di Google Cloud Console dan unduh `credentials.json`.
Sebelum langkah 3, verifikasi kamera yang dipakai memang didukung digiCamControl —
PRD §12 menyebut ini sebagai risiko, dan mengeceknya lima menit.

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
