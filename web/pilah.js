/* Meja pilah dan papan pantau Pet Blessing.
   Meja pilah: admin memilih deretan foto di kotak masuk, mengetik nomor urut,
   lalu menekan Cetak sertifikat. Papan pantau (monitor kedua): daftar sesi dan
   keadaan kotak masuk, tanpa tombol. Keduanya membaca server tiap beberapa detik. */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var PANTAU = document.body.hasAttribute('data-pantau');
  var S = { kamera: [], booth: '', kam: null, pilih: [], terbaik: null, hewan: null, sibuk: false, tanda: {} };

  function el(tag, attrs, anak) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'onclick') n.addEventListener('click', attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (anak || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    return fetch(path, init).catch(function () { throw new Error('Server booth tidak menjawab'); }).then(function (r) {
      return r.text().then(function (t) {
        var d = null;
        try { d = t ? JSON.parse(t) : null; } catch (e) { d = { pesan: t }; }
        if (!r.ok) throw new Error((d && d.pesan) || ('HTTP ' + r.status));
        return d;
      });
    });
  }

  function toast(pesan, jenis) {
    var lama = $('.toast'); if (lama) lama.remove();
    var t = el('div', { class: 'toast' + (jenis ? ' is-' + jenis : ''), role: 'status', text: pesan });
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 4500);
  }

  function chip(kelas, teks) {
    return el('span', { class: 'chip chip-' + kelas }, [el('span', { class: 'dot dot-' + kelas }), teks]);
  }

  if (document.documentElement.hasAttribute('data-pb')) {
    var merek = $('[data-merek]'); if (merek) merek.textContent = 'Pet Blessing 2026';
  }

  /* ============================================================ papan */

  function chipSertifikat(b) {
    if (b.berjalan) return chip('wait', 'Sesi masih berjalan');
    if (!b.sertifikat) return chip('bad', 'Belum ada sertifikat');
    if (b.sertifikat === 'render') return chip('wait', 'Sedang dibuat');
    if (b.sertifikat === 'menunggu') return chip('wait', 'Dibuat, sedang naik ke Drive');
    if (b.sertifikat === 'failed') return chip('bad', 'Gagal dibuat');
    return chip('ok', b.tercatat ? 'Di Drive dan tercatat' : 'Di Drive, pencatatan menyusul');
  }

  function chipFoto(b) {
    if (b.foto_gagal) return chip('bad', b.foto + ' foto, ' + b.foto_gagal + ' gagal naik');
    if (b.foto_drive < b.foto) return chip('wait', b.foto + ' foto, ' + b.foto_drive + ' di Drive');
    return chip('ok', b.foto + ' foto di Drive');
  }

  function gambarPapan(d) {
    var ringkas = $('[data-ringkas]');
    if (ringkas) {
      ringkas.textContent = '';
      if (!d.drive_ok) ringkas.appendChild(chip('bad', 'Drive tidak terjangkau'));
      d.kotak.forEach(function (k) {
        ringkas.appendChild(chip(k.jumlah ? 'wait' : 'ok', 'Camera ' + k.nama + ': ' + k.jumlah + ' foto belum dipilah'));
      });
      if (d.lokal) {
        var antre = d.lokal.pending, gagal = d.lokal.failed;
        ringkas.appendChild(chip(gagal ? 'bad' : (antre ? 'wait' : 'ok'),
          'Laptop ini (Camera ' + d.booth + '): ' + (antre ? antre + ' foto sedang naik ke Drive' : 'semua foto sudah naik ke Drive')
          + (gagal ? ', ' + gagal + ' gagal' : '')));
      }
    }
    var badan = $('[data-papan]');
    if (!badan) return;
    var tanda = JSON.stringify(d.sesi);
    if (S.tanda.papan === tanda) return;
    S.tanda.papan = tanda;
    badan.textContent = '';
    $('[data-papan-kosong]').hidden = d.sesi.length > 0;
    $('[data-papan-jumlah]').textContent = d.sesi.length ? d.sesi.length + ' hewan' : '';
    d.sesi.forEach(function (b, i) {
      var aksi = null;
      if (!PANTAU && b.pilah) {
        aksi = el('button', { class: 'btn btn-sm btn-quiet', type: 'button', text: 'Batalkan' });
        aksi.addEventListener('click', function () { batalkan(b, aksi); });
      }
      badan.appendChild(el('tr', {}, [
        el('td', { class: 'p-urut', text: String(d.sesi.length - i) }),
        el('td', {}, [el('strong', { text: b.label + ' ' + (b.hewan || '') }), el('div', { class: 'small muted', text: (b.pemilik || '') + (b.jenis ? ' · ' + b.jenis : '') })]),
        el('td', { text: b.kamera.filter(Boolean).map(function (k) { return 'Camera ' + k; }).join(', ') }),
        el('td', {}, [chipFoto(b)]),
        el('td', {}, [chipSertifikat(b)]),
        el('td', { class: 'p-folder' }, [b.folder_link ? el('a', { href: b.folder_link, target: '_blank', rel: 'noopener', text: b.folder }) : b.folder]),
        PANTAU ? null : el('td', {}, [aksi]),
      ]));
    });
  }

  function muatPapan() {
    return api('/api/pilah/papan').then(gambarPapan).catch(function (e) {
      var ringkas = $('[data-ringkas]');
      if (ringkas) { ringkas.textContent = ''; ringkas.appendChild(chip('bad', e.message)); }
    });
  }

  function batalkan(b, tombol) {
    if (tombol.dataset.yakin !== '1') {
      tombol.dataset.yakin = '1'; tombol.textContent = 'Yakin batalkan?'; tombol.classList.add('btn-danger-ghost');
      setTimeout(function () { tombol.dataset.yakin = ''; tombol.textContent = 'Batalkan'; tombol.classList.remove('btn-danger-ghost'); }, 4000);
      return;
    }
    tombol.disabled = true; tombol.textContent = 'Membatalkan…';
    api('/api/pilah/batalkan/' + b.id, { method: 'POST' }).then(function (r) {
      toast(b.label + ' ' + (b.hewan || '') + ' dibatalkan, ' + r.dikembalikan + ' foto kembali ke kotak masuk.', 'ok');
      S.tanda = {}; muatPapan(); muatKotak();
    }).catch(function (e) { toast(e.message, 'bad'); tombol.disabled = false; tombol.textContent = 'Batalkan'; });
  }

  if (PANTAU) { muatPapan(); setInterval(muatPapan, 3000); return; }

  /* ====================================================== kotak masuk */

  function kamTerpilih() { return S.kamera.filter(function (k) { return k.nama === S.kam; })[0]; }

  function klikFoto(kam, idx) {
    if (S.sibuk) return;
    if (S.kam !== kam.nama) { S.kam = kam.nama; S.pilih = []; S.terbaik = null; }
    if (idx === S.pilih.length - 1) { S.pilih = []; S.kam = null; S.terbaik = null; }   // klik lagi foto terakhir = lepas
    else S.pilih = kam.berkas.slice(0, idx + 1).map(function (b) { return b.id; });
    if (S.terbaik && S.pilih.indexOf(S.terbaik) < 0) S.terbaik = null;
    gambarKotak(); gambarPanel();
  }

  function gambarKotak() {
    var wadah = $('[data-kotak]');
    var tanda = JSON.stringify([S.kamera, S.kam, S.pilih, S.terbaik]);
    if (S.tanda.kotak === tanda) return;
    S.tanda.kotak = tanda;
    wadah.textContent = '';
    if (!S.kamera.length) {
      wadah.appendChild(el('div', { class: 'card kosong', text: 'Belum ada folder kamera di !Need Organized. Folder muncul sendiri begitu foto pertama masuk.' }));
      return;
    }
    S.kamera.forEach(function (kam) {
      var grid = el('div', { class: 'p-grid' });
      var terbaik = S.terbaik || S.pilih[S.pilih.length - 1];
      kam.berkas.forEach(function (b, i) {
        var ke = S.kam === kam.nama ? S.pilih.indexOf(b.id) : -1;
        var gambar = el('img', { alt: b.nama, loading: 'lazy', src: '/api/pilah/thumb/' + b.id });
        gambar.addEventListener('error', function () {
          // Thumbnail foto dari laptop lain dibuat Drive beberapa detik setelah upload.
          var n = Number(gambar.dataset.coba || 0);
          if (n < 12) setTimeout(function () { gambar.dataset.coba = n + 1; gambar.src = '/api/pilah/thumb/' + b.id + '?coba=' + (n + 1); }, 5000);
        });
        var kotak = el('div', { class: 'p-foto' + (ke >= 0 ? ' is-pilih' : '') + (ke >= 0 && b.id === terbaik ? ' is-terbaik' : ''), title: b.nama }, [
          gambar,
          el('span', { class: 'p-jam', text: b.jam || b.nama }),
          ke >= 0 ? el('span', { class: 'p-no', text: String(ke + 1) }) : null,
        ]);
        kotak.addEventListener('click', function () { klikFoto(kam, i); });
        if (ke >= 0) {
          var bintang = el('button', { class: 'p-bintang', type: 'button', text: b.id === terbaik ? 'Foto sertifikat' : 'Pakai untuk sertifikat' });
          bintang.addEventListener('click', function (ev) { ev.stopPropagation(); S.terbaik = b.id; gambarKotak(); gambarPanel(); });
          kotak.appendChild(bintang);
        }
        grid.appendChild(kotak);
      });
      wadah.appendChild(el('section', { class: 'card p-kamera' }, [
        el('div', { class: 'p-kepala' }, [
          el('h2', { class: 'h2', text: 'Camera ' + kam.nama }),
          chip(kam.berkas.length ? 'wait' : 'ok', kam.berkas.length ? kam.berkas.length + ' foto belum dipilah' : 'kosong, semua sudah dipilah'),
          kam.nama === S.booth ? el('span', { class: 'small muted', text: 'kamera laptop ini' }) : null,
        ]),
        kam.berkas.length ? grid : el('p', { class: 'small muted', text: 'Foto baru muncul di sini beberapa detik setelah dijepret.' }),
      ]));
    });
  }

  function muatKotak() {
    if (S.sibuk) return Promise.resolve();
    return api('/api/pilah/kotak').then(function (d) {
      var ada = {};
      d.kamera.forEach(function (k) { k.berkas.forEach(function (b) { ada[b.id] = 1; }); });
      S.booth = d.booth; S.kamera = d.kamera;
      S.pilih = S.pilih.filter(function (id) { return ada[id]; });
      if (!S.pilih.length) { S.kam = null; S.terbaik = null; }
      gambarKotak(); gambarPanel();
    }).catch(function () { /* papan sudah menampilkan galatnya */ });
  }

  /* ============================================================ panel */

  var e = { cari: $('#cariHewan'), hasil: $('[data-hasil]'), petunjuk: $('[data-petunjuk]'), terpilih: $('[data-terpilih]'),
            foto: $('[data-foto-terpilih]'), cetak: $('[data-cetak]'), sisih: $('[data-sisih]'), alasan: $('[data-alasan]') };

  function gambarPanel() {
    var kam = kamTerpilih(), n = S.pilih.length;
    if (n && kam) {
      var pertama = kam.berkas[0], akhir = kam.berkas[n - 1];
      e.foto.textContent = n + ' foto dari Camera ' + kam.nama + (pertama.jam ? ' (' + pertama.jam + (n > 1 ? ' sampai ' + akhir.jam : '') + ')' : '');
    } else e.foto.textContent = 'Belum ada foto dipilih. Klik foto terakhir milik hewan ini, semua foto sebelumnya ikut terpilih.';
    e.foto.className = n ? 'p-info is-isi' : 'p-info';
    if (S.hewan) {
      e.terpilih.hidden = false;
      e.terpilih.textContent = '';
      e.terpilih.appendChild(el('strong', { text: S.hewan.label + ' ' + S.hewan.nama + (S.hewan.jenis ? ' (' + S.hewan.jenis + ')' : '') }));
      e.terpilih.appendChild(el('div', { class: 'small', text: S.hewan.pemilik + (S.hewan.sudah ? ' · sudah punya sertifikat, akan diganti yang baru' : '') }));
    } else e.terpilih.hidden = true;
    var alasan = S.sibuk ? 'Sedang diproses…' : !n ? 'Pilih fotonya dulu.' : !S.hewan ? 'Ketik nomor urut lalu pilih hewannya.' : '';
    e.cetak.disabled = !!alasan; e.sisih.disabled = S.sibuk || !n;
    e.alasan.textContent = alasan;
    e.cetak.textContent = S.sibuk ? 'Memproses…' : (S.hewan && n ? 'Cetak sertifikat ' + S.hewan.label : 'Cetak sertifikat');
  }

  function pilihHewan(o, h) {
    S.hewan = { owner_id: o.id, pet_id: h.id, label: h.label, nama: h.nama, jenis: h.jenis, pemilik: o.nama, sudah: h.sudah };
    gambarHasil(S.terakhirCari); gambarPanel();
  }

  function gambarHasil(d) {
    e.hasil.textContent = '';
    if (!d) return;
    S.terakhirCari = d;
    if (!d.hasil.length) { e.petunjuk.textContent = 'Tidak ketemu. Periksa nomornya, atau ketik nama pemilik.'; return; }
    e.petunjuk.textContent = d.dari_salinan ? 'Server pendaftaran tidak terjangkau, memakai salinan terakhir.' : '';
    d.hasil.forEach(function (o) {
      var hewan = el('div', { class: 'p-hewan' });
      if (!o.nomor) hewan.appendChild(el('p', { class: 'small bad-text', text: 'Belum reg ulang, belum punya nomor urut.' }));
      o.hewan.forEach(function (h) {
        var aktif = S.hewan && S.hewan.pet_id === h.id;
        var t = el('button', { class: 'btn' + (aktif ? ' btn-primary' : ''), type: 'button' }, [
          el('span', { text: (h.label || h.huruf) + ' ' + h.nama }), el('span', { class: 'p-jenis', text: (h.jenis || '') + (h.sudah ? ' · sudah ada' : '') })]);
        if (!o.nomor) t.disabled = true;
        t.addEventListener('click', function () { pilihHewan(o, h); });
        hewan.appendChild(t);
      });
      e.hasil.appendChild(el('div', { class: 'p-pemilik' }, [
        el('div', { class: 'small' }, [el('strong', { text: (o.nomor ? String(o.nomor).padStart(3, '0') + ' ' : '') + o.nama }), o.uji ? ' (data uji)' : '']), hewan]));
    });
  }

  var tunda = null, urutCari = 0;
  function cari() {
    var q = e.cari.value.trim(), urut = ++urutCari;
    if (!q) { e.hasil.textContent = ''; e.petunjuk.textContent = ''; return; }
    api('/api/pilah/cari?q=' + encodeURIComponent(q)).then(function (d) {
      if (urut !== urutCari) return;
      gambarHasil(d);
      if (d.huruf && d.hasil.length === 1 && d.hasil[0].nomor) {
        var h = d.hasil[0].hewan.filter(function (x) { return x.huruf === d.huruf; })[0];
        if (h) pilihHewan(d.hasil[0], h);
      } else if (d.hasil.length === 1 && d.hasil[0].nomor && d.hasil[0].hewan.length === 1) pilihHewan(d.hasil[0], d.hasil[0].hewan[0]);
    }).catch(function (err) { if (urut === urutCari) e.petunjuk.textContent = err.message; });
  }
  e.cari.addEventListener('input', function () { S.hewan = null; gambarPanel(); clearTimeout(tunda); tunda = setTimeout(cari, 250); });
  e.cari.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { clearTimeout(tunda); cari(); } });

  function kerjakan(path, body, pesan) {
    S.sibuk = true; gambarPanel();
    return api(path, { method: 'POST', body: body }).then(function (r) {
      toast(pesan(r), r.gagal && r.gagal.length ? 'bad' : 'ok');
      S.pilih = []; S.kam = null; S.terbaik = null; S.hewan = null; S.terakhirCari = null;
      e.cari.value = ''; e.hasil.textContent = ''; e.petunjuk.textContent = '';
    }).catch(function (err) { toast(err.message, 'bad'); }).then(function () {
      S.sibuk = false; S.tanda = {};
      return Promise.all([muatKotak(), muatPapan()]);
    }).then(function () { gambarPanel(); e.cari.focus(); });
  }

  e.cetak.addEventListener('click', function () {
    if (e.cetak.disabled || !S.hewan || !S.pilih.length) return;
    var h = S.hewan;
    kerjakan('/api/pilah/tetapkan', { file_ids: S.pilih, owner_id: h.owner_id, pet_id: h.pet_id, terbaik: S.terbaik || S.pilih[S.pilih.length - 1] },
      function (r) {
        return h.label + ' ' + h.nama + ': ' + r.dipindah + ' foto masuk foldernya'
          + (r.sertifikat ? ', sertifikat sedang dibuat.' : ', tapi sertifikat TIDAK dibuat (foto pilihan tidak terbaca).')
          + (r.gagal.length ? ' ' + r.gagal.length + ' foto gagal dipindah dan masih di kotak masuk.' : '');
      });
  });

  e.sisih.addEventListener('click', function () {
    if (e.sisih.disabled || !S.pilih.length) return;
    if (e.sisih.dataset.yakin !== '1') {
      e.sisih.dataset.yakin = '1'; e.sisih.textContent = 'Yakin sisihkan ' + S.pilih.length + ' foto?';
      setTimeout(function () { e.sisih.dataset.yakin = ''; e.sisih.textContent = 'Sisihkan foto terpilih'; }, 4000);
      return;
    }
    e.sisih.dataset.yakin = ''; e.sisih.textContent = 'Sisihkan foto terpilih';
    kerjakan('/api/pilah/sisihkan', { file_ids: S.pilih }, function (r) { return r.disisihkan + ' foto dipindah ke folder Disisihkan.'; });
  });

  gambarPanel();
  muatKotak(); muatPapan();
  setInterval(muatKotak, 4000);
  setInterval(muatPapan, 4000);
})();
