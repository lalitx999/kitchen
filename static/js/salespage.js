/* เซลเพจ /about/: ส่วนต่างๆ เริ่มเบลอแล้วค่อยชัดเมื่อเลื่อนถึง (แนวเดียวกับต้นแบบ)
   - ใส่คลาส sp-reveal-ready ที่ <html> ก่อน ถึงจะเริ่มเบลอ: ไม่มี JS / เบราว์เซอร์เก่า = เห็นทุกอย่างชัดตามปกติ
   - มือถือตั้ง "ลดการเคลื่อนไหว" = ไม่เบลอ ไม่ขยับ
   - หัวเว็บกระจกฝ้า: เลื่อนลงแล้วเพิ่มเงาให้แยกจากเนื้อหา */
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reduce && 'IntersectionObserver' in window) {
    document.documentElement.classList.add('sp-reveal-ready');
    document.addEventListener('DOMContentLoaded', function () {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);   // ชัดแล้วไม่ต้องเบลอกลับ
        });
      }, { rootMargin: '0px 0px -12% 0px', threshold: 0.08 });
      document.querySelectorAll('[data-reveal]').forEach(function (el) { observer.observe(el); });
    });
  }

  var nav = null;
  function onScroll() {
    nav = nav || document.querySelector('.sp-nav');
    if (nav) nav.classList.toggle('is-scrolled', window.scrollY > 24);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  document.addEventListener('DOMContentLoaded', onScroll);
})();
