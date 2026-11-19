/* จอครัว: เสียงแจ้งออเดอร์ใหม่ + กันจอดับ (เสียงจัดการโดย sound.js)
   - แตะหน้าจอครั้งแรก = ปลดล็อกเสียง (เบราว์เซอร์บังคับ) · ปุ่มลำโพงบน header เปิด/ปิดเสียงได้
   - มีออเดอร์ใหม่เข้ามา (id ที่ไม่เคยเห็น) -> ดังทันที (เหมือนระบบเดิม)
   - ยังมีออเดอร์ใหม่ที่ไม่มีใครกดรับ -> ดังซ้ำทุก 60 วินาที (ครัวเสียงดัง อาจไม่ได้ยินครั้งแรก)
   - กดรับครบทุกใบ -> หยุดเสียงทันที */
(function () {
  var sound = window.TmppSound;
  if (!document.getElementById('kds-board')) return;   // หน้าอื่นของครัว (เมนู/วันนี้) ไม่มีบอร์ด ไม่ต้องเล่นเสียง
  var wakeLock = null;
  var known = new Set(readIds());
  var REMIND_MS = 60000;

  function readIds() {
    var el = document.getElementById('kds-new-ids');
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }

  async function keepScreenOn() {
    // กันแท็บเล็ตในครัวจอดับ (ไม่รองรับก็ไม่เป็นไร)
    try { if ('wakeLock' in navigator && !wakeLock) wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { wakeLock = null; }
  }
  sound.onChange(function (on) { if (on) keepScreenOn(); });

  // บอร์ดถูกโหลดใหม่ -> เทียบ id ออเดอร์ใหม่
  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!event.detail.target || event.detail.target.id !== 'kds-board') return;
    var ids = readIds();
    var fresh = ids.filter(function (id) { return !known.has(id); });
    known = new Set(ids);
    document.title = (ids.length ? '(' + ids.length + ') ' : '') + 'จอครัว';
    if (fresh.length) sound.play('order');
    else if (!ids.length) sound.stop('order');
  });

  setInterval(function () { if (readIds().length) sound.play('order'); }, REMIND_MS);

  // กลับมาที่แท็บ: ขอกันจอดับใหม่ (เบราว์เซอร์ปล่อยเองเมื่อสลับแอป)
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { wakeLock = null; if (sound.enabled()) keepScreenOn(); }
  });
})();


/* ---------------------------------------------------------------- M14 ทุกหน้าของครัว */
(function () {
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  // นาฬิกาบนหัวจอ + ตัวจับเวลาบนใบออเดอร์ นับทุกวินาทีในเบราว์เซอร์ (ไม่ต้องถามเซิร์ฟเวอร์)
  // หัวใบเปลี่ยนสีเองเมื่อรอครบเกณฑ์ ไม่ต้องรอบอร์ดโหลดใหม่ 5 วิ
  function tick() {
    var now = new Date();
    document.querySelectorAll('[data-clock]').forEach(function (el) {
      el.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
    });
    document.querySelectorAll('[data-since]').forEach(function (head) {
      var since = Date.parse(head.dataset.since);
      if (isNaN(since)) return;
      var secs = Math.max(0, Math.floor((now.getTime() - since) / 1000));
      var mins = Math.floor(secs / 60);
      var timer = head.querySelector('[data-timer]');
      if (timer) timer.textContent = (mins >= 100 ? mins : pad(mins)) + ':' + pad(secs % 60);
      var level = mins >= Number(head.dataset.late) ? 'late' : (mins >= Number(head.dataset.warn) ? 'warn' : 'ok');
      head.classList.remove('kds-level-ok', 'kds-level-warn', 'kds-level-late');
      head.classList.add('kds-level-' + level);
    });
  }
  setInterval(tick, 1000);
  document.addEventListener('DOMContentLoaded', tick);
  document.body.addEventListener('htmx:afterSettle', tick);

  // ปุ่มเต็มจอ: ซ่อนแถบเบราว์เซอร์บนแท็บเล็ต (iPhone ไม่รองรับ -> ไม่แสดงปุ่ม)
  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.querySelector('[data-fullscreen]');
    if (!btn || !document.fullscreenEnabled) return;
    btn.classList.remove('d-none');
    btn.addEventListener('click', function () {
      if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
      else document.documentElement.requestFullscreen().catch(function () {});
    });
    document.addEventListener('fullscreenchange', function () {
      btn.querySelector('i').className = 'bi ' + (document.fullscreenElement ? 'bi-fullscreen-exit' : 'bi-arrows-fullscreen');
    });
  });

  // ยกเลิกออเดอร์: ปุ่ม X บนใบ -> หน้าต่างเลือกเหตุผล -> ส่งไปที่ URL ของใบนั้น แล้วบอร์ดโหลดใหม่
  var cancelUrl = null;
  document.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-cancel-url]');
    var modalEl = document.getElementById('kds-cancel');
    if (!btn || !modalEl || !window.bootstrap) return;
    cancelUrl = btn.dataset.cancelUrl;
    modalEl.querySelector('[data-cancel-number]').textContent = btn.dataset.cancelNumber;
    window.dispatchEvent(new CustomEvent('kds-cancel-open'));
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  });
  document.addEventListener('submit', function (event) {
    var form = event.target.closest('[data-cancel-form]');
    if (!form) return;
    event.preventDefault();
    var reason = form.querySelector('input[name="reason"]').value.trim();
    if (!cancelUrl || !reason || !window.htmx) return;
    htmx.ajax('POST', cancelUrl, { source: form, target: '#kds-board', swap: 'innerHTML', values: { action: 'cancel', reason: reason } })
      .then(function () { bootstrap.Modal.getOrCreateInstance(document.getElementById('kds-cancel')).hide(); });
  });
})();
