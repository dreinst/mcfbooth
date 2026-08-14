(function () {
  'use strict';

  var here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav a').forEach(function (a) {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });

  var KEY = 'mcf-photobooth-state';
  var chan = ('BroadcastChannel' in window) ? new BroadcastChannel('mcf-photobooth') : null;

  /* Stempel waktu ikut disiarkan supaya layar tamu bisa menolak keadaan basi.
     Tanpa itu, membuka tamu.html keesokan harinya menampilkan nama tamu acara
     kemarin di monitor publik sampai ada yang memulai sesi baru. */
  function publish(state) {
    state.ts = Date.now();
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { }
    if (chan) chan.postMessage(state);
  }

  function readState() {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; }
  }

  /* Satu saluran saja. Mendaftar ke BroadcastChannel dan event storage
     sekaligus membuat tiap publish() sampai dua kali di jendela lain.
     Pesan tanpa `tahap` (ping/pong denyut nadi) tidak diteruskan — kalau
     lolos, layar tamu mematikan semua variannya dan jadi kosong. */
  function subscribe(fn) {
    function teruskan(s) { if (s && s.tahap) fn(s); }
    if (chan) {
      chan.addEventListener('message', function (e) { teruskan(e.data); });
    } else {
      window.addEventListener('storage', function (e) {
        if (e.key === KEY && e.newValue) teruskan(JSON.parse(e.newValue));
      });
    }
  }

  window.MCF = { publish: publish, readState: readState, subscribe: subscribe };

  /* ------------------------------------------------ denyut nadi layar tamu
     Chip "Layar tamu terhubung" dulu berupa teks tetap — hijau meski jendela
     tamu belum pernah dibuka. Sekarang operator mengirim ping tiap 2 detik dan
     layar tamu menjawabnya.

     Cermin di dalam iframe sengaja tidak menjawab: kalau ikut menjawab, chip
     menyala hanya karena halaman operator memuat cuplikannya sendiri. */
  var DI_IFRAME = (window.self !== window.top);

  if (chan && document.querySelector('.guest') && !DI_IFRAME) {
    chan.addEventListener('message', function (e) {
      if (e.data && e.data.ping) chan.postMessage({ pong: 1 });
    });
  }

  var chipTamu = document.querySelectorAll('[data-chip-tamu]');
  var healthTamu = document.querySelectorAll('[data-health-tamu]');
  var healthTamuDot = document.querySelectorAll('[data-health-tamu-dot]');
  var pongTerakhir = 0;

  function tamuHidup() { return (Date.now() - pongTerakhir) < 5000; }

  function gambarChipTamu() {
    var hidup = tamuHidup();
    chipTamu.forEach(function (c) {
      var pendek = c.dataset.chipTamu === 'pendek';
      c.className = 'chip ' + (hidup ? 'chip-ok' : 'chip-idle');
      c.innerHTML = '<span class="dot ' + (hidup ? 'dot-ok' : 'dot-idle') + '"></span> ' +
        (hidup ? (pendek ? 'Terhubung' : 'Layar tamu terhubung')
               : (pendek ? 'Belum dibuka' : 'Layar tamu belum dibuka'));
    });
    /* Baris sidebar ikut dibetulkan. Dulu tertulis "terhubung" apa adanya —
       satu layar bisa menampilkan chip "belum dibuka" di atas dan sidebar
       "terhubung" di bawahnya sekaligus. */
    healthTamu.forEach(function (v) { v.textContent = hidup ? 'terhubung' : 'belum dibuka'; });
    healthTamuDot.forEach(function (d) { d.className = 'dot ' + (hidup ? 'dot-ok' : 'dot-idle'); });
  }

  if ((chipTamu.length || healthTamu.length) && chan) {
    chan.addEventListener('message', function (e) {
      if (e.data && e.data.pong) { pongTerakhir = Date.now(); gambarChipTamu(); }
    });
    gambarChipTamu();
    setInterval(function () { chan.postMessage({ ping: 1 }); gambarChipTamu(); }, 2000);
  }

  /* ---------------------------------------------------- jendela layar tamu */

  window.MCFbukaTamu = function () {
    var w = window.open('tamu.html', 'mcf-tamu', 'width=540,height=960');
    if (w) w.focus();
    return w;
  };

  document.querySelectorAll('[data-buka-tamu]').forEach(function (b) {
    b.addEventListener('click', function () {
      var w = window.MCFbukaTamu();
      /* window.open mengembalikan null saat diblokir. Sebelumnya nilainya
         dibuang: operator menekan tombol terpenting saat menyetel venue,
         tidak terjadi apa-apa, dan tidak ada penjelasan. */
      var pesan = b.parentNode.querySelector('[data-popup-blokir]');
      if (!pesan) {
        pesan = document.createElement('p');
        pesan.className = 'btn-reason';
        pesan.setAttribute('data-popup-blokir', '');
        pesan.textContent = 'Browser memblokir jendela baru. Izinkan popup untuk alamat ini, lalu tekan tombol ini lagi.';
        b.parentNode.insertBefore(pesan, b.nextSibling);
      }
      pesan.hidden = !!w;
    });
  });

  /* Dulu berupa onclick inline di layar-tamu.html — satu-satunya di seluruh
     proyek, dan yang pertama pecah begitu FastAPI memasang CSP di langkah 4. */
  document.querySelectorAll('[data-muat-cuplikan]').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.mirror iframe').forEach(function (f) {
        f.contentWindow.location.reload();
      });
    });
  });

  /* -------------------------------------------------------- salin ke papan klip */

  var TAUTAN_FOLDER = 'https://drive.google.com/drive/folders/1aQ7vKp9XmR2LdT4';

  document.querySelectorAll('[data-salin]').forEach(function (b) {
    b.addEventListener('click', function () {
      var semula = b.dataset.teksSemula || b.textContent;
      b.dataset.teksSemula = semula;
      var janji = (navigator.clipboard && navigator.clipboard.writeText)
        ? navigator.clipboard.writeText(TAUTAN_FOLDER)
        : Promise.reject();
      janji.then(function () {
        b.textContent = 'Tersalin';
      }, function () {
        /* clipboard butuh konteks aman: dari HP lewat IP LAN (http) API-nya
           tidak ada sama sekali. */
        b.textContent = 'Tidak bisa menyalin';
      }).then(function () {
        setTimeout(function () { b.textContent = semula; }, 1800);
      });
    });
  });

  /* ========================================================== halaman Sesi */

  var root = document.querySelector('[data-sesi]');
  if (!root) return;

  var SIM = { jeda: 1700, upload: 2600, retry: 1400, total: 12, gagalDi: [4, 8] };
  var AMBANG_WAIT = 90, AMBANG_BAD = 180;   // detik sejak foto terakhir masuk

  var simulasiGagal = true;

  var sesi = null;
  var foto = [];
  var tick = null, jam = null, urut = 40;

  /* Semua setTimeout simulasi dicatat supaya Reset benar-benar bersih.
     Sebelumnya handle-nya dibuang, jadi timer sesi lama tetap menyala dan
     tetap memanggil render() setelah sesinya dibuang. */
  var timers = [];
  function jadwalkan(fn, ms) { timers.push(setTimeout(fn, ms)); }
  function bersihkanTimer() { timers.forEach(clearTimeout); timers = []; }
  function hentikanInterval() { clearInterval(tick); clearInterval(jam); tick = jam = null; }

  var el = {
    tahap: root.querySelectorAll('[data-tahap]'),
    nama: document.getElementById('inputNama'),
    mulai: document.getElementById('btnMulai'),
    judul: document.querySelectorAll('[data-nama-tamu]'),
    kode: document.querySelectorAll('[data-kode-sesi]'),
    durasi: document.querySelector('[data-durasi]'),
    nOk: document.querySelector('[data-n-ok]'),
    nAntre: document.querySelector('[data-n-antre]'),
    nGagal: document.querySelector('[data-n-gagal]'),
    kartuGagal: document.querySelector('[data-kartu-gagal]'),
    kartuTerakhir: document.querySelector('[data-kartu-terakhir]'),
    chipTerakhir: document.querySelector('[data-chip-terakhir]'),
    nTerakhir: document.querySelector('[data-n-terakhir]'),
    labelTerakhir: document.querySelector('[data-label-terakhir]'),
    metaTerakhir: document.querySelector('[data-meta-terakhir]'),
    pitaGagal: document.querySelector('[data-pita-gagal]'),
    daftarGagal: document.querySelector('[data-daftar-gagal]'),
    judulGagal: document.querySelector('[data-judul-gagal]'),
    meter: document.querySelector('[data-meter]'),
    rasio: document.querySelector('[data-rasio]'),
    grid: document.querySelector('[data-grid]'),
    jumlahFoto: document.querySelector('[data-jumlah-foto]'),
    chipSesi: document.querySelector('[data-chip-sesi]'),
    chipUpload: document.querySelector('[data-chip-upload]'),
    dialog: document.getElementById('dialogSelesai'),
    btnSelesai: document.getElementById('btnSelesai'),
    qrNama: document.querySelector('[data-qr-nama]'),
    qrJumlah: document.querySelector('[data-qr-jumlah]')
  };

  function tahap(nama) {
    el.tahap.forEach(function (n) { n.hidden = (n.dataset.tahap !== nama); });
    root.dataset.tahapAktif = nama;
    /* Cermin di tahap yang belum tampil tidak dimuat. Iframe display:none
       tetap mengunduh dan menjalankan halamannya — halaman operator dulu
       menjalankan tiga salinan aplikasi sekaligus. */
    var f = root.querySelector('[data-tahap="' + nama + '"] iframe[data-src]');
    if (f) { f.src = f.dataset.src; f.removeAttribute('data-src'); }
  }

  function hitung() {
    var ok = 0, antre = 0, gagal = 0;
    foto.forEach(function (f) {
      if (f.status === 'ok') ok++;
      else if (f.status === 'antre') antre++;
      else if (f.status === 'gagal') gagal++;
    });
    return { ok: ok, antre: antre, gagal: gagal, total: foto.length };
  }

  /* \w hanya ASCII. Nama CJK atau ber-emoji dulu menyusut jadi string kosong,
     jadi kodenya kehilangan nama sama sekali — padahal nama itulah satu-satunya
     cara mencari sesi kalau QR-nya hilang. \p{L} mencakup semua huruf.

     Detik ikut masuk. Arsitektur §3.3 menaruh `session_code` sebagai TEXT UNIQUE,
     jadi presisi menit berarti dua tamu bernama sama yang mulai dalam menit yang
     sama menghasilkan kode identik — INSERT-nya ditolak dan sesi kedua gagal
     dibuat. Sesi photobooth itu beruntun; dua "Budi" dalam 60 detik bukan kasus
     aneh. Dengan detik, tabrakan butuh dua sesi di detik yang sama persis. */
  function kodeSesi(nama) {
    var t = new Date();
    var p = function (n) { return String(n).padStart(2, '0'); };
    var slug = nama.trim().replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '');
    if (!slug) slug = 'Tamu';
    return slug + '_' + t.getFullYear() + p(t.getMonth() + 1) + p(t.getDate()) +
      '_' + p(t.getHours()) + p(t.getMinutes()) + p(t.getSeconds());
  }

  /* ------------------------------------------------------------- penanda waktu
     Dipanggil tiap detik. Sengaja tidak menyentuh grid foto: menulis ulang
     innerHTML grid tiap detik menghancurkan fokus papan ketik di tombol
     "Coba lagi" dan, di produksi, memuat ulang tiap thumbnail 60x per menit. */

  var KEADAAN_TERAKHIR = {
    idle: ['chip-idle', 'dot-idle', 'Menunggu'],
    ok: ['chip-ok', 'dot-live', 'Mengalir'],
    wait: ['chip-wait', 'dot-wait', 'Periksa kamera'],
    bad: ['chip-bad', 'dot-bad', 'Tethering putus?']
  };

  function setKeadaanTerakhir(k) {
    var t = KEADAAN_TERAKHIR[k];
    el.kartuTerakhir.className = 'counter counter-terakhir is-' + k;
    el.chipTerakhir.className = 'chip ' + t[0];
    el.chipTerakhir.innerHTML = '<span class="dot ' + t[1] + '"></span> ' + t[2];
  }

  function renderWaktu() {
    if (sesi) {
      var menit = Math.floor((Date.now() - sesi.mulai) / 60000);
      el.durasi.textContent = menit < 1
        ? 'Sesi aktif · baru dimulai'
        : 'Sesi aktif · berjalan ' + menit + ' menit';
    }

    var last = foto[foto.length - 1];
    if (!last) {
      el.nTerakhir.textContent = '—';
      el.labelTerakhir.textContent = 'Belum ada foto masuk';
      el.metaTerakhir.textContent = 'menunggu jepretan pertama';
      setKeadaanTerakhir('idle');
      return;
    }

    var detik = Math.max(0, Math.round((Date.now() - last.masuk) / 1000));
    if (detik < 60) {
      el.nTerakhir.textContent = detik;
      el.labelTerakhir.textContent = 'detik sejak foto terakhir';
    } else {
      el.nTerakhir.textContent = Math.floor(detik / 60);
      el.labelTerakhir.textContent = 'menit sejak foto terakhir';
    }

    var k = detik >= AMBANG_BAD ? 'bad' : detik >= AMBANG_WAIT ? 'wait' : 'ok';
    el.metaTerakhir.textContent = k === 'ok'
      ? last.nama
      : 'kalau kamu baru menjepret, periksa kabel kamera';
    setKeadaanTerakhir(k);
  }

  /* ------------------------------------------------------------------ render
     Dipanggil hanya saat keadaan berubah — foto masuk, status berpindah,
     tahap berganti. Bukan tiap detik. */

  function render() {
    var c = hitung();

    el.nOk.textContent = c.ok;
    el.nAntre.textContent = c.antre;
    el.nGagal.textContent = c.gagal;
    el.jumlahFoto.textContent = c.total + ' foto';
    el.rasio.textContent = c.ok + ' / ' + c.total;

    el.kartuGagal.className = 'counter ' + (c.gagal > 0 ? 'counter-bad-live' : 'counter-bad-zero');
    el.kartuGagal.querySelector('[data-chip-gagal]').className =
      'chip ' + (c.gagal > 0 ? 'chip-bad' : 'chip-idle');
    el.kartuGagal.querySelector('[data-chip-gagal]').innerHTML =
      '<span class="dot ' + (c.gagal > 0 ? 'dot-bad' : 'dot-idle') + '"></span> ' +
      (c.gagal > 0 ? 'Perlu tindakan' : 'Tidak ada');
    el.kartuGagal.querySelector('[data-meta-gagal]').textContent =
      c.gagal > 0 ? 'retry otomatis sudah habis' : 'semua percobaan upload berhasil';

    var namaGagal = foto.filter(function (f) { return f.status === 'gagal'; })
      .map(function (f) { return f.nama; });
    el.pitaGagal.hidden = namaGagal.length === 0;
    if (namaGagal.length) {
      el.judulGagal.textContent = namaGagal.length === 1
        ? '1 foto gagal terupload setelah 3 percobaan'
        : namaGagal.length + ' foto gagal terupload setelah 3 percobaan';
      el.daftarGagal.textContent = namaGagal.join(' · ');
    }

    el.chipUpload.className = 'chip ' + (c.gagal > 0 ? 'chip-bad' : 'chip-idle');
    el.chipUpload.innerHTML = c.gagal > 0
      ? '<span class="dot dot-bad"></span> ' + c.gagal + ' gagal'
      : '<span class="dot dot-ok"></span> Upload lancar';

    var pOk = c.total ? (c.ok / c.total * 100) : 0;
    var pAntre = c.total ? (c.antre / c.total * 100) : 0;
    var pGagal = c.total ? (c.gagal / c.total * 100) : 0;
    el.meter.innerHTML =
      '<span class="m-ok" style="width:' + pOk + '%"></span>' +
      '<span class="m-wait" style="width:' + pAntre + '%"></span>' +
      '<span class="m-bad" style="width:' + pGagal + '%"></span>';

    gambarGrid();
    renderWaktu();

    /* Jumlah di layar QR ikut dihitung ulang. Dulu dibekukan sekali di
       akhiri(), sementara foto yang masih antre tetap menaikkan hitungan yang
       disiarkan ke monitor tamu — layar operator dan monitor tamu bisa
       menampilkan angka berbeda persis di jalur "Tetap tampilkan QR". */
    if (sesi && root.dataset.tahapAktif === 'selesai') {
      el.qrNama.textContent = sesi.nama;
      el.qrJumlah.textContent = c.ok;
    }

    /* Dialog yang sedang terbuka ikut diperbarui. Kalau bentuknya berganti —
       foto baru masuk saat operator membaca, atau antrean akhirnya bersih —
       fokus dipindahkan ke tombol utama bentuk yang baru. */
    if (sesi && el.dialog.open && isiDialog()) fokuskanUtama();

    siarkan();
  }

  var petak = {};   // nama foto -> { el, status }

  function kelasFoto(s) {
    return 'photo' + (s === 'gagal' ? ' is-bad' : s === 'antre' ? ' is-wait' : '');
  }

  /* Nama berkas tidak pernah dirangkai ke innerHTML. Di prototipe namanya
     buatan sendiri (IMG_00xx) jadi aman, tapi di langkah 3 nama itu datang dari
     nama berkas di disk — dan yang menulisnya adalah digiCamControl, bukan kode
     ini. Petaknya dicetak dari markup tetap, namanya dipasang setelahnya. */
  function isiFoto(f) {
    var s = f.status;
    var badge = s === 'ok' ? '<span class="state s-ok">Di Drive</span>'
      : s === 'antre' ? '<span class="state s-wait">Antre</span>' : '';
    var bar = s === 'gagal'
      ? '<button class="retry" type="button" data-retry>' +
      '<svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M15.6 8.2A5.8 5.8 0 1 0 15.9 12" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M16 4.4v3.9h-3.9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '<span class="retry-long">Gagal — coba lagi</span><span class="retry-short">Coba lagi</span></button>'
      : '';
    return '<span class="fill"></span><span class="tag"></span>' + badge + bar;
  }

  function pasangNamaFoto(node, f) {
    node.querySelector('.tag').textContent = f.nama;
    var fill = node.querySelector('.fill');
    if (fill && sesi) {
      fill.style.backgroundImage = 'url("/api/thumb/' + encodeURIComponent(sesi.kode) + '/' + encodeURIComponent(f.nama) + '")';
    }
    var tombol = node.querySelector('.retry');
    if (tombol) tombol.dataset.retry = f.nama;
  }

  /* Petak digambar sekali lalu ditambal satu per satu. Menulis ulang seluruh
     grid tiap ada perubahan menghancurkan fokus papan ketik di tombol
     "Coba lagi" tiap 1,7 detik — tiap kali foto berikutnya masuk — dan di
     produksi memuat ulang tiap thumbnail yang sudah tampil. */
  function gambarGrid() {
    foto.forEach(function (f) {
      var p = petak[f.nama];

      if (!p) {
        var d = document.createElement('div');
        d.className = kelasFoto(f.status);
        d.innerHTML = isiFoto(f);
        pasangNamaFoto(d, f);
        el.grid.insertBefore(d, el.grid.firstChild);   // terbaru di depan
        petak[f.nama] = { el: d, status: f.status };
        return;
      }

      if (p.status === f.status) return;

      /* Kalau fokus sedang di dalam petak ini, ia dipindahkan ke penggantinya
         alih-alih terlempar ke <body>. */
      var punyaFokus = p.el.contains(document.activeElement);
      p.el.className = kelasFoto(f.status);
      p.el.innerHTML = isiFoto(f);
      pasangNamaFoto(p.el, f);
      p.status = f.status;

      if (punyaFokus) {
        var tombol = p.el.querySelector('.retry');
        if (tombol) tombol.focus();
        else { p.el.tabIndex = -1; p.el.focus(); }
      }
    });
  }

  function kosongkanGrid() { petak = {}; el.grid.innerHTML = ''; }

  /* Daftar status per foto dulu ikut disiarkan dan tidak pernah dipakai —
     tamu.html menggambar petaknya dari hitungan saja. Membiarkannya di sana
     mengundang orang memakainya, dan design.md §5.2 melarang persis itu:
     antre dan gagal adalah urusan operator, tamu yang membaca "2 gagal" tidak
     punya apa pun untuk dilakukan selain cemas. */
  function siarkan() {
    if (!sesi) { publish({ tahap: 'sambutan' }); return; }
    var c = hitung();
    publish({
      tahap: root.dataset.tahapAktif === 'selesai' ? 'qr' : 'memotret',
      nama: sesi.nama,
      kode: sesi.kode,
      jumlah: root.dataset.tahapAktif === 'selesai' ? c.ok : c.total
    });
  }

  /* ------------------------------------------------------------ integrasi API nyata */

  function terjemahkanFoto(f_db) {
    var nama_file = f_db.local_path.split('\\').pop().split('/').pop();
    var st = f_db.status === 'pending' ? 'antre' : (f_db.status === 'uploaded' ? 'ok' : 'gagal');
    return { id: f_db.id, nama: nama_file, status: st, masuk: new Date(f_db.created_at).getTime(), percobaan: f_db.retry_count };
  }

  function cobaLagi(f) {
    if (f.status !== 'gagal') return;
    f.status = 'antre';
    render();
    fetch('/api/photos/' + f.id + '/retry', { method: 'POST' });
  }

  function mulai() {
    if (sesi) return;
    var nama = (el.nama.value || '').trim();
    if (!nama) { el.nama.focus(); return; }

    hentikanInterval();
    bersihkanTimer();

    fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guest_name: nama })
    }).then(function(r) { return r.json(); }).then(function(data) {
      sesi = { id: data.id, nama: data.guest_name, kode: data.session_code, mulai: new Date(data.started_at).getTime() };
      foto = []; urut = 40;
      kosongkanGrid();

      el.judul.forEach(function (n) { n.textContent = nama; });
      el.kode.forEach(function (n) { n.textContent = sesi.kode; });
      setChipSesi('jalan');
      tahap('aktif');

      jam = setInterval(renderWaktu, 1000);
      render();
    });
  }

  function setChipSesi(k) {
    if (k === 'off') { el.chipSesi.hidden = true; return; }
    el.chipSesi.hidden = false;
    el.chipSesi.className = 'chip ' + (k === 'jalan' ? 'chip-ok' : 'chip-idle');
    el.chipSesi.innerHTML = k === 'jalan'
      ? '<span class="dot dot-live"></span> Sesi berjalan'
      : '<span class="dot dot-idle"></span> Sesi selesai';
  }

  function akhiri() {
    if (!sesi) return;
    fetch('/api/sessions/' + sesi.id + '/finish', { method: 'POST' }).then(function() {
      hentikanInterval();
      setChipSesi('selesai');
      tahap('selesai');
      render();
      tutupDialog();
    });
  }

  function reset() {
    hentikanInterval();
    bersihkanTimer();
    sesi = null; foto = []; urut = 40;
    kosongkanGrid();
    el.nama.value = '';
    setChipSesi('off');
    tahap('idle');
    render();   // menyapu penghitung, meter, pita gagal, dan menyiarkan 'sambutan'
    /* Setelah render, karena tidak ada foto yang gagal, chip upload berbunyi
       "Upload lancar" — padahal belum ada sesi sama sekali. */
    el.chipUpload.className = 'chip chip-idle';
    el.chipUpload.innerHTML = '<span class="dot dot-idle"></span> Belum ada sesi';
    el.nama.focus();
  }

  /* ----------------------------------------------------------------- dialog
     <dialog> + showModal() memberi focus trap, Esc, dan latar inert secara
     bawaan. Overlay <div> sebelumnya tidak punya satu pun: Tab keluar dari
     dialog ke sidebar di belakangnya, persis di keputusan paling berisiko
     dalam aplikasi ini. */

  /* Isi dialog ikut diperbarui selama ia terbuka. Sebelumnya isinya dibekukan
     saat dibuka: foto yang berpindah dari "antre" ke "gagal" sementara operator
     membaca tetap tertulis "masih diupload" — padahal seluruh keputusan di
     dialog ini bergantung pada beda keduanya. Yang antre menyusul sendiri,
     yang gagal tidak pernah. */
  function isiDialog() {
    var c = hitung();
    var bentuk = (c.antre + c.gagal) > 0 ? 'berisiko' : 'aman';
    var berubah = !!el.dialog.dataset.bentukAktif && el.dialog.dataset.bentukAktif !== bentuk;
    el.dialog.dataset.bentukAktif = bentuk;

    el.dialog.querySelectorAll('[data-bentuk]').forEach(function (n) {
      n.hidden = (n.dataset.bentuk !== bentuk);
    });
    el.dialog.querySelectorAll('[data-d-jumlah]').forEach(function (n) { n.textContent = c.total; });
    el.dialog.querySelectorAll('[data-d-ok]').forEach(function (n) { n.textContent = c.ok; });
    el.dialog.querySelectorAll('[data-d-nama]').forEach(function (n) { n.textContent = sesi.nama; });
    el.dialog.querySelectorAll('[data-d-sisa]').forEach(function (n) {
      n.textContent = c.antre + c.gagal;
    });

    /* Baris ini dulu tertulis "terhubung" apa adanya. Kalau monitor kedua
       ternyata mati, dialog justru meyakinkan operator bahwa QR akan tampil. */
    var tamu = el.dialog.querySelector('[data-d-tamu]');
    if (tamu) {
      tamu.textContent = tamuHidup() ? 'terhubung' : 'belum dibuka';
      tamu.style.color = tamuHidup() ? 'var(--ok)' : 'var(--bad)';
    }

    el.dialog.setAttribute('aria-labelledby', bentuk === 'aman' ? 'judulAman' : 'judulBerisiko');

    var daftar = el.dialog.querySelector('[data-d-daftar]');
    daftar.textContent = '';
    foto.filter(function (f) { return f.status !== 'ok'; })
      .forEach(function (f) {
        var baris = document.createElement('div');
        baris.className = 'row-between';
        baris.style.marginTop = '8px';

        var berkas = document.createElement('span');
        berkas.className = 'small';
        berkas.style.color = 'var(--bad-strong)';
        berkas.textContent = f.nama;

        var keadaan = document.createElement('span');
        keadaan.className = 'mono';
        keadaan.style.color = 'var(--bad-strong)';
        keadaan.textContent = f.status === 'gagal' ? 'Gagal · 3 percobaan' : 'Masih diupload';

        baris.appendChild(berkas);
        baris.appendChild(keadaan);
        daftar.appendChild(baris);
      });

    return berubah;
  }

  /* Fokus ke tombol utama varian yang benar-benar tampil. querySelector di
     tingkat dialog selalu mengambil milik varian "aman"; kalau varian itu yang
     tersembunyi, focus() gagal tanpa suara dan fokus tertinggal di tombol
     Selesai di belakang overlay. */
  function fokuskanUtama() {
    var aktif = el.dialog.querySelector('[data-bentuk]:not([hidden])');
    var utama = aktif && aktif.querySelector('.btn-primary');
    if (utama) utama.focus();
  }

  function bukaDialog() {
    delete el.dialog.dataset.bentukAktif;
    isiDialog();
    el.dialog.showModal();
    fokuskanUtama();
  }

  function tutupDialog() { if (el.dialog.open) el.dialog.close(); }

  el.dialog.addEventListener('close', function () {
    var kembali = root.dataset.tahapAktif === 'selesai'
      ? root.querySelector('[data-sesi-baru]')
      : el.btnSelesai;
    if (kembali) kembali.focus();
  });

  /* ---------------------------------------------------------------- ikatan */

  el.mulai.addEventListener('click', mulai);
  el.nama.addEventListener('keydown', function (e) { if (e.key === 'Enter') mulai(); });
  el.btnSelesai.addEventListener('click', bukaDialog);

  el.dialog.addEventListener('click', function (e) {
    if (e.target.closest('[data-batal]')) tutupDialog();
    if (e.target.closest('[data-akhiri]')) akhiri();
  });

  root.addEventListener('click', function (e) {
    var r = e.target.closest('[data-retry]');
    if (r) {
      var f = foto.find(function (x) { return x.nama === r.dataset.retry; });
      if (f) { cobaLagi(f); render(); }
      return;
    }
    if (e.target.closest('[data-retry-semua]')) {
      if (!sesi) return;
      foto.filter(function (f) { return f.status === 'gagal'; }).forEach(function(f) { f.status = 'antre'; });
      render();
      fetch('/api/sessions/' + sesi.id + '/retry-failed', { method: 'POST' });
      return;
    }
    if (e.target.closest('[data-sesi-baru]')) reset();
  });

  document.querySelectorAll('[data-sim-gagal]').forEach(function (b) {
    b.addEventListener('click', function () {
      simulasiGagal = !simulasiGagal;
      b.setAttribute('aria-pressed', String(simulasiGagal));
      b.textContent = simulasiGagal ? 'Simulasi gagal: on' : 'Simulasi gagal: off';
    });
  });
  document.querySelectorAll('[data-reset]').forEach(function (b) {
    b.addEventListener('click', reset);
  });

  var sse = new EventSource('/api/peristiwa');
  sse.onmessage = function(e) {
    var data = JSON.parse(e.data);
    if (data.jenis === 'foto_baru') {
      var f = { id: data.foto_id, nama: data.nama, status: 'antre', masuk: Date.now(), percobaan: 0 };
      foto.push(f);
      render();
    } else if (data.jenis === 'foto_uploaded' || data.jenis === 'foto_gagal') {
      var target = foto.find(function(x) { return x.id === data.foto_id; });
      if (target) {
        target.status = data.jenis === 'foto_uploaded' ? 'ok' : 'gagal';
        render();
      }
    }
  };

  fetch('/api/sessions/active').then(function(r) {
    if(r.ok) return r.json();
    throw new Error('no active');
  }).then(function(data) {
    sesi = { id: data.id, nama: data.guest_name, kode: data.session_code, mulai: new Date(data.started_at).getTime() };
    el.judul.forEach(function (n) { n.textContent = sesi.nama; });
    el.kode.forEach(function (n) { n.textContent = sesi.kode; });
    setChipSesi('jalan');
    tahap('aktif');
    jam = setInterval(renderWaktu, 1000);
    return fetch('/api/sessions/' + sesi.id + '/photos').then(function(r) { return r.json(); });
  }).then(function(fotos) {
    foto = fotos.map(terjemahkanFoto);
    render();
  }).catch(function(e) {
    publish({ tahap: 'sambutan' });
  });

})();
