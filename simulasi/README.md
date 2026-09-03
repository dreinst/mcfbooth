# Simulasi folder

Bentuk folder kerja yang dipakai sistem, plus dua foto contoh yang dipakai skrip uji.
Tidak ada yang berjalan di sini — folder kerja sungguhan dibuat server sendiri di akar
repo (atau di path yang diatur `.env`).

```
simulasi/
├── tether_dropbox/                     kosong — tempat aplikasi tethering menjatuhkan jepretan
└── local_archive/
    └── Budi_Ani_20260811_115043/       satu folder per sesi, dinamai dari kode sesi
        ├── IMG_0041.JPG
        └── IMG_0042.JPG
```

## Yang mengisi masing-masing

`tether_dropbox/` diisi oleh aplikasi tethering (Imaging Edge Desktop atau
digiCamControl), bukan oleh aplikasi. Aplikasi hanya memantaunya dan tidak pernah
menghapus isinya — jadi di lapangan folder ini menumpuk semua jepretan acara.

`local_archive/<kode_sesi>/` diisi oleh pemantau folder — lapis backup kedua setelah
kartu SD. Nama foldernya sama persis dengan `session_code` yang dibuat `app/db.py`
(`kode_sesi()`), jadi satu sesi bisa dilacak dari layar operator ke disk tanpa
penerjemahan. Foto yang masuk saat tidak ada sesi diamankan ke `local_archive/_tanpa_sesi/`.

Folder ketiga tidak ada di sini karena tidak ada di disk: folder per sesi di Google
Drive (`MCF Photobooth/2. Result/<kode_sesi>/`). Isinya sama dengan
`local_archive/<kode_sesi>/`, bedanya cuma tempat.

## Tentang berkas contohnya

Dua `.JPG` di dalam `Budi_Ani_20260811_115043/` adalah gambar gradien 900 × 600 sebesar
14 KB, bukan foto. `uji/uji_v1.py` menjatuhkan berkas ini ke folder tether sementara
untuk menguji watcher, thumbnail, dan layar tamu. Foto kamera sungguhan 8–25 MB; jangan
pakai ukuran berkas di folder ini untuk memperkirakan kuota.
