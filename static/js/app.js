/* ค่าเริ่มต้นของ HTMX ที่ใช้ทั้งเว็บ */
document.addEventListener('DOMContentLoaded', function () {
  if (!window.htmx) {
    // ยังไม่ได้รัน scripts/fetch_vendor.sh
    console.warn('HTMX ยังไม่ถูกโหลด: รัน bash scripts/fetch_vendor.sh');
    return;
  }
  // ให้ HTMX แสดงหน้า error ของเซิร์ฟเวอร์ (422 ฟอร์มไม่ผ่าน) แทนที่จะเงียบ
  htmx.config.responseHandling = [
    { code: '204', swap: false },
    { code: '[23]..', swap: true },
    { code: '422', swap: true },
    { code: '[45]..', swap: false, error: true },
  ];
  htmx.config.defaultSwapStyle = 'outerHTML';
});

/* toast แจ้งผล: server ส่ง HX-Trigger {"tmpp:toast": {"message", "level"}} */
document.addEventListener('tmpp:toast', function (event) {
  var detail = event.detail || {};
  var toastEl = document.getElementById('tm-toast');
  if (!toastEl || !window.bootstrap) return;
  toastEl.classList.remove('text-bg-success', 'text-bg-warning', 'text-bg-dark');
  toastEl.classList.add(detail.level === 'warning' ? 'text-bg-warning' : 'text-bg-dark');
  document.getElementById('tm-toast-body').textContent = detail.message || '';
  bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 2500 }).show();
  // เพิ่มลงตะกร้าเสร็จ -> ปิด modal เลือกตัวเลือก
  var sheet = document.getElementById('item-sheet');
  if (sheet && detail.level !== 'warning') bootstrap.Modal.getOrCreateInstance(sheet).hide();
});

/* โหลดเนื้อหา modal เมนูเสร็จ -> เปิด modal */
document.addEventListener('htmx:afterSwap', function (event) {
  if (event.detail.target && event.detail.target.id === 'item-sheet-body' && window.bootstrap) {
    bootstrap.Modal.getOrCreateInstance(document.getElementById('item-sheet')).show();
  }
});

/* หยุด polling ของ HTMX เมื่อแท็บถูกซ่อน ลดภาระเซิร์ฟเวอร์และแบตมือถือ
   ใช้คู่กับ hx-trigger="every 5s [document.visibilityState === 'visible']" */
function tmppRefreshVisible() {
  if (document.visibilityState !== 'visible' || !window.htmx) return;
  document.querySelectorAll('[data-refresh-on-visible]').forEach(function (el) { htmx.trigger(el, 'refresh'); });
}
document.addEventListener('visibilitychange', tmppRefreshVisible);
// แอปบนหน้าจอโฮม (iPhone) กลับมาจากพื้นหลังด้วยหน้าเก่าในหน่วยความจำ (bfcache) โดยไม่ยิง visibilitychange
window.addEventListener('pageshow', function (event) { if (event.persisted) tmppRefreshVisible(); });
window.addEventListener('focus', tmppRefreshVisible);
