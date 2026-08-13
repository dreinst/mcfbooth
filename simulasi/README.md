# Simulasi folder

Bentuk folder yang akan dipakai sistem saat sudah jalan. **Tidak ada yang berjalan di
sini** — ini kerangka statis supaya strukturnya bisa dilihat dan disepakati sebelum
kodenya ditulis.

```
simulasi/
├── tether_dropbox/                     kosong — tempat digiCamControl menjatuhkan jepretan
└── local_archive/
    └── Budi_Ani_20260811_115043/       satu folder per sesi, dinamai dari kode sesi
        ├── IMG_0041.JPG
        └── IMG_0042.JPG
```

## Yang mengisi masing-masing

`tether_dropbox/` diisi oleh digiCamControl, bukan oleh aplikasi. Aplikasi hanya
memantaunya. Folder ini sengaja kosong: isinya sementara, dan tiap berkas yang masuk
akan disalin keluar lalu tidak dibutuhkan lagi di sini.

`local_archive/<kode_sesi>/` diisi oleh pemantau folder — lapis backup kedua setelah
kartu SD. Nama foldernya sama persis dengan kode sesi yang dibuat
`prototipe/app.js` (`kodeSesi()`), jadi satu sesi bisa dilacak dari layar operator ke
disk tanpa penerjemahan.

Folder ketiga tidak ada di sini karena tidak ada di disk: folder per sesi di Google
Drive. Isinya sama dengan `local_archive/<kode_sesi>/`, bedanya cuma tempat.

## Tentang berkas contohnya

Dua `.JPG` di dalam `Budi_Ani_20260811_115043/` adalah gambar gradien 900 × 600 sebesar
14 KB, bukan foto. Foto DSLR sungguhan sekitar 25 MB — 400 foto berarti 10 GB, dan
angka itulah yang dipakai README utama untuk menghitung kuota Drive. Jangan pakai
ukuran berkas di folder ini untuk memperkirakan apa pun.

## Yang belum ada

Tidak ada pemantau folder, tidak ada penyalinan, tidak ada retry, tidak ada catatan
hasil. Membuat berkas di `tether_dropbox/` sekarang tidak menyebabkan apa-apa.
Perilaku itu ada di langkah 3 rencana di README utama.
