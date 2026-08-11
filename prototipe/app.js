(function () {
  'use strict';

  var here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav a').forEach(function (a) {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });

  var KEY = 'mcf-photobooth-state';
  var chan = ('BroadcastChannel' in window) ? new BroadcastChannel('mcf-photobooth') : null;

  function publish(state) {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { }
    if (chan) chan.postMessage(state);
  }
  function readState() {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; }
  }
  function subscribe(fn) {
    if (chan) chan.onmessage = function (e) { fn(e.data); };
    window.addEventListener('storage', function (e) {
      if (e.key === KEY && e.newValue) fn(JSON.parse(e.newValue));
    });
  }

  window.MCF = { publish: publish, readState: readState, subscribe: subscribe };

  var guestWin = null;
  window.MCFbukaTamu = function () {
    guestWin = window.open('tamu.html', 'mcf-tamu', 'width=540,height=960');
    if (guestWin) guestWin.focus();
    return guestWin;
  };
  document.querySelectorAll('[data-buka-tamu]').forEach(function (b) {
    b.addEventListener('click', function () { window.MCFbukaTamu(); });
  });

  var root = document.querySelector('[data-sesi]');
  if (!root) return;

  var SIM = { jeda: 1700, upload: 2600, total: 12, gagalDi: [4, 8] };
  var simulasiGagal = true;

  var sesi = null;
  var foto = [];
  var tick = null, jam = null, urut = 40;

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
    pitaGagal: document.querySelector('[data-pita-gagal]'),
    daftarGagal: document.querySelector('[data-daftar-gagal]'),
    judulGagal: document.querySelector('[data-judul-gagal]'),
    terakhir: document.querySelector('[data-terakhir]'),
    terakhirNama: document.querySelector('[data-terakhir-nama]'),
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
  }

  function hitung() {
    var ok = 0, antre = 0, gagal = 0;
    foto.forEach(function (f) {
      if (f.status === 'ok') ok++; else if (f.status === 'antre') antre++; else gagal++;
    });
    return { ok: ok, antre: antre, gagal: gagal, total: foto.length };
  }

  function umur(ts) {
    var d = Math.round((Date.now() - ts) / 1000);
    if (d < 5) return 'baru saja';
    if (d < 60) return d + ' detik lalu';
    var m = Math.floor(d / 60);
    return m + ' menit lalu';
  }

  function kodeSesi(nama) {
    var t = new Date();
    var p = function (n) { return String(n).padStart(2, '0'); };
    return nama.trim().replace(/[^\wÀ-ÿ]+/g, '_').replace(/^_|_$/g, '') + '_' +
      t.getFullYear() + p(t.getMonth() + 1) + p(t.getDate()) + '_' + p(t.getHours()) + p(t.getMinutes());
  }

  function render() {
    var c = hitung();

    el.nOk.textContent = c.ok;
    el.nAntre.textContent = c.antre;
    el.nGagal.textContent = c.gagal;
    el.jumlahFoto.textContent = c.total + ' foto';
    el.rasio.textContent = c.ok + ' / ' + c.total;

    el.kartuGagal.classList.toggle('counter-bad-live', c.gagal > 0);
    el.kartuGagal.classList.toggle('counter-bad-zero', c.gagal === 0);
    el.kartuGagal.querySelector('[data-chip-gagal]').className =
      'chip ' + (c.gagal > 0 ? 'chip-bad' : 'chip-idle');
    el.kartuGagal.querySelector('[data-chip-gagal]').innerHTML =
      '<span class="dot ' + (c.gagal > 0 ? 'dot-bad' : 'dot-idle') + '"></span> ' +
      (c.gagal > 0 ? 'Perlu tindakan' : 'Tidak ada');
    el.kartuGagal.querySelector('[data-meta-gagal]').textContent =
      c.gagal > 0 ? 'retry otomatis sudah habis' : 'semua percobaan upload berhasil';

    var namaGagal = foto.filter(function (f) { return f.status === 'gagal'; })
      .map(function (f) { return f.nama + '.JPG'; });
    el.pitaGagal.hidden = namaGagal.length === 0;
    if (namaGagal.length) {
      el.judulGagal.textContent = namaGagal.length + ' foto gagal terupload setelah 3 percobaan';
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

    el.grid.innerHTML = foto.slice().reverse().map(function (f) {
      var s = f.status;
      var badge = s === 'ok' ? '<span class="state s-ok">Di Drive</span>'
        : s === 'antre' ? '<span class="state s-wait">Antre</span>' : '';
      var bar = s === 'gagal'
        ? '<button class="retry" type="button" data-retry="' + f.nama + '">' +
        '<svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M15.6 8.2A5.8 5.8 0 1 0 15.9 12" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M16 4.4v3.9h-3.9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '<span class="retry-long">Gagal — coba lagi</span><span class="retry-short">Coba lagi</span></button>'
        : '';
      return '<div class="photo' + (s === 'gagal' ? ' is-bad' : s === 'antre' ? ' is-wait' : '') + '">' +
        '<span class="fill"></span><span class="tag">' + f.nama + '</span>' + badge + bar + '</div>';
    }).join('');

    var last = foto[foto.length - 1];
    if (last) {
      var u = umur(last.masuk);
      el.terakhir.textContent = u === 'baru saja' ? 'Foto terakhir baru saja masuk'
        : 'Foto terakhir masuk ' + u;
      el.terakhirNama.textContent = last.nama + '.JPG';
    } else {
      el.terakhir.textContent = 'Belum ada foto masuk';
      el.terakhirNama.textContent = 'menunggu jepretan pertama';
    }

    if (sesi) {
      var menit = Math.floor((Date.now() - sesi.mulai) / 60000);
      el.durasi.textContent = 'Sesi aktif · berjalan ' + menit + ' menit';
    }

    siarkan();
  }

  function siarkan() {
    if (!sesi) { publish({ tahap: 'sambutan' }); return; }
    var c = hitung();
    publish({
      tahap: root.dataset.tahapAktif === 'selesai' ? 'qr' : 'memotret',
      nama: sesi.nama,
      kode: sesi.kode,
      jumlah: root.dataset.tahapAktif === 'selesai' ? c.ok : c.total,
      foto: foto.map(function (f) { return f.status; })
    });
  }

  function tambahFoto() {
    if (foto.length >= SIM.total) { clearInterval(tick); tick = null; return; }
    urut++;
    var f = { nama: 'IMG_00' + urut, status: 'antre', masuk: Date.now() };
    var idx = foto.length;
    foto.push(f);
    render();
    setTimeout(function () {
      f.status = (simulasiGagal && SIM.gagalDi.indexOf(idx) !== -1) ? 'gagal' : 'ok';
      render();
    }, SIM.upload);
  }

  function mulai() {
    var nama = (el.nama.value || '').trim();
    if (!nama) { el.nama.focus(); return; }
    sesi = { nama: nama, kode: kodeSesi(nama), mulai: Date.now() };
    foto = []; urut = 40;
    el.judul.forEach(function (n) { n.textContent = nama; });
    el.kode.forEach(function (n) { n.textContent = sesi.kode; });
    el.chipSesi.hidden = false;
    tahap('aktif');
    render();
    tick = setInterval(tambahFoto, SIM.jeda);
    tambahFoto();
    jam = setInterval(render, 1000);
  }

  function bukaDialog() {
    var c = hitung();
    var berisiko = (c.antre + c.gagal) > 0;
    el.dialog.querySelectorAll('[data-bentuk]').forEach(function (n) {
      n.hidden = (n.dataset.bentuk !== (berisiko ? 'berisiko' : 'aman'));
    });
    el.dialog.querySelectorAll('[data-d-jumlah]').forEach(function (n) { n.textContent = c.total; });
    el.dialog.querySelectorAll('[data-d-ok]').forEach(function (n) { n.textContent = c.ok; });
    el.dialog.querySelectorAll('[data-d-nama]').forEach(function (n) { n.textContent = sesi.nama; });
    var sisa = c.antre + c.gagal;
    el.dialog.querySelectorAll('[data-d-sisa]').forEach(function (n) { n.textContent = sisa; });
    el.dialog.querySelector('[data-d-daftar]').innerHTML = foto
      .filter(function (f) { return f.status !== 'ok'; })
      .map(function (f) {
        return '<div class="row-between" style="margin-top:8px">' +
          '<span class="small" style="color:var(--bad-strong)">' + f.nama + '.JPG</span>' +
          '<span class="mono" style="color:var(--bad-strong)">' +
          (f.status === 'gagal' ? 'Gagal · 3 percobaan' : 'Masih diupload') + '</span></div>';
      }).join('');
    el.dialog.hidden = false;
    el.dialog.querySelector('.btn-primary').focus();
  }

  function tutupDialog() { el.dialog.hidden = true; el.btnSelesai.focus(); }

  function akhiri() {
    clearInterval(tick); tick = null;
    el.dialog.hidden = true;
    var c = hitung();
    el.qrNama.textContent = sesi.nama;
    el.qrJumlah.textContent = c.ok;
    tahap('selesai');
    siarkan();
  }

  function reset() {
    clearInterval(tick); clearInterval(jam); tick = jam = null;
    sesi = null; foto = []; el.nama.value = '';
    el.chipSesi.hidden = true;
    el.chipUpload.className = 'chip chip-idle';
    el.chipUpload.innerHTML = '<span class="dot dot-idle"></span> Belum ada sesi';
    tahap('idle');
    publish({ tahap: 'sambutan' });
    el.nama.focus();
  }

  el.mulai.addEventListener('click', mulai);
  el.nama.addEventListener('keydown', function (e) { if (e.key === 'Enter') mulai(); });
  el.btnSelesai.addEventListener('click', bukaDialog);
  el.dialog.addEventListener('click', function (e) {
    if (e.target.closest('[data-batal]')) tutupDialog();
    if (e.target.closest('[data-akhiri]')) akhiri();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !el.dialog.hidden) tutupDialog();
  });
  root.addEventListener('click', function (e) {
    var r = e.target.closest('[data-retry]');
    if (r) {
      var f = foto.find(function (x) { return x.nama === r.dataset.retry; });
      if (f) { f.status = 'antre'; render(); setTimeout(function () { f.status = 'ok'; render(); }, 1400); }
    }
    if (e.target.closest('[data-retry-semua]')) {
      foto.filter(function (f) { return f.status === 'gagal'; }).forEach(function (f) {
        f.status = 'antre';
        setTimeout(function () { f.status = 'ok'; render(); }, 1400);
      });
      render();
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

  publish({ tahap: 'sambutan' });
})();
