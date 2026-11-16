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
    bar.classList.add('d-none');
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  function syncWithStatus() {
    var card = document.getElementById('rider-status');
    if (card && card.dataset.online === '1') start(); else stop();
  }

  // ส่งซ้ำทุก 5 วิแม้ไม่ขยับ (ลูกค้าจะรู้ว่าไรเดอร์ยังออนไลน์)
  setInterval(function () { send(false); }, SEND_EVERY_MS);

  document.addEventListener('visibilitychange', function () {
    // เบราว์เซอร์ปล่อย Wake Lock เมื่อสลับแอป -> ขอใหม่ + ส่งพิกัดทันที
    if (document.visibilityState === 'visible' && watchId !== null) { wakeLock = null; keepScreenOn(); send(true); }
  });

  // ---------------------------------------------------------------- เสียงงานใหม่
  var bell = document.getElementById('rider-bell');
  var soundBtn = document.getElementById('rider-sound');
  var soundOn = false;
  function readIds() {
    var el = document.getElementById('rider-available-ids');
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }
  var known = new Set(readIds());

  function setSound(on) {
    soundOn = on;
    soundBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    soundBtn.classList.toggle('btn-primary', !on);
    soundBtn.classList.toggle('btn-outline-ink', on);
    soundBtn.innerHTML = on ? '<i class="bi bi-volume-up"></i><span>เสียงเปิดอยู่</span>' : '<i class="bi bi-volume-mute"></i><span>เปิดเสียง</span>';
  }
  soundBtn.addEventListener('click', function () {
    if (soundOn) { setSound(false); return; }
    bell.play().then(function () { bell.pause(); bell.currentTime = 0; setSound(true); }).catch(function () { setSound(false); });
  });

  document.body.addEventListener('htmx:afterSettle', function (event) {
    var id = event.detail.target && event.detail.target.id;
    if (id === 'rider-status') syncWithStatus();
    if (id === 'rider-jobs' || id === 'rider-status') {
      var ids = readIds();
      var fresh = ids.filter(function (x) { return !known.has(x); });
      known = new Set(ids);
      if (fresh.length && soundOn) { bell.currentTime = 0; bell.play().catch(function () {}); }
      fillProofForms();
    }
  });

  syncWithStatus();
})();
