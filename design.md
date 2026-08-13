# Design — Sistem Photobooth MCF

Dokumen ini mengatur tampilan dan perilaku antarmuka. Yang mengatur *apa* yang dibangun
ada di `prd-sistem-photobooth.md`; yang mengatur *bagaimana* sistemnya tersusun ada di
`arsitektur-sistem-photobooth.md`. Kalau ketiganya berselisih, PRD menang soal lingkup,
arsitektur menang soal data, dokumen ini menang soal tampilan.

Prototipe yang bisa dibuka ada di `prototipe/index.html` — empat halaman operator
plus halaman layar tamu, tanpa koneksi internet sama sekali. Ia harus dilayani lewat
HTTP (`python3 -m http.server` dari dalam foldernya), bukan dibuka sebagai berkas:
sinkronisasi dua jendela memakai BroadcastChannel, yang tidak berbagi origin di `file://`.

Rujukan berbentuk `photobooth_*/code.html:<baris>` dan `kinetic_operator/DESIGN.md:<baris>`
menunjuk ke isi `design md.zip` — desain lama hasil Stitch, relatif terhadap folder
`stitch_modern_color_palette_branding/` di dalam arsip itu. Ekstrak arsipnya kalau mau
memeriksa sendiri.

---

## 1. Keputusan yang mendasari dokumen ini

Keputusan pemilik proyek yang membentuk isi dokumen ini.

Fitur yang tidak punya sumber data di arsitektur dibuang, diganti pemeriksaan yang
benar-benar bisa dijawab sistem. Bahasa antarmuka Indonesia seluruhnya. Panel operator
menampilkan pratinjau foto, yang menuntut endpoint baru di server. Tema terang saja,
tanpa tema gelap.

Yang paling menentukan bentuknya: **akan ada monitor kedua khusus untuk tamu.** Dua
layar hidup bersamaan — panel operator tetap di laptop, layar tamu jadi jendela terpisah
yang di-fullscreen di monitor kedua. Operator tidak pernah memutar laptopnya. Arsitektur
menyebut layar terpisah sebagai kandidat v2 (`arsitektur-sistem-photobooth.md:155`);
keputusan ini memindahkannya ke v1.

Dua turunannya diputuskan bersamaan. Selama sesi berjalan, monitor kedua menampilkan
foto yang masuk satu per satu, bukan layar netral — tamu punya sesuatu untuk ditonton
sambil menunggu, dan thumbnail-nya sudah ada. QR bertahan di monitor kedua sampai
operator memulai sesi berikutnya, bukan hilang lewat hitung mundur.

Konsekuensi tema terang ditulis apa adanya: layar putih besar di ballroom remang tetap
mengganggu operator maupun tamu. Yang bisa dilakukan desain hanya meredamnya — kanvas
diturunkan ke `#f4f5f7` alih-alih putih murni, dan bidang putih dibatasi ke permukaan
kartu, bukan ke seluruh halaman. Kalau nanti ada keluhan silau di lapangan, tema gelap
adalah perbaikan pertama yang harus dipertimbangkan.

---

## 2. Fondasi

### 2.1 Prinsip

**Dua penonton, dua layar.** Operator butuh kepadatan dan kontrol; tamu butuh satu pesan
besar yang terbaca dari beberapa meter. Keduanya tidak boleh dilayani oleh tampilan yang
sama, dan sekarang tidak perlu — masing-masing punya monitornya sendiri. Turunannya:
apa pun yang hanya berarti bagi operator tidak boleh bocor ke monitor tamu, dan operator
harus selalu bisa tahu apa yang sedang tampil di monitor yang tidak dia hadapi.

**Yang salah menang secara visual.** Layar yang rapi ketika semua berhasil tapi tidak
menonjolkan dua foto yang gagal di antara dua belas yang berhasil adalah kegagalan
desain, sekalipun terlihat bagus. Aturan turunannya: nol kegagalan tampil diam, satu
kegagalan mengubah bentuk kartunya.

**Antarmuka tidak menanyakan apa yang sudah diketahuinya.** Kalau sistem tahu jumlah
antrean nol, dia tidak meminta manusia mencentang bahwa antreannya nol.

**Tombol tidak pernah dihilangkan karena keadaan.** Tombol yang hilang terbaca seperti
bug. Tombol yang terlihat, nonaktif, dan menyebut alasannya mengajarkan cara kerja
sistem sambil dipakai.

**Setiap angka bisa ditelusuri asalnya.** Angka yang tidak bisa dijelaskan dari mana
datangnya tidak boleh tampil.

### 2.2 Tiga tuas

Mengikuti `design-taste`: VARIANCE 3, MOTION 3, DENSITY 5.

Variance rendah karena operator mencari yang salah, bukan yang indah — tata letak
terstruktur dan konsisten menang atas komposisi menarik. Motion lebih tenang daripada
setelan dashboard biasa karena layar ini dilirik sekilas di sela memotret, bukan
dipelototi di meja. Density lebih longgar daripada dashboard operasional karena
operator membacanya sambil berdiri, sering dari jarak lebih jauh dari monitor kantor.

### 2.3 Tipografi

Dua keluarga, bukan tiga. Design sebelumnya memuat Hanken Grotesk, Inter, dan JetBrains
Mono sekaligus — tiga berkas font untuk aplikasi yang harus jalan tanpa internet.

| Peran | Keluarga |
|---|---|
| Semua teks antarmuka | Hanken Grotesk |
| Kode sesi, path berkas, nama file, timestamp, label meta | JetBrains Mono |

Inter dibuang. Hanken Grotesk mengambil alih badan teks; x-height-nya cukup untuk teks
padat dan geometrinya tetap tegas di ukuran besar.

Skala:

| Nama | Ukuran / tinggi baris | Berat | Dipakai untuk |
|---|---|---|---|
| `display` | 44 / 48 | 800 | nama tamu di sesi aktif, angka penghitung |
| `guest-name` | 8,6vw (93px di 1080) | 800 | nama tamu di layar tamu — lihat §5.5 |
| `h1` | 28 / 34 | 700 | judul layar |
| `h2` | 20 / 26 | 700 | judul bagian |
| `body` | 16 / 24 | 400 | teks umum |
| `small` | 14 / 20 | 400 | keterangan |
| `mono` | 12 / 16, tracking .06em, huruf besar | 500 | label meta |
| `mono-plain` | 13 / 20, tanpa tracking | 400 | kode sesi & path |

Semua angka pakai `font-variant-numeric: tabular-nums` supaya kolom tidak bergoyang
saat penghitung berubah.

Berkas font di-bundle lokal di `app/static/fonts/`. Selama berkasnya belum ada,
prototipe jatuh ke font sistem — ini tercatat sebagai pekerjaan yang belum selesai
di §9.

### 2.4 Warna

Design sebelumnya memakai biru untuk badge "SUCCESS" (`photobooth_sesi_aktif/code.html:248`),
oranye-merah untuk "QUEUED" (`:262`), dan oranye-merah yang sama untuk tombol utama
(`photobooth_konfirmasi_selesai/code.html:208`). Tidak ada satu pun warna yang punya
satu arti. Palet berikut memperbaikinya: satu warna, satu arti, tanpa pengecualian.

| Token | Nilai | Arti |
|---|---|---|
| `--bg` | `#f4f5f7` | kanvas halaman |
| `--surface` | `#ffffff` | permukaan kartu |
| `--surface-2` | `#fafbfc` | permukaan tenggelam (input, kartu di dalam kartu) |
| `--line` | `#e2e5ea` | garis rambut |
| `--line-strong` | `#cbd0d8` | garis yang harus terlihat (batas input, tombol netral) |
| `--ink` | `#12161f` | teks utama |
| `--ink-2` | `#5a6270` | teks sekunder |
| `--ink-3` | `#616875` | teks tersier & label meta |
| `--accent` | `#1b4fd8` | aksi utama dan keadaan aktif, tidak untuk yang lain |
| `--accent-strong` | `#143da8` | aksen saat hover |
| `--accent-soft` | `#eaf0ff` | latar aksen dan cincin fokus |
| `--ok` | `#0f7a4a` | foto sudah sampai di Drive |
| `--wait` | `#9a6400` | foto sedang diantre |
| `--bad` | `#c02626` | gagal, terputus, terhalang |
| `--bad-strong` | `#931d1d` | merah saat hover dan teks di atas latar merah muda |

Rasio kontras terhadap `--surface`, diukur bukan diperkirakan: `--ink` 18,1; `--ink-2`
6,2; `--ink-3` 5,6; `--accent` 6,7; `--ok` 5,4; `--wait` 5,0; `--bad` 5,9. Teks putih
di atas `--accent` 6,7. Teks di dalam chip berwarna juga diukur: hijau di atas hijau
muda 4,7; kuning di atas kuning muda 4,5; merah di atas merah muda 5,1. Semuanya lolos
ambang 4,5:1.

Merah tidak pernah dipakai untuk hal yang berhasil. Ini yang membuat tombol "Ya,
Tampilkan QR Code" di design lama salah: menampilkan QR adalah tujuan sesi, dan
mewarnainya merah melatih operator berhenti membaca merah.

Warna mentah dilarang di markup. Satu-satunya pengecualian adalah kartu QR, yang wajib
hitam di atas putih apa pun temanya (§5.4).

### 2.5 Ruang, bentuk, kedalaman

Skala spasi kelipatan 4: 4, 8, 12, 16, 24, 32, 48, 64. Tidak ada nilai di luar skala.

Radius: 6px untuk elemen kecil (tag, chip persegi), 10px untuk tombol dan input, 14px
untuk kartu, penuh untuk chip status. Design lama menyetel `full: 0.75rem`
(`photobooth_idle_mode/code.html:63-68`), jadi `rounded-full` menghasilkan 12px dan
aturan "Status Pills: 9999px" di `DESIGN.md:145` tidak pernah benar-benar terjadi.

Kedalaman datang dari garis rambut dan lapisan permukaan, bukan bayangan. Satu-satunya
bayangan di seluruh sistem dipakai untuk dialog yang mengambang di atas halaman.

Target sentuh minimum 48px untuk tombol, 44px untuk kontrol sekunder, 64px untuk aksi
utama dan input nama tamu. Design lama melanggar batasnya sendiri di beberapa tempat:
tombol "Lihat QR" 40px (`photobooth_riwayat_sesi/code.html:216`), tombol paginasi 40px
(`:275-279`), dan checkbox konfirmasi 20px (`photobooth_konfirmasi_selesai/code.html:198`).

Aksi per foto selalu terlihat, tidak pernah hanya muncul saat hover. Design lama
menyembunyikan tombol per foto di balik hover (`photobooth_sesi_aktif/code.html:282-285`),
yang berarti tombol itu tidak ada sama sekali di layar sentuh dan sulit dijangkau
dengan trackpad sambil berdiri.

### 2.6 Gerak

Mengikuti `emil-animations`. Hanya `transform` dan `opacity` yang dianimasikan; easing
`cubic-bezier(.22, 1, .36, 1)`; 140ms untuk umpan balik tekan dan hover, 200ms untuk
elemen yang masuk.

Animasi berulang dibatasi dua, keduanya opacity saja: titik penanda sesi hidup, dan
denyut kerangka saat memuat. Yang kedua hilang begitu data datang. Design lama
menjalankan tiga animasi berulang bersamaan sepanjang waktu —
`pulse-ring` pada titik kamera (`photobooth_idle_mode/code.html:97-104`), `animate-pulse`
pada label LIVE SESSION (`photobooth_sesi_aktif/code.html:224`), dan `animate-ping` pada
status Done di riwayat (`photobooth_riwayat_sesi/code.html:211`). Yang ketiga keliru
maknanya: denyut menandakan sesuatu hidup, dan sesi yang selesai tidak hidup.

`pulse-ring` juga menganimasikan `box-shadow`, yang memicu paint tiap frame. Diganti
opacity.

Blok `prefers-reduced-motion` wajib ada dan mematikan animasi masuk, bukan
mempercepatnya. Design lama tidak punya blok itu sama sekali.

---

## 3. Kerangka aplikasi

Aplikasi operator memakai sidebar tetap dengan empat tujuan. Ini keputusan pemilik
proyek, dan ia membalik rancangan sebelumnya di dokumen ini — versi pertama menghapus
sidebar dengan alasan NFR5 membatasi alur ke tiga aksi. Pembalikannya bisa dipertahankan
karena masalah sidebar lama bukan sidebarnya, melainkan isinya: Dashboard yang tidak
menuju ke mana-mana, Hardware berisi telemetri karangan, dan Log Out untuk aplikasi tanpa
login. Empat tujuan di bawah semuanya punya isi nyata, dan alur tiga aksi tetap utuh di
dalam satu halaman.

| Tujuan | Isi |
|---|---|
| Sesi | seluruh alur operator: idle, sesi berjalan, sesi selesai. Halaman ini yang dipakai 95% waktu. |
| Riwayat | pencarian sesi lama dan pembuatan ulang QR (FR14) |
| Layar tamu | keadaan monitor kedua, cuplikan langsungnya, dan cara memasangnya |
| Pengaturan | akun Drive dan kuota, path folder tethering dan arsip, kebijakan retry, izin folder |

Idle, berjalan, dan selesai adalah tiga keadaan dari satu halaman, bukan tiga tujuan.
Menaruhnya di sidebar akan mengundang operator berpindah ke tahap yang tidak berlaku —
tidak ada gunanya membuka "sesi selesai" saat tidak ada sesi.

Di kaki sidebar ada ringkasan kesehatan sistem yang selalu terlihat: kuota Drive,
internet, disk, dan layar tamu. Itu menggantikan footer `v2.4.0-build.88` dan
"API: Connected" di design lama, yang isinya statis dan tidak bisa ditindaklanjuti.

Aplikasi berjalan sebagai dua jendela dari server yang sama.

**Jendela operator** memakai sidebar dan berisi keempat halaman di atas. Ia hidup di
laptop dan tidak pernah berubah jadi tampilan tamu.

**Jendela tamu** hanya berisi halaman `tamu`, dibuka sekali di awal acara dan
di-fullscreen di monitor kedua. Tidak ada sidebar, tidak ada navigasi, tidak ada satu pun
elemen yang membawa ke data sesi lain. Ia tidak dikendalikan langsung oleh operator — keadaannya
mengikuti sesi di server, jadi menekan Selesai di laptop cukup untuk memunculkan QR di
monitor sebelah.

Keduanya membaca keadaan dari server, bukan saling mengirim pesan. Jendela tamu yang
sempat tertutup dan dibuka ulang di tengah acara langsung menampilkan keadaan yang
benar tanpa perlu sinkronisasi manual.

---

## 4. Layar operator

### 4.1 Idle dan pemeriksaan awal

Berkas: `prototipe/index.html`, tahap **idle**.

Dua kolom. Kiri, lebih lebar, adalah satu-satunya titik fokus: input nama tamu setinggi
64px dan tombol Mulai Sesi setinggi 64px. Kanan berisi enam pemeriksaan yang dijalankan
sebelum sesi dimulai.

Pemeriksaan yang ditampilkan, semuanya bisa dijawab tanpa perangkat keras tambahan:

| Pemeriksaan | Sumber |
|---|---|
| Google Drive terhubung | validitas token OAuth + alamat akun |
| Kuota Drive | `about.get` dari Drive API |
| Folder tethering terpantau | watcher aktif pada path yang dikonfigurasi |
| Koneksi internet | permintaan ringan berkala ke endpoint Google |
| Ruang disk lokal | ruang bebas pada partisi `local_archive` |
| Layar tamu | jendela monitor kedua terbuka atau tidak, dan sedang menampilkan apa |

Ini menggantikan kartu "Main Cam / Sensor: Active / Temp: 42°C"
(`photobooth_idle_mode/code.html:211`) dan seluruh halaman Hardware Status, yang
menampilkan baterai kamera (`photobooth_hardware_status/code.html:238-246`) dan
kecepatan jaringan (`:276-299`) tanpa ada satu pun komponen di arsitektur yang bisa
menghasilkan angka itu. Arsitektur hanya memantau folder hasil tethering
(`arsitektur-sistem-photobooth.md:48`); dari file yang jatuh ke folder, baterai dan
suhu tidak bisa diketahui.

Perbedaan peringatan dan penghalang dijaga tegas. Kuota Drive menipis berwarna kuning
dan tidak menghalangi apa pun — operator boleh memutuskan sendiri. Drive tidak
terhubung berwarna merah dan menonaktifkan tombol Mulai Sesi, karena sesi yang dimulai
tanpa folder tujuan menghasilkan foto yang tidak akan pernah sampai ke tamu. Tombolnya
tetap terlihat dengan alasannya tertulis di bawahnya.

Input nama menampilkan keterangan kalau nama serupa sudah dipakai hari ini. `session_code`
dijamin unik oleh timestamp berpresisi detik (`arsitektur-sistem-photobooth.md:65`), jadi
tabrakan nama tidak merusak data — yang rusak adalah pencarian di Riwayat berbulan-bulan
kemudian.
Keterangan ini mendorong operator menambahkan pembeda saat mengetik, bukan menyesalinya
nanti.

Varian sesi tertinggal muncul kalau ada baris `sessions` berstatus `active` saat
aplikasi dibuka. Arsitektur menjanjikan sesi tetap bisa ditelusuri walau aplikasi
sempat ditutup (`arsitektur-sistem-photobooth.md:15`), tapi design lama tidak punya
layar untuk keadaan itu. Pita peringatan menyebut nama, waktu mulai, jumlah foto, dan
kapan foto terakhir masuk, lalu menawarkan lanjutkan atau akhiri sekarang.

### 4.2 Sesi aktif

Berkas: `prototipe/index.html`, tahap **aktif**.

Kepala layar menampilkan nama tamu berukuran 44px, kode sesi dalam mono, dan tombol
Selesai. Tombol Selesai berwarna aksen biru, bukan merah — ia jalur normal, bukan aksi
merusak.

Tiga penghitung sejajar: sudah di Drive, sedang diupload, gagal. Yang ketiga inilah
yang hilang sepenuhnya dari design lama, padahal `photo_uploads.status` punya nilai
`failed` (`arsitektur-sistem-photobooth.md:83`) dan §3.2 poin 5 menyebut foto gagal
harus ditampilkan di UI operator supaya bisa di-retry manual sebelum sesi ditutup.

Perilaku penghitung gagal:

- Nol: teks abu, chip netral "Tidak ada", tanpa penekanan apa pun.
- Satu atau lebih: latar merah muda, batas merah 2px, chip "Perlu tindakan", dan pita
  merah muncul di atas penghitung berisi nama berkas yang gagal serta tombol coba lagi.

Di bawah penghitung ada baris yang menjadi jangkar kepercayaan operator: **foto terakhir
masuk berapa lama lalu**, dengan nama berkasnya. Ini menjawab kegagalan yang tidak bisa
dilihat dari tiga angka di atasnya. Semua penghitung dihitung dari berkas yang dilihat
pemantau folder; kalau tethering tersendat dan satu jepretan tidak pernah jatuh ke
folder, ketiga angka tetap cocok satu sama lain dan ketiganya salah. Jarak waktu foto
terakhir adalah satu-satunya angka yang bisa dibandingkan operator dengan ingatannya
sendiri. Kalimat itu ditulis eksplisit di layar, bukan disimpan di dokumentasi.

Grid pratinjau menampilkan foto yang masuk dengan status per foto. Foto gagal diberi
batas merah dan satu bilah merah selebar kartu di bagian bawahnya, setinggi 44px,
bertuliskan "Gagal — coba lagi". Satu elemen mengerjakan dua hal: menyatakan
kegagalannya dan menawarkan perbaikannya. Di layar sempit labelnya memendek jadi
"Coba lagi" — warna merah sudah menyatakan sisanya.

Di samping penanda kepercayaan ada kartu **Layar tamu**: cuplikan kecil berukuran 16:9
yang meniru apa yang sedang tampil di monitor kedua, ditambah status sambungan dan
tombol untuk membuka ulang jendelanya. Operator menghadap laptop dan tidak bisa melihat
monitor di belakang atau di sampingnya; tanpa cermin ini, QR bisa menampilkan sesi yang
salah selama sepuluh menit tanpa ada yang menyadarinya.

Varian server putus menangani keadaan yang tidak pernah dipertimbangkan design lama:
server Python mati sementara browser tetap terbuka. Design lama akan berhenti
memperbarui diri tanpa memberi tahu siapa pun, dan setiap angka di layar berubah jadi
kebohongan diam-diam. Perlakuan barunya: chip merah di bilah atas, pita yang menyebut
angka terakhir berumur berapa detik, penanda hidup berganti jadi titik merah, dan
tombol Selesai dinonaktifkan dengan alasan tertulis. Sesi tidak boleh diakhiri lewat
layar yang tidak tahu keadaan sebenarnya.

Cermin layar tamu ikut jujur di keadaan itu: ia tidak menebak, ia berubah merah dan
berbunyi "Tidak bisa dipastikan — server tidak menjawab", lalu menyarankan operator
memeriksa monitornya langsung. Cermin yang menampilkan gambar basi lebih berbahaya
daripada cermin yang mengaku tidak tahu.

### 4.3 Konfirmasi akhiri sesi

Berkas: `prototipe/index.html`, dialog konfirmasi.

Dialog ini punya dua bentuk, bukan satu. Design lama memakai satu bentuk untuk kedua
keadaan dan menambahkan checkbox manual "Pastikan semua foto tamu sudah terupload"
(`photobooth_konfirmasi_selesai/code.html:198`) — meminta manusia mengonfirmasi apa yang
sudah dihitung mesin dan ditampilkan di layar yang sama.

**Bentuk aman**, saat antrean dan kegagalan sama-sama nol. Chip hijau, judul "Akhiri
sesi <nama>?", ringkasan tiga baris (foto masuk, foto di Drive, kapan foto terakhir),
tanpa checkbox. Dua tombol setara lebar: batal, dan akhiri & tampilkan QR berwarna
aksen.

**Bentuk berisiko**, saat masih ada antrean atau kegagalan. Judulnya bukan pertanyaan
melainkan akibat: "Tamu tidak akan melihat 2 foto ini". Isinya menjelaskan kenapa, dan
kalimatnya harus tepat karena dua keadaan itu berbeda akibatnya. Foto yang masih antre
akan menyusul sendiri ke folder yang benar — `photo_uploads.session_id` sudah menunjuk ke
sana, jadi berakhirnya sesi tidak menghilangkan tujuannya. Foto berstatus `failed` tidak
menyusul sama sekali sampai di-upload ulang. Yang membuat keduanya sama-sama merugikan
adalah waktu: tamu memindai sekarang, mengunduh isi folder apa adanya saat itu, dan
kebanyakan tamu cuma memindai sekali. Berkas yang bermasalah disebut satu per satu
beserta statusnya.

Urutan tombolnya dibalik. Aksi utama menjadi "Kembali, coba upload lagi" dengan warna
aksen dan lebar penuh; "Tetap tampilkan QR" menjadi tombol garis merah yang lebih
sempit. Gesekan tambahan hanya pantas di sini, bukan di jalur aman.

### 4.4 Riwayat sesi

Berkas: `prototipe/riwayat.html`.

FR14 menyebut fungsinya: cari sesi lama berdasarkan nama tamu dan tampilkan ulang
QR-nya. Karena itu kolom pencarian ditaruh di atas dan mendapat fokus otomatis, bukan
diselipkan di pojok kanan judul seperti di `photobooth_riwayat_sesi/code.html:188-193`.

Tiap baris menampilkan nama tamu, kode sesi, rentang waktu, dan status upload.
Statusnya memakai kosakata yang sama dengan layar sesi aktif: "12 foto lengkap" hijau,
atau "2 dari 15 belum terkirim" merah. Sesi yang punya foto tertinggal tetap terlihat
sebagai bermasalah berhari-hari kemudian, bukan hanya selama sesinya berjalan, dan
barisnya menawarkan "Upload sisanya".

Status `Archived` di `photobooth_riwayat_sesi/code.html:238` dihapus. Kolom `status`
hanya punya `active` dan `done` (`arsitektur-sistem-photobooth.md:69`); menampilkan
nilai ketiga yang tidak ada di skema membuat operator menebak artinya.

Selain "Tampilkan QR", tiap baris menyediakan "Salin tautan" — lebih berguna daripada
QR ketika tamu sudah pulang dan tautannya perlu dikirim lewat pesan.

---

## 5. Layar tamu — monitor kedua

Berkas: `prototipe/tamu.html`. Tiga keadaan: sambutan, memotret, QR siap.
Halaman kontrolnya di sisi operator: `prototipe/layar-tamu.html`.

Ini jendela terpisah yang dibuka sekali di awal acara, di-fullscreen di monitor kedua,
lalu tidak disentuh lagi. Ia berganti keadaan sendiri mengikuti sesi di server —
operator tidak pernah memindahkan, memutar, atau menutup apa pun.

### 5.1 Tiga keadaan

**Sambutan**, saat tidak ada sesi berjalan. Wordmark besar dan satu kalimat yang
menjelaskan apa yang akan terjadi: foto muncul di layar ini, kode unduhan tampil setelah
sesi selesai. Tidak ada nama, tidak ada foto.

**Memotret**, dari operator menekan Mulai sampai menekan Selesai. Nama tamu 60px, jumlah
foto sejauh ini, dan grid foto yang bertambah sendiri. Tamu melihat hasilnya sambil
menunggu, dan booth punya sesuatu untuk ditonton. Foto baru masuk sekali dengan gerak
200ms; tidak ada animasi yang berulang selamanya di layar yang menyala berjam-jam.

Satu pil di bawah grid menyebut "Kode untuk mengunduh tampil setelah sesi selesai". Itu
menjaga janji PRD §9 — QR hanya muncul setelah operator konfirmasi — sambil mencegah
tamu menunggu sesuatu yang memang belum waktunya ada.

**QR siap**, setelah sesi diakhiri. Nama tamu, jumlah foto, kartu QR, satu kalimat
instruksi, tautan cadangan dalam mono, dan enam pratinjau. Nama dan jumlah foto tidak
ada di design lama (`photobooth_scan_qr/code.html:111-116`); keduanya memberi tahu tamu
bahwa ini memang fotonya, sekaligus menangkap operator yang membuka sesi keliru.

QR bertahan sampai operator memulai sesi berikutnya. Tamu punya waktu selama yang dia
butuhkan, dan operator tidak menanggung satu aksi tambahan — NFR5 membatasi alurnya ke
tiga aksi. Konsekuensinya disebut apa adanya: tamu berikutnya bisa melihat QR tamu
sebelumnya selama beberapa detik sebelum layar berganti ke keadaan memotret.

### 5.2 Yang tidak boleh ada di layar ini

Status upload. Antre dan gagal adalah urusan operator; tamu yang membaca "2 gagal" tidak
punya apa pun untuk dilakukan selain cemas. Grid di layar tamu menampilkan foto, titik.

Nama tamu lain. Riwayat tidak bisa dicapai dari jendela ini karena jendela ini tidak
punya navigasi sama sekali.

Sisa sesi sebelumnya. Grid harus dikosongkan saat sesi baru dimulai, bukan diisi ulang
di atas isi lama.

### 5.3 Kalau monitor keduanya tidak ada

Monitor kedua adalah perkakas, bukan syarat. Sesi tetap boleh dimulai tanpa dia — di
pemeriksaan awal, barisnya memberi keterangan, bukan menghalangi. Kalau jendelanya
tertutup atau monitornya tercabut, QR ditampilkan di laptop operator sebagai layar penuh,
dengan jalan keluar kecil di sudut yang butuh tekan-tahan.

Jalan keluar itu sengaja dibuat sulit ditemukan tamu. Design lama melakukan kebalikannya:
tombol paling menonjol di layar yang dilihat tamu adalah "Kembali ke Beranda"
(`photobooth_scan_qr/code.html:119-122`) — afordansi terbesar yang diberikan kepada tamu
adalah menghapus benda yang dia datangi.

### 5.4 Dua aturan teknis

Kartu QR selalu hitam di atas putih. Membalik warnanya membuat sebagian pemindai HP
gagal membaca, dan zona sunyi di sekeliling kode tidak boleh dipotong oleh padding
kartu.

Jendela ini tidak boleh tidur. Screen Wake Lock API dipanggil saat jendela dibuka dan
dipertahankan sepanjang acara, bukan hanya saat QR tampil.

### 5.5 Ukuran untuk 1080 × 1920

Monitornya 1920 × 1080 yang diputar berdiri, jadi kanvasnya 1080 lebar dan 1920 tinggi.
Lebar yang jadi kendala, bukan tinggi, jadi semua ukuran di layar tamu diikat ke `vw` —
bukan piksel tetap, bukan `vh`.

| Elemen | Ukuran | Di 1080px |
|---|---|---|
| Nama tamu | 8,6vw | 93px |
| Jumlah foto | 3,4vw | 37px |
| Kartu QR | 58vw | 626px |
| Instruksi | 3,3vw | 36px |
| Tautan cadangan | 1,75vw | 19px |
| Tile grid memotret | 2 kolom, rasio 3:2 | ±477px |
| Cuplikan di layar QR | 12,6vw, satu baris | 136px |

QR 626px di panel 24 inci yang diputar berdiri berarti sekitar 17 cm persegi — terbaca
oleh kamera HP dari dua meter, jauh melebihi jarak orang berdiri di depan booth.

Dua hal dibatasi supaya layar kiosk tidak pernah perlu digulir. Grid memotret hanya
menampilkan enam foto terbaru; sesi dua puluh foto akan mendorong pil penjelas di
bawahnya keluar layar. Dan nama tamu mengecil sendiri di atas 16 karakter, lalu mengecil
lagi di atas 26 — "Keluarga Wijaya Pratama" pada ukuran penuh melipat jadi dua baris dan
mendorong QR turun 128px, cukup untuk memotongnya di kaki layar.

Blok `@media (orientation: portrait)` ditaruh paling akhir di `ui.css` dengan sengaja.
Media query berbasis lebar di atasnya menganggap 1080px sebagai desktop, dan tanpa urutan
itu aturan portrait akan kalah.

---

## 6. Keadaan yang berlaku di semua layar

**Kosong tidak sama dengan gagal.** Riwayat tanpa hasil pencarian berbunyi "Tidak ada
sesi bernama X" dan menawarkan ejaan yang lebih pendek; riwayat yang memang belum
pernah terisi berbunyi "Belum ada sesi sama sekali" dan menawarkan memulai sesi
pertama. Keduanya butuh tindakan berbeda, jadi keduanya tidak boleh berbunyi "Tidak ada
data".

**Memuat memakai kerangka**, bukan spinner tunggal — bentuknya menyerupai isi yang akan
datang supaya tata letak tidak melompat.

**Server tidak terjawab** ditangani seperti di §4.2: angka ditandai basi beserta
umurnya, aksi yang mengubah keadaan dinonaktifkan, dan pesan menyebutkan apa yang
sebaiknya tidak dilakukan operator.

**Bahasa Indonesia seluruhnya.** Design lama mencampur keduanya dalam satu layar —
"Start Session" bersebelahan dengan "Mulai Sesi" di `photobooth_idle_mode/code.html:120`
dan `:197`.

---

## 7. Kondisi lapangan

Semua kontrol dapat dicapai lewat papan ketik, dan cincin fokus memakai `outline` 3px
warna aksen dengan `outline-offset` 2px — terlihat jelas di atas latar apa pun di palet.

Baris riwayat berubah bentuk menjadi kartu bertumpuk di bawah 900px, bukan di bawah
768px. Di 768px kelima kolomnya masih muat secara teknis, tapi kode sesi dan chip status
saling menempel sampai tidak terbaca — muat tidak sama dengan terbaca. Di bawah 720px
bilah atas melipat jadi dua baris dan penghitung menjadi satu kolom.

Tombol dialog menumpuk dengan aksi utama di paling bawah supaya paling dekat dengan ibu
jari, dan aksi berisiko tidak pernah jatuh ke posisi termudah itu. Dialog yang lebih
tinggi daripada layar bisa digulir di dalam lapisannya sendiri; sebelum diperbaiki,
dialog "berisiko" setinggi 675px di layar 667px membuat tombol utamanya tidak terjangkau
sama sekali.

Tidak ada halaman yang menggulir horizontal di 375, 768, 900, 1024, dan 1280 — diperiksa
otomatis pada 13 kombinasi layar dan varian.

Kontras minimum 4,5:1 untuk semua teks, angkanya di §2.4. Pemeriksaan yang sama juga
menghitung tinggi setiap tombol, tautan, dan input (tidak ada yang di bawah 44px) dan
memastikan tiap elemen yang bisa dijangkau papan ketik punya cincin fokus 3px.

Tombol yang dinonaktifkan memakai `aria-disabled`, bukan atribut `disabled`. Atribut
`disabled` mengeluarkan tombol dari urutan tab, jadi pemakai papan ketik tidak akan
pernah sampai ke alasan yang ditulis di bawahnya — persis hal yang seharusnya dijamin
oleh prinsip di §2.1.

Aset front-end di-bundle lokal. Design lama memuat Tailwind dari `cdn.tailwindcss.com`
(`photobooth_idle_mode/code.html:5`) dan tiga keluarga font dari `fonts.googleapis.com`
(`:6-8`), padahal NFR1 menuntut sistem tetap berfungsi saat internet venue tidak stabil.
Wifi putus berarti aplikasi tampil tanpa gaya sama sekali di tengah acara.

---

## 8. Yang dituntut desain ini dari arsitektur

Bagian ini disebut terbuka supaya tidak diselundupkan sebagai "sekadar tampilan".
Skema database tidak perlu berubah.

| Kebutuhan | Bentuk | Untuk layar |
|---|---|---|
| Hasil pemeriksaan awal | `GET /api/preflight` — status token Drive, kuota, watcher, internet, ruang disk | 01 |
| Daftar foto satu sesi | `GET /api/sessions/{id}/photos` — id, nama berkas, status, waktu | 02 |
| Pratinjau foto | `GET /api/thumb/{photo_id}` — thumbnail dari `local_archive`, dibuat sekali lalu disimpan di `thumbs/` | 02, 04 |
| Upload ulang satu foto | `POST /api/photos/{id}/retry` | 02, 05 |
| Upload ulang sisa sesi lama | `POST /api/sessions/{id}/retry-failed` | 05 |
| Halaman layar tamu | rute `GET /tamu` — dokumen terpisah, tanpa navigasi, dibuka sebagai jendela kedua | 04 |
| Keadaan layar tamu | `GET /api/tampilan-tamu` — keadaan (`sambutan`/`memotret`/`qr`), nama tamu, daftar thumbnail, tautan QR | 04, 02 |
| Aliran perubahan | Server-Sent Events di `/api/peristiwa` — jendela tamu berganti keadaan tanpa polling, jendela operator ikut memperbarui angkanya | 02, 04 |
| Jendela tamu terdeteksi | server mencatat koneksi SSE dari `/tamu` yang masih hidup, dipakai untuk chip "Terhubung" dan barisnya di pemeriksaan awal | 01, 02 |
| Aset front-end lokal | `app/static/` berisi CSS, JS, dan font woff2 | semua |
| Layar tidak tidur | Screen Wake Lock API, dipegang selama jendela tamu terbuka | 04 |

Thumbnail dibuat dari berkas yang sudah ada di `local_archive` (`arsitektur-sistem-photobooth.md:51`),
jadi tidak menambah lapis penyimpanan baru dan tidak menyentuh berkas aslinya. Ukuran
sisi panjang 400px cukup untuk grid operator; layar tamu memakai berkas yang sama, dan
di monitor 1080p tile selebar 300px masih tajam.

"Foto terakhir masuk" diturunkan dari `MAX(photo_uploads.created_at)` untuk sesi
berjalan — tidak perlu kolom baru.

Deteksi jendela tamu sengaja memakai koneksi SSE yang masih hidup, bukan Screen
Detection API. Yang ingin diketahui operator bukan "apakah ada monitor kedua terpasang",
melainkan "apakah jendela tamu benar-benar terbuka dan menerima keadaan". Monitor
terpasang tapi jendelanya tertutup adalah kegagalan yang sama, dan hanya cara ini yang
menangkap keduanya.

---

## 9. Yang dibuang dari desain sebelumnya

| Dibuang | Alasan |
|---|---|
| Halaman Hardware Status | Baterai, suhu, dan kecepatan jaringan tidak punya sumber data di arsitektur. Diganti pemeriksaan awal di layar idle. |
| Status printer & tombol print per foto | PRD `prd-sistem-photobooth.md:51` menyatakan pencetakan foto tidak termasuk v1. |
| Tombol "Clear Cache" | `photobooth_hardware_status/code.html:335-337`. Local archive adalah lapis backup kedua (`arsitektur-sistem-photobooth.md:128`) dan FR8 melarang penghapusan sebelum upload terkonfirmasi. Tombol itu satu klik dari menghapus lapis pengaman. |
| Login, profil operator, Log Out | Tidak ada autentikasi di PRD. NFR4 justru menyatakan aplikasi hanya diakses lokal oleh operator. |
| Isi sidebar lama (Dashboard, Hardware, Log Out) | Ketiganya tidak menuju ke apa pun yang nyata. Sidebarnya sendiri dipertahankan dengan empat tujuan yang punya isi — lihat §3. |
| Footer `v2.4.0-build.88`, "API: Connected" | Tidak memberi informasi yang bisa ditindaklanjuti, dan isinya statis di design lama. Diganti ringkasan kesehatan di kaki sidebar. |
| Tiga ikon di bilah atas (camera, cloud, wifi) | Tombol tanpa tujuan. |
| Status `Archived` | Tidak ada di enum `status`. |
| Checkbox konfirmasi manual | Menanyakan apa yang sudah diketahui sistem. |
| Inter sebagai keluarga font ketiga | Satu berkas font lagi untuk aplikasi yang harus jalan offline, tanpa peran yang tidak bisa diambil Hanken Grotesk. |

Nama produk diseragamkan menjadi "MCF Photobooth". Design lama memakai "MCF Booth" di
`photobooth_idle_mode/code.html:111` dan "PHOTO OPS" di `photobooth_hardware_status/code.html:151`.

---

## 10. Yang belum selesai

Berkas font Hanken Grotesk dan JetBrains Mono belum ada di repo. Sampai woff2-nya
ditaruh di `app/static/fonts/`, prototipe memakai font sistem dan tipografi yang
terlihat sekarang bukan tipografi yang dimaksud dokumen ini.

QR di `prototipe/tamu.html` adalah gambar contoh dan tidak bisa dipindai. Ia ada
untuk menilai ukuran dan tata letak; di produksi gambarnya datang dari
`qr_codes/<session_code>.png`.

Prototipe tidak memuat data dan tidak memanggil server — semua angka ditulis tetap di
markup. Perilaku yang bergantung waktu (umur data basi, kemunculan pita kegagalan) belum
bisa dinilai dari prototipe.

Yang berubah sejak revisi ini: dua jendela yang saling mengikuti sudah bisa dicoba.
Prototipe menyiarkan keadaan sesi lewat BroadcastChannel, jadi menekan Selesai di jendela
operator benar-benar memunculkan QR di jendela tamu. Yang masih disimulasikan adalah
sumber datanya — foto "masuk" dari timer, bukan dari folder tethering. Jeda nyata antara
jepretan dan tampilnya thumbnail baru ketahuan setelah watcher-nya ada.

Cuplikan layar tamu di panel operator sudah memakai `<iframe>` berskala dari halaman tamu
yang sungguhan, bukan gambaran abstrak. Kalau yang tampil di monitor kedua salah,
kesalahan itu ikut terlihat di cuplikannya.

Keadaan memuat hanya diatur sebagai aturan di §6 dan disediakan sebagai kelas `.skel`
di `prototipe/ui.css`; tidak ada layar yang memperagakannya, karena prototipe tidak
punya jeda pemuatan untuk diperagakan.

Tema gelap tidak dibuat, sesuai keputusan di §1. Risiko silau di ruangan gelap belum
diuji di venue nyata.

Alur "Upload sisanya" dari Riwayat belum punya layar sendiri — sekarang baru berupa
tombol. Bentuk umpan baliknya saat proses berjalan perlu diputuskan sebelum
diimplementasikan.
