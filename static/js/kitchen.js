/* จอครัว: เสียงแจ้งออเดอร์ใหม่ + กันจอดับ
   - เบราว์เซอร์ไม่ให้เล่นเสียงจนกว่าจะมีการกด จึงต้องกด "เปิดเสียง" หนึ่งครั้งทุกครั้งที่เปิดจอ
   - มีออเดอร์ใหม่เข้ามา (id ที่ไม่เคยเห็น) -> ดังทันที
   - ยังมีออเดอร์ใหม่ที่ไม่มีใครกดรับ -> ดังซ้ำทุก 60 วินาที (ครัวเสียงดัง อาจไม่ได้ยินครั้งแรก) */
(function () {
  var bell = document.getElementById('kds-bell');
  var button = document.getElementById('kds-sound');
  var enabled = false;
  var wakeLock = null;
  var known = new Set(readIds());
  var REMIND_MS = 60000;

  function readIds() {
    var el = document.getElementById('kds-new-ids');
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }

  function ring() {
    if (!enabled || !bell) return;
    bell.currentTime = 0;
    bell.play().catch(function () { /* ถูกบล็อก: ให้กดเปิดเสียงใหม่ */ setButton(false); });
  }

  function setButton(on) {
    enabled = on;
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
    button.classList.toggle('btn-primary', !on);
    button.classList.toggle('btn-outline-ink', on);
    button.innerHTML = on
      ? '<i class="bi bi-volume-up"></i><span>เสียงเปิดอยู่</span>'
      : '<i class="bi bi-volume-mute"></i><span>เปิดเสียง</span>';
  }

  async function keepScreenOn() {
    // กันแท็บเล็ตในครัวจอดับ (ไม่รองรับก็ไม่เป็นไร)
    try { if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { wakeLock = null; }
  }

  button.addEventListener('click', function () {
    if (enabled) { setButton(false); return; }
    bell.muted = false;
    bell.play().then(function () { bell.pause(); bell.currentTime = 0; setButton(true); keepScreenOn(); })
      .catch(function () { setButton(false); });
  });

  // บอร์ดถูกโหลดใหม่ -> เทียบ id ออเดอร์ใหม่
  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!event.detail.target || event.detail.target.id !== 'kds-board') return;
    var ids = readIds();
    var fresh = ids.filter(function (id) { return !known.has(id); });
    known = new Set(ids);
    document.title = (ids.length ? '(' + ids.length + ') ' : '') + 'จอครัว';
    if (fresh.length) ring();
  });

  setInterval(function () { if (readIds().length) ring(); }, REMIND_MS);

  // กลับมาที่แท็บ: ขอกันจอดับใหม่ (เบราว์เซอร์ปล่อยเองเมื่อสลับแอป)
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && enabled && !wakeLock) keepScreenOn();
  });
})();
