/* หน้างานไรเดอร์ (templates/delivery/job.html)
   1. ระยะ/เวลาถึงเป้าหมาย: คิดจาก GPS ของมือถือ (rider.js ส่ง event tmpp:rider-position มา)
      เป้าหมาย = ร้าน (ก่อนรับอาหาร) หรือบ้านลูกค้า (กำลังไปส่ง) อ่านจาก #job-target ในแผ่นล่าง (เปลี่ยนเองหลังกดรับอาหาร)
      ระยะเป็นเส้นตรง เวลาประมาณจากความเร็วมอเตอร์ไซค์ในเมือง · ไม่มี GPS = บอกตรงๆ ไม่เดาตำแหน่ง
   2. แผนที่ (มีเฉพาะเมื่อตั้ง GOOGLE_MAPS_API_KEY): หมุดร้าน, บ้านลูกค้า, ไรเดอร์ + เส้นตรงไรเดอร์ -> เป้าหมาย
      ไม่ใช้ Directions API (คิดเงินทุกครั้ง) ให้ปุ่ม "นำทาง" เปิดแอป Google Maps แทน */
(function () {
  var CITY_SPEED_KMH = 25;      // ความเร็วเฉลี่ยในเมืองรวมไฟแดง ใช้ประมาณเวลาเท่านั้น
  var GPS_STALE_MS = 60000;
  var config = JSON.parse(document.getElementById('job-config').textContent);
  var me = null, meAt = 0;
  var map = null, meMarker = null, line = null, fitted = false;

  function distanceM(a, b) {
    var R = 6371000, toRad = Math.PI / 180;
    var dLat = (b.lat - a.lat) * toRad, dLng = (b.lng - a.lng) * toRad;
    var h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toRad) * Math.cos(b.lat * toRad) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function target() {
    var el = document.getElementById('job-target');
    if (!el || !el.dataset.lat) return null;
    return { lat: Number(el.dataset.lat), lng: Number(el.dataset.lng), kind: el.dataset.kind };
  }

  function setText(selector, text) {
    document.querySelectorAll(selector).forEach(function (el) { el.textContent = text; });
  }

  function render() {
    var t = target();
    if (!t) { setText('[data-eta-note]', 'ร้านยังไม่ได้ตั้งพิกัด ใช้ปุ่มโทรถามทางแทน'); return; }
    if (!me) return;   // ยังรอ GPS: ข้อความเริ่มต้นในแผ่นล่างบอกอยู่แล้ว
    var meters = distanceM(me, t);
    var km = meters / 1000;
    setText('[data-eta-distance]', km < 1 ? Math.round(meters) + ' ม.' : km.toFixed(1) + ' กม.');
    setText('[data-eta-minutes]', String(Math.max(1, Math.round(km / CITY_SPEED_KMH * 60))));
    var stale = Date.now() - meAt > GPS_STALE_MS;
    setText('[data-eta-note]', stale
      ? 'ตำแหน่งไม่อัปเดตเกิน 1 นาที: เปิด GPS และเปิดแอปค้างไว้'
      : 'ระยะเป็นเส้นตรง เวลาเป็นค่าประมาณ ถนนจริงอาจไกลกว่า');
    drawLine(t);
  }

  // ---------------------------------------------------------------- แผนที่
  function pin(iconClass, kind) {
    var el = document.createElement('div');
    el.className = 'map-pin map-pin-' + kind;
    el.innerHTML = '<i class="bi ' + iconClass + '"></i>';
    return el;
  }

  function drawLine(t) {
    if (!map || !me) return;
    var pos = { lat: me.lat, lng: me.lng };
    if (meMarker) meMarker.position = pos;
    if (line) line.setPath([pos, { lat: t.lat, lng: t.lng }]);
    if (!fitted) {
      var bounds = new google.maps.LatLngBounds();
      bounds.extend(pos); bounds.extend({ lat: t.lat, lng: t.lng });
      map.fitBounds(bounds, 64);
      fitted = true;
    }
  }

  window.tmppInitRiderMap = async function () {
    var el = document.getElementById('rider-map');
    if (!el || !window.google) return;
    var { Map, Polyline } = await google.maps.importLibrary('maps');
    var { AdvancedMarkerElement } = await google.maps.importLibrary('marker');
    var t = target();
    var center = t || config.customer;
    map = new Map(el, {
      center: center, zoom: 15, mapId: window.TMPP_MAP_ID || 'DEMO_MAP_ID',
      streetViewControl: false, mapTypeControl: false, fullscreenControl: false, clickableIcons: false,
      gestureHandling: 'greedy',   // นิ้วเดียวเลื่อนแผนที่ได้ (มือถือ)
    });
    if (config.shop) new AdvancedMarkerElement({ map: map, position: config.shop, content: pin('bi-shop', 'shop'), title: 'ร้าน' });
    new AdvancedMarkerElement({ map: map, position: config.customer, content: pin('bi-house-door', 'customer'), title: 'บ้านลูกค้า' });
    meMarker = new AdvancedMarkerElement({ map: map, position: me || center, content: pin('bi-scooter', 'me'), title: 'ฉัน' });
    // สีเส้นมาจากตัวแปรธีม (ไม่ hardcode สี)
    var brand = getComputedStyle(document.documentElement).getPropertyValue('--tm-brand').trim();
    line = new Polyline({ map: map, path: [], strokeColor: brand, strokeOpacity: 0.9, strokeWeight: 4, geodesic: true });
    render();
  };

  document.addEventListener('tmpp:rider-position', function (event) {
    me = event.detail; meAt = Date.now();
    render();
  });
  // แผ่นล่างโหลดใหม่ (เช่น กดรับอาหารแล้ว เป้าหมายเปลี่ยนเป็นบ้านลูกค้า) -> คิดใหม่ + จัดแผนที่ใหม่
  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!event.detail.target || event.detail.target.id !== 'job-sheet') return;
    var el = document.getElementById('job-target');
    if (el && el.dataset.kind !== document.body.dataset.jobTarget) { fitted = false; document.body.dataset.jobTarget = el.dataset.kind; }
    render();
  });
  setInterval(render, 15000);   // อัปเดตข้อความ "ตำแหน่งไม่อัปเดต" แม้ GPS เงียบ
  document.body.dataset.jobTarget = (document.getElementById('job-target') || { dataset: {} }).dataset.kind || '';
  render();
})();
