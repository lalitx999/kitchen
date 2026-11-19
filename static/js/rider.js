/* หน้าไรเดอร์
   1. ส่งพิกัด GPS ทุก ~5 วินาที (หรือเมื่อขยับ > 15 ม.) ระหว่าง "กำลังรับงาน"
   2. กันจอดับ (Wake Lock) ระหว่างรับงาน · กลับเข้าแอปแล้วส่งพิกัดทันที
   3. เสียงเตือนเมื่อมีงานใหม่ (ต้องกด "เปิดเสียง" ก่อน ตามกฎเบราว์เซอร์)
   ไม่มีพิกัดสำรอง: หา GPS ไม่ได้ แสดงสถานะและวิธีแก้ */
(function () {
  var config = document.getElementById('rider-config');
  var LOCATION_URL = config.dataset.locationUrl;
  var SEND_EVERY_MS = 5000;
  var MIN_MOVE_M = 15;
  var csrf = JSON.parse(document.body.getAttribute('hx-headers') || '{}')['X-CSRFToken'];

  var watchId = null, wakeLock = null, last = null, lastSentAt = 0, lastSentPos = null, sending = false;
  var bar = document.getElementById('gps-bar'), barText = document.getElementById('gps-text');

  // ---------------------------------------------------------------- แถบสถานะ GPS
  function setBar(text, level) {
    if (!bar) return;
    bar.classList.remove('d-none', 'border-warning', 'border-danger', 'text-danger');
    if (level === 'warn') bar.classList.add('border-warning');
    if (level === 'error') bar.classList.add('border-danger', 'text-danger');
    barText.textContent = text;
  }

  setInterval(function () {
    if (!watchId || !lastSentAt) return;
    var age = Math.round((Date.now() - lastSentAt) / 1000);
    if (age > 120) setBar('ส่งตำแหน่งล่าสุด ' + Math.round(age / 60) + ' นาทีที่แล้ว: เปิดแอปค้างไว้และเปิด GPS', 'error');
    else if (age > 30) setBar('ส่งตำแหน่งล่าสุด ' + age + ' วิที่แล้ว', 'warn');
    else setBar('ส่งตำแหน่งให้ลูกค้าแล้ว (' + age + ' วิที่แล้ว)');
  }, 3000);

  // ---------------------------------------------------------------- ส่งพิกัด
  function distanceM(a, b) {
    var R = 6371000, toRad = Math.PI / 180;
    var dLat = (b.lat - a.lat) * toRad, dLng = (b.lng - a.lng) * toRad;
    var h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toRad) * Math.cos(b.lat * toRad) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function fillProofForms() {
    if (!last) return;
    document.querySelectorAll('[data-gps-lat]').forEach(function (el) { el.value = last.lat.toFixed(7); });
    document.querySelectorAll('[data-gps-lng]').forEach(function (el) { el.value = last.lng.toFixed(7); });
  }

  function send(force) {
    if (!last || sending) return;
    var due = Date.now() - lastSentAt >= SEND_EVERY_MS;
    var moved = lastSentPos ? distanceM(lastSentPos, last) >= MIN_MOVE_M : true;
    if (!force && !due && !moved) return;
    sending = true;
    fetch(LOCATION_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(last),
    }).then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (res.ok) { lastSentAt = Date.now(); lastSentPos = { lat: last.lat, lng: last.lng }; }
        else setBar(res.body.error || 'ส่งตำแหน่งไม่สำเร็จ', 'warn');
      })
      .catch(function () { setBar('เน็ตหลุด ส่งตำแหน่งไม่ได้ จะลองใหม่อัตโนมัติ', 'warn'); })
      .finally(function () { sending = false; });
  }

  function onPosition(pos) {
    last = {
      lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy,
      heading: (pos.coords.heading === null || isNaN(pos.coords.heading)) ? null : pos.coords.heading,
      speed: (pos.coords.speed === null || isNaN(pos.coords.speed)) ? null : pos.coords.speed,
    };
    fillProofForms();
    // หน้างาน (rider_job.js) ใช้ตำแหน่งนี้คิดระยะ/เวลา และขยับหมุดบนแผนที่
    document.dispatchEvent(new CustomEvent('tmpp:rider-position', { detail: last }));
    send(false);
  }

  function onError(err) {
    var msg = err.code === 1
      ? 'ยังไม่อนุญาตตำแหน่ง: กดรูปแม่กุญแจข้าง URL > เปิดตำแหน่ง แล้วรีเฟรช'
      : 'หาตำแหน่งไม่ได้: เปิด GPS ของมือถือ';
    setBar(msg, 'error');
  }

  async function keepScreenOn() {
    try { if ('wakeLock' in navigator && !wakeLock) wakeLock = await navigator.wakeLock.request('screen'); }
    catch (e) { wakeLock = null; }
  }

  function start() {
    if (watchId !== null) return;
    if (!navigator.geolocation) { setBar('มือถือ/เบราว์เซอร์นี้หาตำแหน่งไม่ได้', 'error'); return; }
    setBar('กำลังหาตำแหน่ง...');
    watchId = navigator.geolocation.watchPosition(onPosition, onError, { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
    keepScreenOn();
  }

  function stop() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null; last = null; lastSentAt = 0;
    if (bar) bar.classList.add('d-none');
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  function syncWithStatus() {
    // หน้าแรกมีการ์ดสถานะที่กดเปลี่ยนได้ · หน้าอื่นใช้ค่าจาก layout (#rider-config)
    var card = document.getElementById('rider-status') || config;
    if (card && card.dataset.online === '1') start(); else stop();
  }

  // ส่งซ้ำทุก 5 วิแม้ไม่ขยับ (ลูกค้าจะรู้ว่าไรเดอร์ยังออนไลน์)
  setInterval(function () { send(false); }, SEND_EVERY_MS);

  document.addEventListener('visibilitychange', function () {
    // เบราว์เซอร์ปล่อย Wake Lock เมื่อสลับแอป -> ขอใหม่ + ส่งพิกัดทันที
    if (document.visibilityState === 'visible' && watchId !== null) { wakeLock = null; keepScreenOn(); send(true); }
  });

  // ---------------------------------------------------------------- เสียงงานใหม่ (sound.js)
  // เหมือนระบบเดิม: มีงานรอรับ -> เสียงดังวนจนกว่าจะกดรับงาน หรือไม่มีงานเหลือ
  var sound = window.TmppSound;
  function readIds() {
    var el = document.getElementById('rider-available-ids');
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }
  var known = new Set(readIds());
  var ringing = false;
  function updateRing(fresh) {
    var waiting = readIds().length > 0;
    if (waiting && (fresh || !ringing)) { sound.play('rider', { loop: true }).then(function (ok) { ringing = ok; }); }
    else if (!waiting && ringing) { sound.stop('rider'); ringing = false; }
  }
  sound.onChange(function (on) { if (on) updateRing(false); else ringing = false; });
  // กดรับงาน -> หยุดเสียงทันที ไม่ต้องรอบอร์ดโหลดใหม่
  document.body.addEventListener('htmx:beforeRequest', function (event) {
    var vals = (event.detail.elt && event.detail.elt.getAttribute('hx-vals')) || '';
    if (vals.indexOf('"accept"') !== -1) { sound.stop('rider'); ringing = false; }
  });

  document.body.addEventListener('htmx:afterSettle', function (event) {
    var id = event.detail.target && event.detail.target.id;
    if (id === 'rider-status') syncWithStatus();
    if (id === 'job-sheet') fillProofForms();
    if (id === 'rider-jobs' || id === 'rider-status') {
      var ids = readIds();
      var fresh = ids.filter(function (x) { return !known.has(x); });
      known = new Set(ids);
      updateRing(fresh.length > 0);
      fillProofForms();
    }
  });

  syncWithStatus();
})();

/* ย่อรูปหลักฐานก่อนส่ง: รูปกล้องมือถือ 3-8 MB -> JPEG ด้านยาว 1600px (~300 KB) อัปโหลดเร็วบนเน็ตมือถือ
   ใส่ไฟล์ที่ย่อแล้วกลับเข้าช่องเดิม (DataTransfer) · เบราว์เซอร์ไม่รองรับ = ส่งรูปเดิม (เซิร์ฟเวอร์รับได้ถึง 6 MB) */
window.tmppCompressImage = function (input) {
  var file = input.files[0];
  var MAX_SIDE = 1600;
  return new Promise(function (resolve) {
    if (!file || !/^image\//.test(file.type) || typeof DataTransfer === 'undefined') { resolve(file); return; }
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob(function (blob) {
        if (!blob || blob.size >= file.size) { resolve(file); return; }
        try {
          var small = new File([blob], 'proof.jpg', { type: 'image/jpeg' });
          var dt = new DataTransfer(); dt.items.add(small); input.files = dt.files;
          resolve(small);
        } catch (e) { resolve(file); }
      }, 'image/jpeg', 0.82);
    };
    img.onerror = function () { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
};
