/* จอครัว: เสียงแจ้งออเดอร์ใหม่ + กันจอดับ (เสียงจัดการโดย sound.js)
   - แตะหน้าจอครั้งแรก = ปลดล็อกเสียง (เบราว์เซอร์บังคับ) · ปุ่มลำโพงบน header เปิด/ปิดเสียงได้
   - มีออเดอร์ใหม่เข้ามา (id ที่ไม่เคยเห็น) -> ดังทันที (เหมือนระบบเดิม)
   - ยังมีออเดอร์ใหม่ที่ไม่มีใครกดรับ -> ดังซ้ำทุก 60 วินาที (ครัวเสียงดัง อาจไม่ได้ยินครั้งแรก)
   - กดรับครบทุกใบ -> หยุดเสียงทันที */
(function () {
  var sound = window.TmppSound;
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
