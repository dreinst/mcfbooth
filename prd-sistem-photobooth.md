# PRD: Sistem Photobooth Otomatis

## 1. Latar Belakang

Di event dengan photobooth, proses distribusi foto ke tamu biasanya lambat dan manual — dikirim lewat email, USB, atau upload satu-satu ke sosial media setelah acara selesai. Operator juga sering kesulitan melacak foto milik tamu tertentu kalau ada masalah di tengah jalan.

Sistem ini membuat proses itu otomatis: begitu operator selesai motret satu sesi, tamu langsung bisa scan QR dan download foto mereka sendiri, tanpa menunggu proses manual apa pun setelahnya.

## 2. Tujuan

- Menghilangkan jeda antara "sesi selesai" dan "tamu bisa download" — idealnya nyaris instan.
- Foto tidak pernah hilang meskipun koneksi internet venue tidak stabil.
- Operator bisa menjalankan sistem dengan langkah minimal, tanpa training rumit.
- Setiap sesi bisa ditelusuri ulang berdasarkan nama tamu, kalau QR fisik hilang atau ada kendala teknis.

## 3. Target Pengguna

| Peran | Deskripsi |
|---|---|
| Operator | Menjalankan kamera & aplikasi di laptop, biasanya fotografer/vendor event. Cukup familiar dengan komputer, tidak harus teknis. |
| Tamu | Peserta event yang difoto. Tidak teknis sama sekali — interaksinya cuma scan QR dengan HP. |

## 4. User Stories

- Sebagai **operator**, saya ingin input nama tamu dan mulai sesi, supaya semua foto yang diambil otomatis terkait ke tamu tersebut.
- Sebagai **operator**, saya ingin melihat jumlah foto yang sudah terupload dan status pending, supaya saya tahu kapan aman untuk mengakhiri sesi.
- Sebagai **operator**, saya ingin mengakhiri sesi dengan satu klik, supaya QR langsung tampil untuk tamu.
- Sebagai **operator**, saya ingin mencari sesi lama berdasarkan nama tamu, supaya saya bisa generate ulang QR kalau hilang atau bermasalah.
- Sebagai **tamu**, saya ingin scan QR dan langsung download foto saya, tanpa install aplikasi atau bikin akun apa pun.
- Sebagai **tamu**, saya ingin tetap bisa mengakses foto meski sistem operator berbasis lokal, karena saya mengakses lewat internet HP saya sendiri.

## 5. Ruang Lingkup

### Termasuk (v1)

- Platform Windows
- Tethering kamera DSLR/mirrorless lewat digiCamControl
- Satu kamera & satu laptop operator per waktu
- Google Drive sebagai storage & distribusi ke tamu
- Log sesi lokal (SQLite), bisa dicari berdasarkan nama tamu
- Generate & tampilkan QR code setelah sesi diakhiri operator
- Retry otomatis kalau upload gagal, tanpa kehilangan foto

### Tidak termasuk (v1 — kandidat v2)

- Gallery page custom dengan branding & download ZIP (masih pakai link Drive langsung)
- Dukungan Mac
- Multi-kamera atau multi-station bersamaan
- Layar terpisah untuk operator vs tamu
- Deteksi otomatis "sesi selesai" (tetap manual, sesuai prinsip operator selalu konfirmasi)
- Integrasi pencetakan foto atau pembayaran

## 6. Requirement Fungsional

| ID | Requirement |
|---|---|
| FR1 | Operator dapat input nama tamu untuk memulai sesi baru |
| FR2 | Sistem membuat kode sesi unik (nama + timestamp) otomatis |
| FR3 | Sistem membuat folder Drive khusus sesi tersebut saat sesi dimulai (bukan setelah selesai) |
| FR4 | Folder diset permission "anyone with link - viewer" secara otomatis |
| FR5 | Sistem memantau folder hasil tethering kamera dan mendeteksi foto baru otomatis |
| FR6 | Setiap foto yang terdeteksi diupload otomatis ke folder Drive sesi yang aktif |
| FR7 | Upload yang gagal di-retry otomatis tanpa perlu aksi operator |
| FR8 | File foto lokal tidak dihapus sebelum upload terkonfirmasi sukses |
| FR9 | Operator dapat melihat status upload real-time (jumlah terkirim / pending / gagal) |
| FR10 | Operator dapat mengakhiri sesi secara manual dengan satu aksi |
| FR11 | QR code digenerate dari link folder Drive saat sesi diakhiri |
| FR12 | QR code ditampilkan jelas di layar untuk discan tamu |
| FR13 | Setiap sesi tercatat permanen (nama tamu, kode sesi, link, status, waktu mulai/selesai), bertahan walau aplikasi ditutup |
| FR14 | Operator dapat mencari sesi lama berdasarkan nama tamu dan generate ulang QR-nya |

## 7. Requirement Non-Fungsional

| ID | Requirement |
|---|---|
| NFR1 | Sistem tetap berfungsi meski koneksi internet venue tidak stabil (retry + backup lokal) |
| NFR2 | Foto terdeteksi & mulai diupload dalam hitungan detik setelah selesai diambil kamera |
| NFR3 | Akses Google Drive dibatasi hanya ke file yang dibuat aplikasi (scope `drive.file`), bukan seluruh akun Drive |
| NFR4 | Laptop tidak perlu membuka akses dari internet publik — aplikasi hanya diakses lokal oleh operator |
| NFR5 | Alur operator maksimal 3 aksi per sesi: input nama, mulai, selesai |
| NFR6 | Berjalan di Windows |
| NFR7 | Komponen sistem modular — bagian tampilan link (Drive vs gallery custom) bisa diganti tanpa mengubah logic upload/log |

## 8. Alur Pengguna

1. Operator input nama tamu → tekan **Mulai Sesi**
2. Layar menunjukkan status "sesi aktif" + jumlah foto yang sudah masuk
3. Operator memotret tamu seperti biasa memakai kamera
4. Foto otomatis terupload di belakang layar, operator bisa lihat progresnya
5. Operator menekan **Selesai** setelah yakin semua foto sudah masuk
6. QR code tampil di layar
7. Tamu scan QR pakai HP → langsung ke folder Drive → download foto

## 9. Requirement UI

- Tiga tahap tampilan: **idle** (form nama + tombol mulai), **aktif** (status & progres upload + tombol selesai), **selesai** (QR + instruksi untuk tamu).
- QR **hanya muncul setelah operator menekan Selesai** — tidak ada kondisi lain yang menampilkannya, supaya tamu tidak scan sebelum semua foto lengkap.
- Status upload harus terlihat jelas oleh operator sebelum menekan Selesai (indikator jumlah pending vs terkirim).
- Ada mode pencarian sesi lama (input nama tamu → tampil link/QR sesi tersebut) sebagai fitur terpisah dari alur utama.

## 10. Asumsi & Ketergantungan

- Venue punya koneksi internet yang cukup (meski tidak stabil) untuk upload akhirnya berhasil — sistem menangani keterlambatan, bukan ketiadaan internet total permanen.
- Operator punya akun Google dengan kuota Drive yang cukup untuk menampung foto event.
- Kamera yang dipakai didukung oleh digiCamControl untuk tethering.
- Satu laptop menangani satu sesi aktif pada satu waktu (tidak ada dua sesi paralel di v1).

## 11. Metrik Keberhasilan

- Persentase sesi di mana semua foto berhasil terupload sebelum tamu scan QR.
- Waktu dari "tombol Selesai ditekan" sampai QR tampil (target: nyaris instan).
- Jumlah kasus di mana fitur pencarian sesi lama harus dipakai (indikator seberapa sering ada kendala di lapangan).
- Kemudahan penggunaan menurut operator (feedback kualitatif setelah event).

## 12. Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Wifi venue mati total | Foto tetap tersimpan di kartu SD kamera dan local archive; upload menyusul begitu koneksi kembali |
| Kuota Drive penuh di tengah event | Cek kuota sebelum event, siapkan akun dengan storage cukup |
| Kamera tidak kompatibel dengan digiCamControl | Verifikasi daftar kamera yang didukung sebelum hari-H |
| Link "anyone with link" berpotensi diakses pihak tak diundang | ID folder Drive acak & tidak terindeks mesin pencari; link hanya disebar lewat QR fisik ke tamu terkait |

## 13. Referensi

Detail teknis komponen, skema database, dan struktur folder ada di `arsitektur-sistem-photobooth.md`.
