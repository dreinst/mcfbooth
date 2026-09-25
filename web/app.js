/* MCF Photobooth — tampilan operator dan layar tamu.
   Tanpa framework, tanpa permintaan ke luar. Semua keadaan dibaca dari server
   (design.md §3): jendela operator dan jendela tamu tidak saling mengirim pesan,
   keduanya mengikuti /api/tampilan-tamu dan aliran SSE. */
(function () {
  'use strict';

  /* ================================================================ util */

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).catch(function () {
      var err = new Error('Server tidak menjawab'); err.status = 0; err.body = {}; throw err;
    }).then(function (r) {
      return r.text().then(function (t) {
        var data = null;
        try { data = t ? JSON.parse(t) : null; } catch (e) { data = { pesan: t }; }
        if (!r.ok) {
          var err = new Error((data && data.pesan) || ('HTTP ' + r.status));
          err.status = r.status; err.body = data || {};
          throw err;
        }
        return data;
      });
    });
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];       // hanya untuk markup tetap, tidak pernah data
      else if (k.indexOf('data-') === 0 || k.indexOf('aria-') === 0 || k === 'type' || k === 'href' || k === 'download' || k === 'style' || k === 'title' || k === 'id' || k === 'tabindex' || k === 'role') n.setAttribute(k, attrs[k]);
      else n[k] = attrs[k];
    });
    (children || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  var ICON = {
    ok: '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 10.5l3.2 3.2L15.5 6.5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    bad: '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M6 6l8 8M14 6l-8 8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
    wait: '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 5v5l3 2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10" cy="10" r="7.5" stroke="currentColor" stroke-width="2"/></svg>',
    idle: '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="3" fill="currentColor"/></svg>',
    retry: '<svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M15.6 8.2A5.8 5.8 0 1 0 15.9 12" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M16 4.4v3.9h-3.9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  };

  function toast(pesan, jenis) {
    $$('.toast').forEach(function (t) { t.remove(); });
    var t = el('div', { class: 'toast' + (jenis ? ' is-' + jenis : ''), role: 'status', text: pesan });
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  }

  function setChip(node, kelas, teks, dot) {
    if (!node) return;
    node.className = 'chip ' + kelas;
    node.textContent = '';
    if (dot) node.appendChild(el('span', { class: 'dot ' + dot }));
    node.appendChild(document.createTextNode(teks));
  }

  function setDisabled(btn, nonaktif, alasanEl, alasan) {
    if (!btn) return;
    btn.setAttribute('aria-disabled', nonaktif ? 'true' : 'false');
    if (alasanEl) { alasanEl.textContent = nonaktif && alasan ? alasan : ''; alasanEl.hidden = !(nonaktif && alasan); }
  }
  function nonaktif(btn) { return btn && btn.getAttribute('aria-disabled') === 'true'; }

  function fmtGb(n) { return n == null ? '—' : (Math.round(n * 10) / 10).toLocaleString('id-ID') + ' GB'; }
  function fmtJam(iso) {
    if (!iso) return '—';
    var d = new Date(iso); if (isNaN(d)) return '—';
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
  function fmtTanggal(iso) {
    if (!iso) return '';
    var d = new Date(iso); if (isNaN(d)) return '';
    return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' });
  }
  function detikSejak(iso) { if (!iso) return null; var t = new Date(iso).getTime(); return isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 1000)); }
  function relatif(detik) {
    if (detik == null) return '—';
    if (detik < 5) return 'baru saja';
    if (detik < 60) return detik + ' detik lalu';
    if (detik < 3600) return Math.floor(detik / 60) + ' menit lalu';
    return Math.floor(detik / 3600) + ' jam lalu';
  }
  function durasi(detik) {
    if (detik == null) return '—';
    if (detik < 60) return detik + ' detik';
    if (detik < 3600) return Math.floor(detik / 60) + ' menit';
    return Math.floor(detik / 3600) + ' jam';
  }
  function debounce(fn, ms) { var t; return function () { var a = arguments; clearTimeout(t); t = setTimeout(function () { fn.apply(null, a); }, ms); }; }
  function thumbUrl(kode, f) { return '/api/thumb/' + encodeURIComponent(kode) + '/' + encodeURIComponent(f.thumb || f.nama); }

  /* ============================================================ aliran SSE */

  function Aliran(path) {
    this.path = path; this.handlers = {}; this.terhubung = false; this.terakhir = 0; this.es = null;
    var self = this;
    this.sambung();
    setInterval(function () {
      // Ping datang tiap 25 detik; sunyi 45 detik berarti sambungan mati diam-diam.
      if (self.terhubung && Date.now() - self.terakhir > 45000) self._putus();
    }, 5000);
  }
  Aliran.prototype.on = function (jenis, fn) { (this.handlers[jenis] = this.handlers[jenis] || []).push(fn); return this; };
  Aliran.prototype._emit = function (jenis, data) { (this.handlers[jenis] || []).forEach(function (fn) { try { fn(data); } catch (e) { console.error(e); } }); };
  Aliran.prototype._hidup = function () { this.terakhir = Date.now(); if (!this.terhubung) { this.terhubung = true; this._emit('koneksi', true); } };
  Aliran.prototype._putus = function () { if (this.terhubung) { this.terhubung = false; this._emit('koneksi', false); } };
  Aliran.prototype.sambung = function () {
    var self = this;
    if (this.es) this.es.close();
    var es = this.es = new EventSource(this.path);
    es.addEventListener('halo', function (e) { self._hidup(); var d = {}; try { d = JSON.parse(e.data); } catch (x) {} self._emit('halo', d); self._emit('*', d); });
    es.onmessage = function (e) {
      self._hidup();
      var d = null; try { d = JSON.parse(e.data); } catch (x) { return; }
      if (!d || d.jenis === 'ping') return;
      self._emit(d.jenis, d); self._emit('*', d);
    };
    es.onopen = function () { self._hidup(); };
    es.onerror = function () { self._putus(); };
  };
  Aliran.prototype.sambungUlang = function () { this.sambung(); };

  var HALAMAN_TAMU = !!$('[data-tamu]');
  var PARAM = new URLSearchParams(location.search);
  var CERMIN = PARAM.has('cermin');
  var aliran = new Aliran(HALAMAN_TAMU && !CERMIN ? '/api/peristiwa-tamu' : '/api/peristiwa');

  window.MCF = { api: api, aliran: aliran, toast: toast, preflight: null };

  /* ======================================================= kerangka operator */

  if ($('.sidebar')) {
    var here = location.pathname.split('/').pop() || 'index.html';
    $$('.nav a').forEach(function (a) { if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page'); });

    function gambarKesehatan(pf) {
      var drive = pf.drive || {};
      var vDrive = $('[data-health-drive]'), dDrive = $('[data-health-drive-dot]');
      if (vDrive) {
        if (drive.keadaan === 'terhubung') {
          var sisa = drive.kuota_sisa_gb;
          vDrive.textContent = sisa == null ? 'terhubung' : fmtGb(sisa) + ' sisa';
          var tipis = sisa != null && sisa < 5;
          vDrive.className = 'val' + (tipis ? ' is-wait' : '');
          dDrive.className = 'dot ' + (tipis ? 'dot-wait' : 'dot-ok');
        } else {
          vDrive.textContent = ({ belum_login: 'belum login', token_kedaluwarsa: 'login ulang', tanpa_credentials: 'perlu setup', offline: 'offline' })[drive.keadaan] || 'terputus';
          vDrive.className = 'val is-bad'; dDrive.className = 'dot dot-bad';
        }
      }
      var vNet = $('[data-health-internet]'), dNet = $('[data-health-internet-dot]');
      if (vNet) { vNet.textContent = pf.internet ? 'tersambung' : 'putus'; vNet.className = 'val' + (pf.internet ? '' : ' is-bad'); dNet.className = 'dot ' + (pf.internet ? 'dot-ok' : 'dot-bad'); }
      var vDisk = $('[data-health-disk]'), dDisk = $('[data-health-disk-dot]');
      if (vDisk) { var gb = pf.disk_bebas_gb; vDisk.textContent = fmtGb(gb); var rendah = gb != null && gb < 20; vDisk.className = 'val' + (rendah ? ' is-wait' : ''); dDisk.className = 'dot ' + (rendah ? 'dot-wait' : 'dot-ok'); }
      $$('[data-health-tamu]').forEach(function (v) { v.textContent = pf.layar_tamu ? 'terhubung' : 'belum dibuka'; v.className = v.classList.contains('check-value') ? 'check-value' : 'val'; });
      $$('[data-health-tamu-dot]').forEach(function (d) { d.className = 'dot ' + (pf.layar_tamu ? 'dot-ok' : 'dot-idle'); });
      $$('[data-chip-tamu]').forEach(function (c) {
        var pendek = c.dataset.chipTamu === 'pendek';
        setChip(c, pf.layar_tamu ? 'chip-ok' : 'chip-idle',
          pf.layar_tamu ? (pendek ? 'Terhubung' : 'Layar tamu terhubung') : (pendek ? 'Belum dibuka' : 'Layar tamu belum dibuka'),
          pf.layar_tamu ? 'dot-ok' : 'dot-idle');
      });
    }

    function muatRingkasan() {
      api('/api/sessions/ringkasan').then(function (r) {
        $$('[data-badge-riwayat]').forEach(function (b) { b.textContent = r.total ? String(r.total) : ''; });
        document.dispatchEvent(new CustomEvent('mcf:ringkasan', { detail: r }));
      }).catch(function () {});
    }

    var muatPreflight = window.MCF.muatPreflight = function () {
      return api('/api/preflight').then(function (pf) {
        window.MCF.preflight = pf;
        gambarKesehatan(pf);
        document.dispatchEvent(new CustomEvent('mcf:preflight', { detail: pf }));
        return pf;
      }).catch(function () { return null; });
    };
    muatPreflight(); muatRingkasan();
    setInterval(muatPreflight, 15000);
    setInterval(muatRingkasan, 60000);
    ['sesi_mulai', 'sesi_selesai', 'drive_status', 'layar_tamu', 'sesi_drive_terpasang', 'tampilan_tamu', 'foto_tanpa_sesi'].forEach(function (j) {
      aliran.on(j, function () { muatPreflight(); if (j.indexOf('sesi_') === 0) muatRingkasan(); });
    });

    // Chip server di bilah atas, cermin, dan tombol pengubah keadaan — semua halaman operator (design.md §6).
    var ALASAN_PUTUS = 'Server tidak menjawab. Tunggu tersambung lagi sebelum mengubah apa pun.';
    window.MCF.serverHidup = true;
    aliran.on('koneksi', function (hidup) {
      window.MCF.serverHidup = hidup;
      $$('[data-chip-server]').forEach(function (c) {
        c.hidden = hidup;
        setChip(c, 'chip-bad', 'Terputus dari server', 'dot-bad');
      });
      $$('.mirror').forEach(function (m) {
        m.classList.toggle('mirror-unknown', !hidup);
        m.dataset.pesan = 'Tidak bisa dipastikan — server tidak menjawab. Periksa monitornya langsung.';
      });
      $$('[data-butuh-server]').forEach(function (b) {
        if (!hidup) { b.dataset.alasanSemula = b.getAttribute('aria-disabled') || 'false'; b.setAttribute('aria-disabled', 'true'); }
        else if (b.dataset.alasanSemula !== undefined) { b.setAttribute('aria-disabled', b.dataset.alasanSemula); delete b.dataset.alasanSemula; }
      });
      $$('[data-alasan-server]').forEach(function (p) { p.hidden = hidup; p.textContent = ALASAN_PUTUS; });
      if (hidup) { muatPreflight(); muatRingkasan(); }
    });

    // Buka jendela layar tamu.
    window.MCFbukaTamu = function () {
      var w = window.open('/tamu', 'mcf-tamu', 'width=540,height=960');
      if (w) w.focus();
      return w;
    };
    $$('[data-buka-tamu]').forEach(function (b) {
      b.addEventListener('click', function () {
        var w = window.MCFbukaTamu();
        var pesan = b.parentNode.querySelector('[data-popup-blokir]');
        if (!pesan) {
          pesan = el('p', { class: 'btn-reason', 'data-popup-blokir': '', text: 'Browser memblokir jendela baru. Izinkan popup untuk alamat ini, lalu tekan tombol ini lagi.' });
          b.parentNode.insertBefore(pesan, b.nextSibling);
        }
        pesan.hidden = !!w;
      });
    });
    $$('[data-muat-cuplikan]').forEach(function (b) {
      b.addEventListener('click', function () { $$('.mirror iframe').forEach(function (f) { f.src = f.src; }); });
    });
  }

  function salinTeks(teks) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(teks);
    return Promise.reject(new Error('clipboard tidak tersedia'));
  }
  function ikatSalin(btn, ambilTeks) {
    btn.addEventListener('click', function () {
      var semula = btn.dataset.teksSemula || btn.textContent;
      btn.dataset.teksSemula = semula;
      var teks = ambilTeks();
      if (!teks) { toast('Belum ada tautan untuk disalin.', 'bad'); return; }
      salinTeks(teks).then(function () { btn.textContent = 'Tersalin'; }, function () { btn.textContent = 'Tidak bisa menyalin'; })
        .then(function () { setTimeout(function () { btn.textContent = semula; }, 1800); });
    });
  }

  /* ============================================================== halaman Sesi */

  (function halamanSesi() {
    var root = $('[data-sesi]');
    if (!root) return;

    var AMBANG_WAIT = 90, AMBANG_BAD = 180;
    var sesi = null, foto = [], jam = null, petak = {};
    var pf = null;
    var modePb = false, pilihan = null, pemilikPb = null;

    var e = {
      nama: $('#inputNama'), mulai: $('#btnMulai'), alasanMulai: $('[data-alasan-mulai]'), hintNama: $('[data-hint-nama]'),
      preflight: $('[data-preflight]'), tertinggal: $('[data-tertinggal]'),
      judul: $$('[data-nama-tamu]'), kode: $$('[data-kode-sesi]'), durasi: $('[data-durasi]'),
      nOk: $('[data-n-ok]'), nAntre: $('[data-n-antre]'), nGagal: $('[data-n-gagal]'),
      kartuGagal: $('[data-kartu-gagal]'), kartuTerakhir: $('[data-kartu-terakhir]'), chipTerakhir: $('[data-chip-terakhir]'),
      nTerakhir: $('[data-n-terakhir]'), labelTerakhir: $('[data-label-terakhir]'), metaTerakhir: $('[data-meta-terakhir]'),
      pitaGagal: $('[data-pita-gagal]'), daftarGagal: $('[data-daftar-gagal]'), judulGagal: $('[data-judul-gagal]'),
      pitaDrive: $('[data-pita-drive]'), pitaPutus: $('[data-pita-putus]'), umurPutus: $('[data-umur-putus]'),
      meter: $('[data-meter]'), rasio: $('[data-rasio]'), grid: $('[data-grid]'), gridKosong: $('[data-grid-kosong]'), jumlahFoto: $('[data-jumlah-foto]'),
      chipSesi: $('[data-chip-sesi]'), chipUpload: $('[data-chip-upload]'),
      dialog: $('#dialogSelesai'), btnSelesai: $('#btnSelesai'), alasanSelesai: $('[data-alasan-selesai]'),
      kartuPb: $('[data-kartu-pb]'), kartuNama: $('[data-kartu-nama]'), kodePb: $('#inputKodePb'), hintPb: $('[data-pb-hint]'),
      hasilPb: $('[data-pb-hasil]'), nomorPb: $('[data-pb-nomor]'), pemilikPb: $('[data-pb-pemilik]'), hewanPb: $('[data-pb-hewan]'), alasanPb: $('[data-alasan-pb]'),
      kameraWrap: $('[data-pb-kamera-wrap]'), video: $('[data-pb-video]'),
      kartuSrt: $('[data-kartu-sertifikat]'), chipSrt: $('[data-chip-sertifikat]'), infoSrt: $('[data-sertifikat-info]'), btnSrt: $('[data-buat-sertifikat]'),
      pdfSrt: $('[data-sertifikat-pdf]'), driveSrt: $('[data-sertifikat-drive]'), imgSrt: $('[data-sertifikat-img]'),
      qrNama: $('[data-qr-nama]'), qrJumlah: $('[data-qr-jumlah]'), qrLink: $('[data-qr-link]'), qrImg: $('[data-qr-img]'), qrUnduh: $('[data-qr-unduh]'), qrTanpa: $('[data-qr-tanpa-drive]')
    };

    function tahap(nama) {
      $$('[data-tahap]', root).forEach(function (n) { n.hidden = n.dataset.tahap !== nama; });
      root.dataset.tahapAktif = nama;
      var f = root.querySelector('[data-tahap="' + nama + '"] iframe[data-src]');
      if (f) { f.src = f.dataset.src; f.removeAttribute('data-src'); }
    }

    /* ---- pemeriksaan awal ---- */
    function barisCek(kunci, keadaan, nilai) {
      var li = e.preflight && e.preflight.querySelector('[data-cek="' + kunci + '"]');
      if (!li) return;
      var ikon = li.querySelector('.check-icon'), val = li.querySelector('.check-value');
      ikon.className = 'check-icon is-' + keadaan; ikon.innerHTML = ICON[keadaan] || ICON.idle;
      val.textContent = nilai; val.className = 'check-value' + (keadaan === 'bad' ? ' is-bad' : keadaan === 'wait' ? ' is-wait' : '');
    }
    function gambarPreflight(p) {
      pf = p;
      var d = p.drive || {};
      if (d.keadaan === 'terhubung') barisCek('drive', 'ok', 'terhubung sebagai ' + (d.email || 'akun Drive'));
      else barisCek('drive', p.izinkan_tanpa_drive ? 'wait' : 'bad', d.pesan || 'belum terhubung — login di Pengaturan');
      if (d.kuota_sisa_gb == null) barisCek('kuota', 'idle', d.keadaan === 'terhubung' ? 'tidak dilaporkan Google' : 'menunggu Drive');
      else barisCek('kuota', d.kuota_sisa_gb < 5 ? 'wait' : 'ok', fmtGb(d.kuota_sisa_gb) + ' tersisa dari ' + fmtGb(d.kuota_total_gb) + (d.kuota_sisa_gb < 5 ? ' — cukup untuk ±' + Math.floor(d.kuota_sisa_gb * 80) + ' foto JPEG' : ''));
      if (p.watcher_aktif) barisCek('tether', p.berkas_menunggu ? 'wait' : 'ok', p.tether_folder + (p.berkas_menunggu ? ' — ' + p.berkas_menunggu + ' berkas baru belum masuk sesi mana pun' : ''));
      else barisCek('tether', 'bad', 'pemantau tidak berjalan — ' + p.tether_folder);
      barisCek('internet', p.internet ? 'ok' : 'bad', p.internet ? 'tersambung ke Google' : 'putus — foto tetap diarsipkan, upload menyusul');
      barisCek('disk', p.disk_bebas_gb == null ? 'idle' : p.disk_bebas_gb < 20 ? 'wait' : 'ok', p.disk_bebas_gb == null ? 'tidak terbaca' : fmtGb(p.disk_bebas_gb) + ' bebas di ' + p.archive_folder);
      var t = p.tampilan_tamu || {};
      barisCek('tamu', p.layar_tamu ? 'ok' : 'wait', p.layar_tamu ? 'terbuka, menampilkan ' + ({ sambutan: 'sambutan', memotret: 'sesi ' + (t.nama_tamu || ''), qr: 'QR ' + (t.nama_tamu || '') })[t.keadaan] : 'belum dibuka — QR bisa ditampilkan di laptop ini');

      if (!window.MCF.serverHidup) { setDisabled(e.mulai, true, e.alasanMulai, 'Server tidak menjawab.'); }
      else if (!p.boleh_mulai) { e.alasanMulai.className = 'btn-reason'; setDisabled(e.mulai, true, e.alasanMulai, p.alasan_tidak_boleh); }
      else {
        setDisabled(e.mulai, false, e.alasanMulai, '');
        if (p.peringatan_mulai) { e.alasanMulai.hidden = false; e.alasanMulai.className = 'btn-reason is-wait'; e.alasanMulai.textContent = p.peringatan_mulai; }
      }

      if ((p.mode === 'petblessing') !== modePb) {
        modePb = p.mode === 'petblessing';
        e.kartuPb.hidden = !modePb; e.kartuNama.hidden = modePb;
        if (modePb && root.dataset.tahapAktif === 'idle') e.kodePb.focus();
      }
      if (modePb) {
        var alasanPb = !window.MCF.serverHidup ? 'Server tidak menjawab.' : !p.boleh_mulai ? p.alasan_tidak_boleh
          : !p.pb_siap ? 'Sambungan ke database Pet Blessing belum diatur (PETBLESSING_API_URL dan PETBLESSING_BOOTH_TOKEN di .env).' : '';
        e.alasanPb.textContent = alasanPb; e.alasanPb.hidden = !alasanPb;
        $$('[data-pb-pilih]', e.hewanPb).forEach(function (b) { b.setAttribute('aria-disabled', alasanPb ? 'true' : 'false'); });
      }

      var pitaTanpa = $('[data-pita-tanpa-sesi]');
      if (pitaTanpa) { pitaTanpa.hidden = !p.foto_tanpa_sesi; if (p.foto_tanpa_sesi) $('[data-n-tanpa-sesi]').textContent = String(p.foto_tanpa_sesi); }

      if (p.sesi_aktif && !sesi && root.dataset.tahapAktif === 'idle') gambarTertinggal(p.sesi_aktif);
      else if (!p.sesi_aktif && e.tertinggal) e.tertinggal.hidden = true;
    }
    document.addEventListener('mcf:preflight', function (ev) { gambarPreflight(ev.detail); });
    if (window.MCF.preflight) gambarPreflight(window.MCF.preflight);

    /* ---- sesi tertinggal ---- */
    function gambarTertinggal(s) {
      if (!e.tertinggal) return;
      e.tertinggal.hidden = false;
      $('[data-tt-nama]').textContent = s.guest_name;
      $('[data-tt-info]').textContent = 'dimulai ' + fmtJam(s.started_at) + ' · ' + s.foto.total + ' foto · foto terakhir ' + (s.foto_terakhir_at ? relatif(detikSejak(s.foto_terakhir_at)) : 'belum ada');
      $('[data-tt-lanjut]').onclick = function () { muatSesi(s); };
      $('[data-tt-akhiri]').onclick = function () {
        api('/api/sessions/' + s.id + '/finish', { method: 'POST' }).then(function () { e.tertinggal.hidden = true; toast('Sesi ' + s.guest_name + ' diakhiri.', 'ok'); window.MCF.muatPreflight(); })
          .catch(function (err) { toast(err.message, 'bad'); });
      };
    }

    /* ---- nama serupa ---- */
    var cekNama = debounce(function () {
      var q = (e.nama.value || '').trim();
      if (!q) { e.hintNama.textContent = ''; e.hintNama.className = 'field-hint'; return; }
      api('/api/sessions/nama-serupa?q=' + encodeURIComponent(q)).then(function (r) {
        if (r.jumlah > 0) { e.hintNama.className = 'field-hint is-wait'; e.hintNama.textContent = r.jumlah + ' sesi hari ini sudah memakai nama ini. Tambahkan nomor meja atau pembeda lain supaya mudah dicari di Riwayat.'; }
        else { e.hintNama.className = 'field-hint'; e.hintNama.textContent = ''; }
      }).catch(function () {});
    }, 350);
    e.nama.addEventListener('input', cekNama);
    // Ketikan pertama untuk tamu berikutnya membatalkan tenggang setelah Selesai:
    // jepretan uji tidak boleh masuk ke folder tamu sebelumnya.
    var sudahBersiap = false;
    e.nama.addEventListener('input', function () {
      if (sudahBersiap || !e.nama.value) return;
      sudahBersiap = true; api('/api/sessions/bersiap', { method: 'POST' }).catch(function () {});
    });

    /* ---- hitung & render ---- */
    function hitung() {
      var c = { ok: 0, antre: 0, gagal: 0, total: foto.length };
      foto.forEach(function (f) { if (f.status === 'uploaded') c.ok++; else if (f.status === 'pending') c.antre++; else c.gagal++; });
      return c;
    }
    var KEADAAN_TERAKHIR = { idle: ['chip-idle', 'dot-idle', 'Menunggu'], ok: ['chip-ok', 'dot-live', 'Mengalir'], wait: ['chip-wait', 'dot-wait', 'Periksa kamera'], bad: ['chip-bad', 'dot-bad', 'Tethering putus?'] };
    function setKeadaanTerakhir(k) {
      var t = KEADAAN_TERAKHIR[k];
      e.kartuTerakhir.className = 'counter counter-terakhir is-' + k;
      setChip(e.chipTerakhir, t[0], t[2], t[1]);
    }
    function renderWaktu() {
      if (sesi && e.durasi) {
        var menit = Math.floor((Date.now() - new Date(sesi.started_at).getTime()) / 60000);
        e.durasi.textContent = menit < 1 ? 'Sesi aktif · baru dimulai' : 'Sesi aktif · berjalan ' + menit + ' menit';
      }
      var last = foto[foto.length - 1];
      if (!last) {
        e.nTerakhir.textContent = '—'; e.labelTerakhir.textContent = 'Belum ada foto masuk'; e.metaTerakhir.textContent = 'menunggu jepretan pertama';
        setKeadaanTerakhir('idle'); return;
      }
      var detik = detikSejak(last.created_at) || 0;
      if (detik < 60) { e.nTerakhir.textContent = String(detik); e.labelTerakhir.textContent = 'detik sejak foto terakhir'; }
      else { e.nTerakhir.textContent = String(Math.floor(detik / 60)); e.labelTerakhir.textContent = 'menit sejak foto terakhir'; }
      var k = detik >= AMBANG_BAD ? 'bad' : detik >= AMBANG_WAIT ? 'wait' : 'ok';
      e.metaTerakhir.textContent = k === 'ok' ? last.nama : 'kalau kamu baru menjepret, periksa kabel kamera';
      setKeadaanTerakhir(k);
      if (e.pitaPutus && !e.pitaPutus.hidden && e.umurPutus) e.umurPutus.textContent = durasi(Math.round((Date.now() - aliran.terakhir) / 1000));
    }

    function render() {
      var c = hitung();
      e.nOk.textContent = c.ok; e.nAntre.textContent = c.antre; e.nGagal.textContent = c.gagal;
      e.jumlahFoto.textContent = c.total + ' foto'; e.rasio.textContent = c.ok + ' / ' + c.total;

      e.kartuGagal.className = 'counter ' + (c.gagal > 0 ? 'counter-bad-live' : 'counter-bad-zero');
      setChip(e.kartuGagal.querySelector('[data-chip-gagal]'), c.gagal > 0 ? 'chip-bad' : 'chip-idle', c.gagal > 0 ? 'Perlu tindakan' : 'Tidak ada', c.gagal > 0 ? 'dot-bad' : 'dot-idle');
      e.kartuGagal.querySelector('[data-meta-gagal]').textContent = c.gagal > 0 ? 'retry otomatis sudah habis' : 'semua percobaan upload berhasil';

      var gagal = foto.filter(function (f) { return f.status === 'failed'; });
      e.pitaGagal.hidden = gagal.length === 0;
      if (gagal.length) {
        e.judulGagal.textContent = gagal.length === 1 ? '1 foto gagal terupload setelah 3 percobaan' : gagal.length + ' foto gagal terupload setelah 3 percobaan';
        e.daftarGagal.textContent = gagal.map(function (f) { return f.nama; }).join(' · ');
      }

      if (e.pitaDrive) {
        var tanpaDrive = !!(sesi && !sesi.drive_folder_link);
        e.pitaDrive.hidden = !tanpaDrive;
        if (tanpaDrive) {
          // 30 detik pertama masih wajar: folder dipasang di latar setelah Mulai Sesi.
          var baru = (detikSejak(sesi.started_at) || 0) < 30;
          e.pitaDrive.querySelector('.banner').className = 'banner ' + (baru ? 'banner-accent' : 'banner-wait');
          e.pitaDrive.querySelector('.banner-title').textContent = baru ? 'Menyiapkan folder Drive…' : 'Sesi ini belum punya folder Drive';
          e.pitaDrive.querySelector('.banner-text').textContent = baru
            ? 'Folder dan QR sedang dibuat di latar. Kamu sudah boleh memotret.'
            : 'Drive tidak terjangkau saat sesi dimulai. Foto tetap diarsipkan di laptop dan menunggu. Penjaga latar memasang foldernya begitu Drive tersambung — atau tekan tombol ini.';
        }
      }

      setChip(e.chipUpload, c.gagal > 0 ? 'chip-bad' : c.antre > 0 ? 'chip-wait' : 'chip-idle',
        c.gagal > 0 ? c.gagal + ' gagal' : c.antre > 0 ? c.antre + ' antre' : (sesi ? 'Upload lancar' : 'Belum ada sesi'),
        c.gagal > 0 ? 'dot-bad' : c.antre > 0 ? 'dot-wait' : (sesi ? 'dot-ok' : 'dot-idle'));

      var pOk = c.total ? c.ok / c.total * 100 : 0, pAntre = c.total ? c.antre / c.total * 100 : 0, pGagal = c.total ? c.gagal / c.total * 100 : 0;
      e.meter.innerHTML = '<span class="m-ok" style="width:' + pOk + '%"></span><span class="m-wait" style="width:' + pAntre + '%"></span><span class="m-bad" style="width:' + pGagal + '%"></span>';

      gambarGrid();
      renderWaktu();

      if (sesi && root.dataset.tahapAktif === 'selesai') gambarSelesai(c);
      if (sesi && e.dialog.open && isiDialog()) fokuskanUtama();
    }

    function kelasFoto(s) { return 'photo' + (s === 'failed' ? ' is-bad' : s === 'pending' ? ' is-wait' : ''); }
    function isiPetak(node, f, urutan) {
      node.className = kelasFoto(f.status) + (pilihan === f.id ? ' is-pilih' : '');
      node.dataset.foto = String(f.id);
      node.innerHTML = '<span class="fill"></span>' +
        (urutan ? '<span class="seq mono-plain">#' + String(urutan).padStart(2, '0') + '</span>' : '') +
        '<span class="tag"></span>' +
        (f.status === 'uploaded' ? '<span class="state s-ok">Di Drive</span>' : f.status === 'pending' ? '<span class="state s-wait">Antre</span>' : '') +
        (f.status === 'failed' ? '<button class="retry" type="button" data-retry>' + ICON.retry + '<span class="retry-long">Gagal — coba lagi</span><span class="retry-short">Coba lagi</span></button>' : '');
      node.querySelector('.tag').textContent = f.nama;
      if (sesi && f.thumb) node.querySelector('.fill').style.backgroundImage = 'url("' + thumbUrl(sesi.session_code, f) + '")';
      var tombol = node.querySelector('.retry'); if (tombol) tombol.dataset.retry = String(f.id);
    }
    function gambarGrid() {
      if (e.gridKosong) e.gridKosong.hidden = foto.length > 0;
      foto.forEach(function (f, idx) {
        var p = petak[f.id];
        if (!p) {
          var d = document.createElement('div'); isiPetak(d, f, idx + 1);
          e.grid.insertBefore(d, e.grid.firstChild); petak[f.id] = { el: d, status: f.status, urutan: idx + 1 };
          return;
        }
        if (p.status === f.status) return;
        var punyaFokus = p.el.contains(document.activeElement);
        isiPetak(p.el, f, p.urutan); p.status = f.status;
        if (punyaFokus) { var t = p.el.querySelector('.retry'); if (t) t.focus(); else { p.el.tabIndex = -1; p.el.focus(); } }
      });
    }
    function kosongkanGrid() { petak = {}; e.grid.innerHTML = ''; }

    function gambarSelesai(c) {
      e.qrNama.textContent = sesi.guest_name; e.qrJumlah.textContent = String(c.ok);
      var link = sesi.drive_folder_link;
      e.qrLink.textContent = link ? link.replace(/^https?:\/\//, '') : 'belum ada — Drive tidak terhubung saat sesi dimulai';
      e.qrTanpa.hidden = !!link;
      if (link) {
        e.qrImg.src = '/api/qr/' + encodeURIComponent(sesi.session_code) + '?v=' + Date.now(); e.qrImg.parentNode.hidden = false;
        e.qrUnduh.href = '/api/qr/' + encodeURIComponent(sesi.session_code); e.qrUnduh.setAttribute('download', 'qr-' + sesi.session_code + '.png');
        e.qrUnduh.setAttribute('aria-disabled', 'false'); e.qrUnduh.title = '';
      } else {
        e.qrImg.parentNode.hidden = true;
        e.qrUnduh.removeAttribute('href'); e.qrUnduh.removeAttribute('download');
        e.qrUnduh.setAttribute('aria-disabled', 'true'); e.qrUnduh.title = 'Belum ada QR — pasang folder Drive dulu';
      }
    }

    /* ---- alur ---- */
    function pasangSesi(s) {
      sesi = s;
      e.judul.forEach(function (n) { n.textContent = s.guest_name; });
      e.kode.forEach(function (n) { n.textContent = s.session_code; });
    }
    function muatSesi(s) {
      pasangSesi(s); foto = []; kosongkanGrid();
      pilihan = null; hentikanKamera();
      e.kartuSrt.hidden = !s.pb;
      if (s.pb) { root.setAttribute('data-sesi-pb', ''); gambarSertifikat(null); muatSertifikat(); }
      else root.removeAttribute('data-sesi-pb');
      if (e.tertinggal) e.tertinggal.hidden = true;
      setChip(e.chipSesi, 'chip-ok', 'Sesi berjalan', 'dot-live'); e.chipSesi.hidden = false;
      tahap('aktif');
      clearInterval(jam); jam = setInterval(renderWaktu, 1000);
      return api('/api/sessions/' + s.id + '/photos').then(function (fs) { foto = fs; render(); }).catch(function () { render(); });
    }
    function mulai() {
      if (sesi || nonaktif(e.mulai)) return;
      var nama = (e.nama.value || '').trim();
      if (!nama) { e.nama.focus(); return; }
      setDisabled(e.mulai, true);
      api('/api/sessions', { method: 'POST', body: { guest_name: nama } }).then(function (s) {
        e.nama.value = ''; e.hintNama.textContent = '';
        return muatSesi(s);
      }).catch(function (err) {
        if (err.status === 409 && err.body.sesi_aktif) { gambarTertinggal(err.body.sesi_aktif); toast(err.message, 'bad'); }
        else toast('Sesi tidak bisa dimulai: ' + err.message, 'bad');
      }).then(function () { if (pf) gambarPreflight(pf); else setDisabled(e.mulai, false); });
    }
    function akhiri() {
      if (!sesi) return;
      api('/api/sessions/' + sesi.id + '/finish', { method: 'POST' }).then(function (s) {
        pasangSesi(s); selesaikanTampilan();
      }).catch(function (err) {
        if (err.status === 409 && err.body.sesi) { pasangSesi(err.body.sesi); selesaikanTampilan(); }
        else toast('Tidak bisa mengakhiri: ' + err.message, 'bad');
      });
    }
    function selesaikanTampilan() {
      clearInterval(jam); jam = null;
      setChip(e.chipSesi, 'chip-idle', 'Sesi selesai', 'dot-idle');
      tahap('selesai'); render(); tutupDialog();
    }
    function reset() {
      clearInterval(jam); jam = null; sesi = null; foto = []; kosongkanGrid();
      e.nama.value = ''; e.chipSesi.hidden = true; tahap('idle'); render();
      setChip(e.chipUpload, 'chip-idle', 'Belum ada sesi', 'dot-idle');
      window.MCF.muatPreflight();
      if (modePb) {
        // Pemilik yang sama sering membawa lebih dari satu hewan: daftarnya
        // dimuat ulang (status sertifikat terbaru) tanpa scan ulang.
        if (pemilikPb) cariPb(pemilikPb.id); else e.kodePb.focus();
      } else e.nama.focus();
    }
    function cobaLagi(id) {
      var f = foto.find(function (x) { return x.id === id; }); if (!f) return;
      f.status = 'pending'; render();
      api('/api/photos/' + id + '/retry', { method: 'POST' }).catch(function (err) { toast(err.message, 'bad'); muatUlangFoto(); });
    }
    function muatUlangFoto() { if (sesi) api('/api/sessions/' + sesi.id + '/photos').then(function (fs) { foto = fs; render(); }).catch(function () {}); }

    /* ---- Pet Blessing: scan QR, pilih hewan ---- */
    function cariPb(kode) {
      kode = (kode || '').trim();
      if (kode.length < 8) { e.hintPb.className = 'field-hint is-wait'; e.hintPb.textContent = 'Kode minimal 8 huruf.'; return; }
      e.hintPb.className = 'field-hint'; e.hintPb.textContent = 'Mencari…';
      api('/api/sessions/bersiap', { method: 'POST' }).catch(function () {});
      api('/api/pb/pemilik?kode=' + encodeURIComponent(kode)).then(function (o) {
        pemilikPb = o; e.kodePb.value = '';
        e.hintPb.className = o.dari_salinan ? 'field-hint is-wait' : 'field-hint';
        e.hintPb.textContent = o.dari_salinan ? 'Internet putus: data diambil dari salinan terakhir di laptop.' : '';
        e.nomorPb.textContent = 'Nomor antrean ' + o.nomor + (o.uji ? ' · DATA UJI' : '');
        e.pemilikPb.textContent = o.nama;
        e.hewanPb.textContent = '';
        o.hewan.forEach(function (h) {
          var srt = h.sertifikat;
          var ket = !srt ? 'belum difoto' : srt.status === 'uploaded' ? 'sertifikat sudah di Drive' : srt.status === 'failed' ? 'sertifikat gagal dibuat' : 'sertifikat menunggu upload';
          var b = el('button', { class: 'btn pb-hewan' + (srt ? '' : ' btn-primary'), type: 'button', 'data-pb-pilih': h.id }, [
            el('span', {}, [el('strong', { text: h.nama }), document.createTextNode(' · ' + h.jenis)]),
            el('span', { class: 'small', text: ket })
          ]);
          e.hewanPb.appendChild(b);
        });
        e.hasilPb.hidden = false;
        if (pf) gambarPreflight(pf);
      }).catch(function (err) {
        pemilikPb = null; e.hasilPb.hidden = true;
        e.hintPb.className = 'field-hint is-bad'; e.hintPb.textContent = err.message;
      });
    }
    function mulaiPb(petId) {
      if (sesi || !pemilikPb) return;
      api('/api/sessions', { method: 'POST', body: { owner_id: pemilikPb.id, pet_id: petId } }).then(muatSesi).catch(function (err) {
        if (err.status === 409 && err.body.sesi_aktif) { gambarTertinggal(err.body.sesi_aktif); toast(err.message, 'bad'); }
        else toast('Sesi tidak bisa dimulai: ' + err.message, 'bad');
      });
    }
    var aliranKamera = null, detektor = null;
    if ('BarcodeDetector' in window) { try { detektor = new window.BarcodeDetector({ formats: ['qr_code'] }); e.kameraWrap.hidden = false; } catch (x) { detektor = null; } }
    function hentikanKamera() {
      if (aliranKamera) aliranKamera.getTracks().forEach(function (t) { t.stop(); });
      aliranKamera = null; if (e.video) e.video.hidden = true;
    }
    function mulaiKamera() {
      if (aliranKamera) { hentikanKamera(); return; }
      navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 } } }).then(function (st) {
        aliranKamera = st; e.video.srcObject = st; e.video.hidden = false; e.video.play();
        (function pindai() {
          if (!aliranKamera) return;
          detektor.detect(e.video).then(function (hasil) {
            if (hasil && hasil.length) { hentikanKamera(); cariPb(hasil[0].rawValue); } else setTimeout(pindai, 250);
          }).catch(function () { setTimeout(pindai, 500); });
        })();
      }).catch(function () { toast('Kamera laptop tidak bisa dibuka.', 'bad'); });
    }

    /* ---- Pet Blessing: sertifikat ---- */
    function gambarSertifikat(srt) {
      var status = srt ? srt.status : null;
      var t = !srt ? ['chip-idle', 'dot-idle', 'Belum dibuat', 'Tap foto terbaik di bawah, lalu tekan Buat sertifikat.']
        : status === 'render' ? ['chip-wait', 'dot-wait', 'Sedang dibuat', 'Sertifikat sedang disusun dari foto pilihan.']
        : status === 'menunggu' ? ['chip-wait', 'dot-wait', 'Menunggu upload', srt.pesan || 'Sertifikat siap di laptop, sedang dikirim ke Drive.']
        : status === 'uploaded' ? ['chip-ok', 'dot-ok', srt.tercatat ? 'Di Drive, tercatat' : 'Di Drive', srt.tercatat ? 'PDF dan PNG sudah di Drive dan tautannya tercatat di data pendaftaran.' : 'PDF dan PNG sudah di Drive. Tautan ke data pendaftaran menyusul otomatis.']
        : ['chip-bad', 'dot-bad', 'Gagal', 'Sertifikat gagal dibuat: ' + (srt.pesan || 'sebab tidak diketahui') + '. Pilih foto lain lalu coba lagi.'];
      setChip(e.chipSrt, t[0], t[2], t[1]); e.infoSrt.textContent = t[3];
      var adaBerkas = srt && srt.png_path;
      e.imgSrt.hidden = !adaBerkas; if (adaBerkas) e.imgSrt.src = '/api/sertifikat/' + srt.id + '/berkas.png?v=' + srt.id + status;
      e.pdfSrt.hidden = !adaBerkas; if (adaBerkas) e.pdfSrt.href = '/api/sertifikat/' + srt.id + '/berkas.pdf';
      e.driveSrt.hidden = !(srt && srt.link_pdf); if (srt && srt.link_pdf) e.driveSrt.href = srt.link_pdf;
      e.btnSrt.textContent = srt && status !== 'failed' ? 'Buat ulang dengan foto pilihan' : 'Buat sertifikat';
      setDisabled(e.btnSrt, !pilihan || status === 'render');
    }
    function muatSertifikat() {
      if (!sesi || !sesi.pb) return;
      api('/api/sessions/' + sesi.id + '/sertifikat').then(function (daftar) { srtTerakhir = daftar[daftar.length - 1] || null; gambarSertifikat(srtTerakhir); }).catch(function () {});
    }
    var srtTerakhir = null;
    function pilihFoto(id) {
      pilihan = pilihan === id ? null : id;
      $$('.photo', e.grid).forEach(function (n) { n.classList.toggle('is-pilih', n.dataset.foto === String(pilihan)); });
      setDisabled(e.btnSrt, !pilihan || (srtTerakhir && srtTerakhir.status === 'render'));
    }
    function buatSertifikat() {
      if (!sesi || !pilihan || nonaktif(e.btnSrt)) return;
      setDisabled(e.btnSrt, true);
      api('/api/sessions/' + sesi.id + '/sertifikat', { method: 'POST', body: { photo_id: pilihan } }).then(function (srt) { srtTerakhir = srt; gambarSertifikat(srt); })
        .catch(function (err) { toast(err.message, 'bad'); setDisabled(e.btnSrt, false); });
    }

    /* ---- dialog ---- */
    function isiDialog() {
      var c = hitung();
      var bentuk = (c.antre + c.gagal) > 0 ? 'berisiko' : 'aman';
      var berubah = !!e.dialog.dataset.bentukAktif && e.dialog.dataset.bentukAktif !== bentuk;
      e.dialog.dataset.bentukAktif = bentuk;
      $$('[data-bentuk]', e.dialog).forEach(function (n) { n.hidden = n.dataset.bentuk !== bentuk; });
      $$('[data-d-jumlah]', e.dialog).forEach(function (n) { n.textContent = c.total; });
      $$('[data-d-ok]', e.dialog).forEach(function (n) { n.textContent = c.ok; });
      $$('[data-d-nama]', e.dialog).forEach(function (n) { n.textContent = sesi.guest_name; });
      $$('[data-d-sisa]', e.dialog).forEach(function (n) { n.textContent = c.antre + c.gagal; });
      var last = foto[foto.length - 1];
      $$('[data-d-terakhir]', e.dialog).forEach(function (n) { n.textContent = last ? relatif(detikSejak(last.created_at)) : 'belum ada'; });
      var tamu = e.dialog.querySelector('[data-d-tamu]');
      var hidup = !!(window.MCF.preflight && window.MCF.preflight.layar_tamu);
      if (tamu) { tamu.textContent = hidup ? 'terhubung' : 'belum dibuka — QR bisa ditampilkan di laptop'; tamu.className = 'mono-plain ' + (hidup ? 'ok-text' : 'wait-text'); }
      e.dialog.setAttribute('aria-labelledby', bentuk === 'aman' ? 'judulAman' : 'judulBerisiko');
      var daftar = e.dialog.querySelector('[data-d-daftar]'); daftar.textContent = '';
      foto.filter(function (f) { return f.status !== 'uploaded'; }).forEach(function (f) {
        daftar.appendChild(el('div', { class: 'row-between', style: 'margin-top:8px' }, [
          el('span', { class: 'small bad-text', text: f.nama }),
          el('span', { class: 'mono bad-text', text: f.status === 'failed' ? 'Gagal · 3 percobaan' : 'Masih diupload' })
        ]));
      });
      return berubah;
    }
    function fokuskanUtama() { var aktif = e.dialog.querySelector('[data-bentuk]:not([hidden])'); var u = aktif && aktif.querySelector('.btn-primary'); if (u) u.focus(); }
    function bukaDialog() { if (nonaktif(e.btnSelesai) || !sesi) return; delete e.dialog.dataset.bentukAktif; isiDialog(); e.dialog.showModal(); fokuskanUtama(); }
    function tutupDialog() { if (e.dialog.open) e.dialog.close(); }
    e.dialog.addEventListener('close', function () { var k = root.dataset.tahapAktif === 'selesai' ? root.querySelector('[data-sesi-baru]') : e.btnSelesai; if (k) k.focus(); });

    /* ---- ikatan ---- */
    e.mulai.addEventListener('click', mulai);
    e.kodePb.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') cariPb(e.kodePb.value); });
    root.querySelector('[data-pb-cari]').addEventListener('click', function () { cariPb(e.kodePb.value); });
    root.querySelector('[data-pb-kamera]').addEventListener('click', mulaiKamera);
    e.hewanPb.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-pb-pilih]'); if (b && !nonaktif(b)) mulaiPb(b.dataset.pbPilih);
    });
    e.btnSrt.addEventListener('click', buatSertifikat);
    e.grid.addEventListener('click', function (ev) {
      if (!sesi || !sesi.pb || ev.target.closest('[data-retry]')) return;
      var p = ev.target.closest('.photo'); if (p && p.dataset.foto) pilihFoto(parseInt(p.dataset.foto, 10));
    });
    e.nama.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') mulai(); });
    e.btnSelesai.addEventListener('click', bukaDialog);
    e.dialog.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-batal]')) tutupDialog();
      if (ev.target.closest('[data-akhiri]')) { if (nonaktif(e.btnSelesai)) { toast('Server tidak menjawab.', 'bad'); return; } akhiri(); }
    });
    root.addEventListener('click', function (ev) {
      var r = ev.target.closest('[data-retry]');
      if (r) { cobaLagi(parseInt(r.dataset.retry, 10)); return; }
      if (ev.target.closest('[data-retry-semua]')) {
        if (!sesi) return;
        foto.forEach(function (f) { if (f.status === 'failed') f.status = 'pending'; }); render();
        api('/api/sessions/' + sesi.id + '/retry-failed', { method: 'POST' }).then(function (r) { toast(r.jumlah_retry + ' foto diupload ulang.', 'ok'); }).catch(function (err) { toast(err.message, 'bad'); });
        return;
      }
      if (ev.target.closest('[data-pasang-drive]')) {
        if (!sesi) return;
        api('/api/sessions/' + sesi.id + '/drive', { method: 'POST' }).then(function (s) { pasangSesi(s); render(); toast('Folder Drive terpasang.', 'ok'); })
          .catch(function (err) { toast(err.message, 'bad'); });
        return;
      }
      if (ev.target.closest('[data-sesi-baru]')) reset();
      if (ev.target.closest('[data-sambung-ulang]')) aliran.sambungUlang();
      if (ev.target.closest('[data-akui-tanpa-sesi]')) {
        api('/api/tanpa-sesi/akui', { method: 'POST' }).then(function () { window.MCF.muatPreflight(); }).catch(function (err) { toast(err.message, 'bad'); });
      }
    });
    $$('[data-salin]', root).forEach(function (b) { ikatSalin(b, function () { return sesi && sesi.drive_folder_link; }); });

    /* ---- aliran ---- */
    function milikSesi(d) { return sesi && (d.session_id === sesi.id || (d.sesi && d.sesi.id === sesi.id) || (d.foto && d.foto.session_id === sesi.id)); }
    aliran.on('foto_baru', function (d) {
      if (!milikSesi(d)) return;
      if (!foto.some(function (f) { return f.id === d.foto.id; })) { d.foto.nama = d.foto.nama || d.foto.local_path.split(/[\\/]/).pop(); d.foto.thumb = d.foto.thumb || d.foto.nama.replace(/\.[^.]+$/, '.jpg'); foto.push(d.foto); }
      render();
    });
    ['foto_uploaded', 'foto_gagal', 'foto_retry'].forEach(function (j) {
      aliran.on(j, function (d) {
        if (!milikSesi(d) || !d.foto) return;
        var t = foto.find(function (x) { return x.id === d.foto.id; });
        if (t) t.status = d.foto.status; else muatUlangFoto();
        render();
      });
    });
    ['sertifikat_mulai', 'sertifikat_siap', 'sertifikat_uploaded', 'sertifikat_tertunda', 'sertifikat_tercatat', 'sertifikat_gagal'].forEach(function (j) {
      aliran.on(j, function (d) {
        if (!sesi || d.session_id !== sesi.id) return;
        srtTerakhir = d.sertifikat; gambarSertifikat(d.sertifikat);
        if (j === 'sertifikat_uploaded') toast('Sertifikat sudah di Drive.', 'ok');
        if (j === 'sertifikat_gagal') toast('Sertifikat gagal dibuat.', 'bad');
      });
    });
    aliran.on('sesi_drive_terpasang', function (d) { if (milikSesi(d)) { pasangSesi(d.sesi); render(); } });
    aliran.on('sesi_mulai', function (d) { if (!sesi || sesi.id !== d.sesi.id) muatSesi(d.sesi); });
    aliran.on('sesi_selesai', function (d) { if (sesi && d.sesi.id === sesi.id && root.dataset.tahapAktif === 'aktif') { pasangSesi(d.sesi); selesaikanTampilan(); } });
    aliran.on('koneksi', function (hidup) {
      if (e.pitaPutus) e.pitaPutus.hidden = hidup;
      setDisabled(e.btnSelesai, !hidup, e.alasanSelesai, 'Server tidak menjawab. Angka di layar mungkin basi — jangan akhiri sesi dari sini sebelum tersambung lagi.');
      if (sesi && !e.chipSesi.hidden) setChip(e.chipSesi, hidup ? 'chip-ok' : 'chip-bad', hidup ? 'Sesi berjalan' : 'Sesi berjalan?', hidup ? 'dot-live' : 'dot-bad');
      if (hidup) { muatUlangFoto(); if (pf) gambarPreflight(pf); }
    });
    /* Sesi aktif saat halaman dibuka: kalau masih hangat (ada foto atau baru
       dimulai dalam 10 menit) langsung dilanjutkan — operator cuma pindah
       halaman. Kalau sudah dingin, ini sesi tertinggal (design.md §4.1):
       pita menawarkan lanjutkan atau akhiri, tidak memutuskan sendiri. */
    function sesiMasihHangat(s) {
      var acuan = s.foto_terakhir_at || s.started_at;
      var d = detikSejak(acuan);
      return d != null && d < 600;
    }
    aliran.on('halo', function (d) {
      if (d.sesi_aktif && (!sesi || sesi.id !== d.sesi_aktif.id) && root.dataset.tahapAktif !== 'selesai') {
        if (sesiMasihHangat(d.sesi_aktif)) muatSesi(d.sesi_aktif); else gambarTertinggal(d.sesi_aktif);
      } else if (!d.sesi_aktif && sesi && root.dataset.tahapAktif === 'aktif') {
        api('/api/sessions/' + sesi.id).then(function (s) { pasangSesi(s); if (s.status === 'done') selesaikanTampilan(); });
      }
    });

    tahap('idle'); render(); e.nama.focus();
  })();

  /* =========================================================== halaman Riwayat */

  (function halamanRiwayat() {
    var root = $('[data-riwayat]');
    if (!root) return;
    var e = { cari: $('[data-cari]'), daftar: $('[data-daftar]'), kosong: $('[data-kosong]'), kosongCari: $('[data-kosong-cari]'), kosongQ: $('[data-kosong-q]'), ringkas: $('[data-ringkasan-riwayat]'), lagi: $('[data-lagi]'), skel: $('[data-skel]'), pitaQr: $('[data-pita-qr]'), pitaQrNama: $('[data-pita-qr-nama]'), filterCatatan: $('[data-filter-catatan]') };
    var q = '', offset = 0, total = 0, LIMIT = 20, filter = 'semua', dimuat = [];

    /* Chip filter Semua/Lengkap/Perlu tindakan (design.md §0 v1.2): saringan
       ini hanya menata ulang tampilan baris yang SUDAH dimuat di halaman ini —
       tidak ada endpoint pencarian baru, jadi ia jujur menyebut batasannya
       sendiri lewat data-filter-catatan alih-alih berpura-pura lengkap. */
    var chipFilter = $$('[data-filter]', root);
    function cocokFilter(s) {
      if (filter === 'semua') return true;
      var sisa = s.foto.pending + s.foto.failed;
      if (filter === 'masalah') return sisa > 0;
      return sisa === 0; // 'lengkap' — termasuk sesi tanpa foto sama sekali
    }
    function terapkanFilter() {
      var tampil = 0;
      $$('.list-row', e.daftar).forEach(function (row, i) {
        var cocok = cocokFilter(dimuat[i]);
        row.hidden = !cocok; if (cocok) tampil++;
      });
      chipFilter.forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.filter === filter)); });
      if (e.filterCatatan) e.filterCatatan.hidden = filter === 'semua';
      var lengkap = dimuat.filter(function (s) { return s.foto.pending + s.foto.failed === 0; }).length;
      var masalah = dimuat.length - lengkap;
      $$('[data-filter-n="semua"]').forEach(function (n) { n.textContent = String(dimuat.length); });
      $$('[data-filter-n="lengkap"]').forEach(function (n) { n.textContent = String(lengkap); });
      $$('[data-filter-n="masalah"]').forEach(function (n) { n.textContent = String(masalah); });
      return tampil;
    }
    chipFilter.forEach(function (c) {
      c.addEventListener('click', function () { filter = c.dataset.filter; terapkanFilter(); });
    });

    function chipStatus(s) {
      var f = s.foto;
      if (s.status === 'active') return el('span', { class: 'chip chip-accent' }, [el('span', { class: 'dot dot-live' }), 'Sedang berjalan · ' + f.total + ' foto']);
      if (f.total === 0) return el('span', { class: 'chip chip-idle' }, [el('span', { class: 'dot dot-idle' }), 'Tanpa foto']);
      var sisa = f.pending + f.failed;
      if (sisa > 0) return el('span', { class: 'chip chip-bad' }, [el('span', { class: 'dot dot-bad' }), sisa + ' dari ' + f.total + ' belum terkirim']);
      return el('span', { class: 'chip chip-ok' }, [el('span', { class: 'dot dot-ok' }), f.total + ' foto lengkap']);
    }
    function baris(s) {
      var sisa = s.foto.pending + s.foto.failed;
      var row = el('div', { class: 'list-row' + (sisa > 0 ? ' has-problem' : '') });
      row.appendChild(el('div', { class: 'who' }, [
        el('div', { class: 'name', text: s.guest_name }),
        el('div', { class: 'code', text: s.session_code + ' · ' + fmtTanggal(s.started_at) + ' ' + fmtJam(s.started_at) + (s.finished_at ? '–' + fmtJam(s.finished_at) : ' – berjalan') })
      ]));
      row.appendChild(chipStatus(s));
      var acts = el('div', { class: 'acts' });
      if (sisa > 0 && s.status === 'done') {
        var up = el('button', { class: 'btn btn-sm btn-danger-ghost', type: 'button', text: 'Upload sisanya', 'data-butuh-server': '' });
        up.addEventListener('click', function () {
          if (nonaktif(up)) { toast('Server tidak menjawab.', 'bad'); return; }
          up.textContent = 'Mengupload…';
          api('/api/sessions/' + s.id + '/retry-failed', { method: 'POST' }).then(function (r) { toast(r.jumlah_retry + ' foto diupload ulang.', r.jumlah_retry ? 'ok' : ''); }).catch(function (err) { toast(err.message, 'bad'); }).then(function () { up.textContent = 'Upload sisanya'; });
        });
        acts.appendChild(up);
      }
      var salin = el('button', { class: 'btn btn-sm btn-quiet', type: 'button', text: 'Salin tautan' });
      ikatSalin(salin, function () { return s.drive_folder_link; });
      acts.appendChild(salin);
      if (s.drive_folder_link) {
        acts.appendChild(el('a', { class: 'btn btn-sm btn-quiet', href: s.drive_folder_link, target: '_blank', rel: 'noopener', text: 'Buka folder Drive' }));
      }
      var qr = el('button', { class: 'btn btn-sm btn-primary', type: 'button', text: 'Tampilkan QR', 'data-butuh-server': '' });
      var alasanQr = !s.drive_folder_link ? 'Belum ada folder Drive, jadi belum ada QR' : (s.status === 'active' ? 'Sesi ini sedang berjalan — QR tampil setelah Selesai' : '');
      if (alasanQr) { qr.setAttribute('aria-disabled', 'true'); acts.appendChild(el('p', { class: 'btn-reason is-quiet', style: 'flex-basis:100%;margin:0', text: alasanQr })); }
      qr.addEventListener('click', function () {
        if (nonaktif(qr)) { toast(alasanQr || 'Server tidak menjawab.', 'bad'); return; }
        api('/api/sessions/' + s.id + '/tampilkan-qr', { method: 'POST' }).then(function () { toast('QR ' + s.guest_name + ' tampil di monitor tamu.', 'ok'); }).catch(function (err) { toast(err.message, 'bad'); });
      });
      acts.appendChild(qr);
      row.appendChild(acts);
      return row;
    }
    function muat(reset) {
      if (reset) { offset = 0; e.daftar.textContent = ''; dimuat = []; }
      e.skel.hidden = false; e.lagi.hidden = true;
      api('/api/sessions?q=' + encodeURIComponent(q) + '&limit=' + LIMIT + '&offset=' + offset).then(function (r) {
        total = r.total;
        if (reset) { e.daftar.textContent = ''; dimuat = []; }
        r.sesi.forEach(function (s) { e.daftar.appendChild(baris(s)); dimuat.push(s); });
        offset += r.sesi.length;
        e.kosong.hidden = !(total === 0 && !q); e.kosongCari.hidden = !(total === 0 && q);
        if (e.kosongQ) e.kosongQ.textContent = q;
        e.lagi.hidden = offset >= total;
        e.ringkas.textContent = q ? total + ' sesi cocok' : total + ' sesi tercatat';
        terapkanFilter();
      }).catch(function (err) { toast('Riwayat tidak bisa dimuat: ' + err.message, 'bad'); }).then(function () { e.skel.hidden = true; });
    }
    e.cari.addEventListener('input', debounce(function () { q = e.cari.value.trim(); muat(true); }, 300));
    e.lagi.addEventListener('click', function () { muat(false); });
    var segarkan = debounce(function () { muat(true); }, 600);
    ['sesi_mulai', 'sesi_selesai', 'foto_uploaded', 'foto_gagal', 'foto_baru', 'sesi_drive_terpasang'].forEach(function (j) { aliran.on(j, segarkan); });
    aliran.on('koneksi', function (hidup) { if (hidup) segarkan(); });

    document.addEventListener('mcf:preflight', function (ev) {
      var t = ev.detail.tampilan_tamu || {};
      var aktif = t.keadaan === 'qr' && t.dari_riwayat;
      e.pitaQr.hidden = !aktif;
      if (aktif) e.pitaQrNama.textContent = t.nama_tamu;
    });
    $('[data-batal-qr]').addEventListener('click', function () {
      api('/api/tampilan-tamu/qr', { method: 'DELETE' }).then(function () { toast('Monitor tamu kembali ke sambutan.', 'ok'); window.MCF.muatPreflight(); }).catch(function (err) { toast(err.message, 'bad'); });
    });
    document.addEventListener('mcf:ringkasan', function (ev) {
      var r = ev.detail; var h = $('[data-ringkasan-hari]');
      if (h) h.textContent = r.hari_ini + ' sesi hari ini · ' + r.bermasalah + ' sesi dengan foto tertinggal';
    });
    e.cari.focus(); muat(true);
  })();

  /* ======================================================= halaman Layar tamu */

  (function halamanLayarTamu() {
    var root = $('[data-layar-tamu]');
    if (!root) return;
    var f = $('.mirror iframe', root); if (f && f.dataset.src) { f.src = f.dataset.src; f.removeAttribute('data-src'); }
    document.addEventListener('mcf:preflight', function (ev) {
      var p = ev.detail, t = p.tampilan_tamu || {};
      var v = $('[data-lt-keadaan]');
      if (v) v.textContent = ({ sambutan: 'layar sambutan', memotret: 'sesi ' + (t.nama_tamu || '') + ' — ' + (t.foto_count || 0) + ' foto', qr: 'QR ' + (t.nama_tamu || '') + (t.dari_riwayat ? ' (dari Riwayat)' : '') })[t.keadaan] || '—';
      var j = $('[data-lt-jumlah]'); if (j) j.textContent = p.layar_tamu_jumlah ? p.layar_tamu_jumlah + ' jendela terhubung' : 'tidak ada jendela yang terhubung';
      var m = $('.mirror', root); if (m) { m.classList.remove('mirror-unknown'); }
    });
    $$('[data-qr-laptop]').forEach(function (b) { b.addEventListener('click', function () { window.open('/tamu?laptop=1', '_blank'); }); });
  })();

  /* ======================================================= halaman Pengaturan */

  (function halamanPengaturan() {
    var root = $('[data-pengaturan]');
    if (!root) return;
    function isi(kunci, nilai) { $$('[data-p="' + kunci + '"]', root).forEach(function (n) { n.textContent = nilai == null || nilai === '' ? '—' : String(nilai); }); }
    var btnLogin = $('[data-drive-login]'), btnLogout = $('[data-drive-logout]'), chip = $('[data-drive-chip]'), pesan = $('[data-drive-pesan]'), meter = $('[data-kuota-meter]'), btnUji = $('[data-uji-ulang]');

    function gambarDrive(p) {
      var d = p.drive || {};
      var peta = { terhubung: ['chip-ok', 'Terhubung', 'dot-ok'], belum_login: ['chip-bad', 'Belum login', 'dot-bad'], token_kedaluwarsa: ['chip-bad', 'Login ulang', 'dot-bad'], tanpa_credentials: ['chip-bad', 'credentials.json tidak ada', 'dot-bad'], offline: ['chip-wait', 'Offline', 'dot-wait'] };
      var k = peta[d.keadaan] || ['chip-bad', 'Galat', 'dot-bad'];
      setChip(chip, k[0], k[1], k[2]);
      isi('email', d.email || (d.keadaan === 'terhubung' ? 'akun Drive' : 'belum ada akun'));
      pesan.textContent = d.keadaan === 'terhubung' ? '' : (d.pesan || '');
      isi('kuota', d.kuota_total_gb ? fmtGb(d.kuota_terpakai_gb) + ' dari ' + fmtGb(d.kuota_total_gb) : '—');
      isi('kuota-sisa', d.kuota_sisa_gb != null ? 'Sisa ' + fmtGb(d.kuota_sisa_gb) + ' — cukup untuk sekitar ' + Math.floor(d.kuota_sisa_gb * 80) + ' foto JPEG 24 MP (±12 MB).' : 'Kuota belum bisa dibaca.');
      if (meter) { var pct = d.kuota_total_gb ? Math.min(100, d.kuota_terpakai_gb / d.kuota_total_gb * 100) : 0; meter.innerHTML = '<span class="' + (pct > 85 ? 'm-bad' : pct > 65 ? 'm-wait' : 'm-ok') + '" style="width:' + pct + '%"></span>'; }
      var s = p.drive_struktur;
      isi('struktur', s ? (s.sumber === 'env' ? 'folder induk dari .env' : 'folder induk dibuat aplikasi') + ' · ' + (s.qr ? 'QR ✓' : 'QR ✗') + ' · ' + (s.result ? 'Result ✓' : 'Result ✗') : 'menunggu Drive terhubung');
      btnLogin.textContent = d.login_berjalan ? 'Menunggu izin di browser…' : ((d.keadaan === 'terhubung' || d.keadaan === 'token_kedaluwarsa') ? 'Login ulang' : 'Login Google');
      setDisabled(btnLogin, d.login_berjalan || d.keadaan === 'tanpa_credentials', $('[data-drive-login-alasan]'), d.keadaan === 'tanpa_credentials' ? 'Taruh credentials.json dulu di akar folder.' : '');
      setDisabled(btnLogout, !d.token_ada, $('[data-drive-logout-alasan]'), 'Belum ada akun yang login.');
      isi('layar-tamu', p.layar_tamu ? 'jendela terbuka' : 'belum dibuka');
      isi('internet', p.internet ? 'tersambung' : 'putus');
      isi('disk', fmtGb(p.disk_bebas_gb) + ' bebas');
    }
    document.addEventListener('mcf:preflight', function (ev) { gambarDrive(ev.detail); });
    if (window.MCF.preflight) gambarDrive(window.MCF.preflight);

    api('/api/pengaturan').then(function (c) {
      isi('versi', c.versi); isi('kamera', c.kamera); isi('tethering', c.tethering_app);
      isi('tether', c.tether_folder); isi('arsip', c.archive_folder); isi('thumbs', c.thumbs_folder); isi('qr', c.qr_folder); isi('db', c.db);
      isi('retry', c.retry_delays.join(', ') + ' detik'); isi('tenggang', c.tenggang_setelah_selesai + ' detik'); isi('stabil', c.stabilitas_detik + ' detik');
      isi('scope', c.drive.scope); isi('credentials', c.drive.credentials_path + (c.drive.credentials_ada ? '' : ' — belum ada')); isi('token', c.drive.token_path + (c.drive.token_ada ? '' : ' — belum ada'));
      isi('root', c.drive.parent_folder_env ? c.drive.parent_folder_env + ' (dari .env)' : c.drive.nama_root + ' (dibuat aplikasi di akar Drive)');
      isi('folder-qr', c.drive.folder_qr); isi('folder-result', c.drive.folder_result);
      isi('tanpa-drive', c.izinkan_tanpa_drive ? 'diizinkan (mode pengembangan)' : 'tidak diizinkan');
    }).catch(function (err) { toast('Pengaturan tidak bisa dimuat: ' + err.message, 'bad'); });

    var pollLogin = null;
    btnLogin.addEventListener('click', function () {
      if (nonaktif(btnLogin)) return;
      api('/api/drive/login', { method: 'POST' }).then(function (r) {
        toast(r.pesan, r.ok ? '' : 'bad');
        clearInterval(pollLogin);
        pollLogin = setInterval(function () {
          api('/api/drive/login').then(function (k) {
            if (!k.berjalan) { clearInterval(pollLogin); toast(k.pesan || 'Selesai.', k.hasil === 'ok' ? 'ok' : 'bad'); window.MCF.muatPreflight(); }
          });
        }, 1500);
        window.MCF.muatPreflight();
      }).catch(function (err) { toast(err.message, 'bad'); });
    });
    btnLogout.addEventListener('click', function () {
      if (nonaktif(btnLogout)) return;
      if (!window.confirm('Hapus token dan keluar dari akun Drive ini? Sesi yang sudah ada tidak terpengaruh.')) return;
      api('/api/drive/logout', { method: 'POST' }).then(function (r) { toast(r.pesan, 'ok'); window.MCF.muatPreflight(); }).catch(function (err) { toast(err.message, 'bad'); });
    });
    aliran.on('drive_status', function () { window.MCF.muatPreflight(); });

    if (btnUji) btnUji.addEventListener('click', function () {
      if (nonaktif(btnUji)) return;
      var semula = btnUji.textContent; btnUji.textContent = 'Menguji…';
      Promise.all([api('/api/drive/status?paksa=true'), window.MCF.muatPreflight()])
        .then(function () { toast('Pemeriksaan selesai.', 'ok'); })
        .catch(function (err) { toast(err.message, 'bad'); })
        .then(function () { btnUji.textContent = semula; });
    });
  })();

  /* ============================================================= layar tamu */

  (function halamanTamu() {
    var root = $('[data-tamu]');
    if (!root) return;
    var blok = {}; $$('[data-variant]', root).forEach(function (n) { blok[n.dataset.variant] = n; });
    var e = { nama: $('[data-t-nama]'), jml: $('[data-t-jumlah]'), grid: $('[data-t-grid]'), gridKosong: $('[data-t-kosong]'), qNama: $('[data-q-nama]'), qJml: $('[data-q-jumlah]'), qStrip: $('[data-q-strip]'), qrCard: $('[data-qr-card]'), qrImg: $('[data-qr-img]'), link: $('[data-q-link]'), status: $('[data-t-status]'), statusDot: $('[data-t-status-dot]') };
    var jumlahLama = 0, kodeLama = null, keadaanLama = null;

    function tile(kode, f, baru) {
      var d = el('div', { class: 'photo' + (baru ? ' is-new' : '') }, [el('span', { class: 'fill' })]);
      d.firstChild.style.backgroundImage = 'url("' + thumbUrl(kode, f) + '")';
      return d;
    }
    function pasangNama(node, nama) {
      nama = nama || ''; node.textContent = nama;
      node.classList.toggle('is-long', nama.length > 16 && nama.length <= 26);
      node.classList.toggle('is-verylong', nama.length > 26);
    }
    function render(t) {
      t = t || { keadaan: 'sambutan' };
      Object.keys(blok).forEach(function (k) { blok[k].classList.toggle('is-on', k === t.keadaan); });
      if (t.keadaan === 'memotret') {
        if (kodeLama !== t.session_code) { jumlahLama = 0; e.grid.textContent = ''; }
        pasangNama(e.nama, t.nama_tamu); e.jml.textContent = String(t.foto_count || 0);
        var fotos = t.fotos || [];
        e.grid.textContent = '';
        fotos.forEach(function (f, i) { e.grid.appendChild(tile(t.session_code, f, i === fotos.length - 1 && (t.foto_count || 0) > jumlahLama)); });
        e.gridKosong.hidden = fotos.length > 0; e.grid.hidden = fotos.length === 0;
        jumlahLama = t.foto_count || 0;
      }
      if (t.keadaan === 'qr') {
        pasangNama(e.qNama, t.nama_tamu); e.qJml.textContent = String(t.foto_count || 0);
        e.qStrip.textContent = ''; (t.fotos || []).forEach(function (f) { e.qStrip.appendChild(tile(t.session_code, f, false)); });
        e.qStrip.hidden = !(t.fotos && t.fotos.length);
        if (t.qr_ada) {
          e.qrCard.classList.remove('is-missing'); e.qrImg.hidden = false;
          var src = '/api/qr/' + encodeURIComponent(t.session_code);
          if (e.qrImg.getAttribute('data-kode') !== t.session_code) { e.qrImg.src = src; e.qrImg.setAttribute('data-kode', t.session_code); }
          $('[data-qr-teks]').hidden = true;
        } else { e.qrCard.classList.add('is-missing'); e.qrImg.hidden = true; $('[data-qr-teks]').hidden = false; }
        e.link.textContent = (t.drive_folder_link || '').replace(/^https?:\/\//, '');
      }
      if (t.keadaan === 'sambutan') { jumlahLama = 0; }
      kodeLama = t.session_code || null; keadaanLama = t.keadaan;
    }
    var segarkan = debounce(function () { api('/api/tampilan-tamu').then(render).catch(function () {}); }, 120);
    aliran.on('halo', function (d) { if (d.tampilan) render(d.tampilan); else segarkan(); });
    aliran.on('*', function (d) { if (d.jenis !== 'halo' && d.jenis !== 'layar_tamu') segarkan(); });
    aliran.on('koneksi', function (hidup) {
      if (e.status) { e.status.textContent = hidup ? 'tersambung' : 'menyambung ulang…'; e.statusDot.className = 'dot ' + (hidup ? 'dot-ok' : 'dot-bad'); }
      if (hidup) segarkan();
    });
    setInterval(function () { if (!aliran.terhubung) segarkan(); }, 10000);
    segarkan();

    // Layar tidak boleh tidur (design.md §5.4).
    var lock = null;
    function jagaTerjaga() {
      if (!('wakeLock' in navigator) || CERMIN) return;
      navigator.wakeLock.request('screen').then(function (l) { lock = l; l.addEventListener('release', function () { lock = null; }); }).catch(function () {});
    }
    jagaTerjaga();
    document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible' && lock === null) jagaTerjaga(); });

    // Jalan keluar tersembunyi: tekan-tahan pojok kanan bawah 2 detik (design.md §5.3).
    var keluar = $('[data-keluar]'), timerKeluar = null;
    if (keluar) {
      var mulaiTahan = function () { timerKeluar = setTimeout(function () { location.href = '/'; }, 2000); };
      var batal = function () { clearTimeout(timerKeluar); };
      keluar.addEventListener('pointerdown', mulaiTahan); keluar.addEventListener('pointerup', batal); keluar.addEventListener('pointerleave', batal);
    }
    if (!CERMIN) document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') location.href = '/'; });
    if (CERMIN) document.documentElement.classList.add('is-cermin');
  })();
})();
