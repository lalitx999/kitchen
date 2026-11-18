/* หน้า checkout: หาพิกัดจัดส่ง (GPS / ที่อยู่เดิม / หมุดบนแผนที่) แล้วให้ HTMX คิดค่าส่ง
   ไม่มีพิกัดสำรอง: ถ้าหาตำแหน่งไม่ได้ แสดงวิธีแก้ ไม่เดาตำแหน่งให้ */
(function () {
  var latInput = document.getElementById('id_latitude');
  var lngInput = document.getElementById('id_longitude');
  var statusEl = document.getElementById('location-status');
  var marker = null;
  var map = null;

  function setStatus(html) { statusEl.innerHTML = html; }

  function setLocation(lat, lng, source) {
    latInput.value = Number(lat).toFixed(7);
    lngInput.value = Number(lng).toFixed(7);
    setStatus('<span class="text-action"><i class="bi bi-check-circle me-1"></i>ปักหมุดแล้ว' + (source ? ' (' + source + ')' : '') + '</span>');
    if (map && marker) {
      var pos = { lat: Number(lat), lng: Number(lng) };
      marker.position = pos;
      map.panTo(pos);
    }
    document.body.dispatchEvent(new CustomEvent('tmpp:location'));
  }

  document.getElementById('use-my-location').addEventListener('click', function () {
    if (!navigator.geolocation) {
      setStatus('<span class="text-danger">เบราว์เซอร์นี้หาตำแหน่งไม่ได้ ลองเปิดด้วย Chrome หรือ Safari</span>');
      return;
    }
    var spinner = document.getElementById('locating');
    spinner.classList.remove('d-none');
    navigator.geolocation.getCurrentPosition(function (pos) {
      spinner.classList.add('d-none');
      if (pos.coords.accuracy > 500) {
        setStatus('<span class="text-warning">ตำแหน่งคลาดเคลื่อนมาก (' + Math.round(pos.coords.accuracy) + ' ม.) ลองออกไปที่โล่งแล้วกดใหม่</span>');
      }
      setLocation(pos.coords.latitude, pos.coords.longitude, 'GPS ±' + Math.round(pos.coords.accuracy) + ' ม.');
    }, function (err) {
      spinner.classList.add('d-none');
      var msg = err.code === 1
        ? 'ยังไม่ได้อนุญาตให้ใช้ตำแหน่ง: กดรูปแม่กุญแจข้างช่อง URL แล้วเปิด "ตำแหน่ง" จากนั้นกดใหม่'
        : 'หาตำแหน่งไม่สำเร็จ ลองเปิด GPS ของมือถือแล้วกดใหม่';
      setStatus('<span class="text-danger">' + msg + '</span>');
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });
  });

  document.querySelectorAll('[data-saved-address]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.getElementById('id_address_text').value = btn.dataset.text;
      var note = document.getElementById('id_address_note');
      if (note) note.value = btn.dataset.note || '';
      setLocation(btn.dataset.lat, btn.dataset.lng, 'ที่อยู่เดิม');
    });
  });

  // กลับมาหน้านี้หลังฟอร์มไม่ผ่าน: มีพิกัดอยู่แล้ว -> คิดค่าส่งให้เลย
  document.addEventListener('DOMContentLoaded', function () {
    if (latInput.value && lngInput.value) document.body.dispatchEvent(new CustomEvent('tmpp:location'));
  });

  // Google Maps (มีเฉพาะเมื่อตั้ง GOOGLE_MAPS_API_KEY)
  window.tmppInitAddressMap = async function () {
    var el = document.getElementById('address-map');
    if (!el || !window.google) return;
    var { Map } = await google.maps.importLibrary('maps');
    var { AdvancedMarkerElement } = await google.maps.importLibrary('marker');
    var start = latInput.value ? { lat: Number(latInput.value), lng: Number(lngInput.value) } : window.TMPP_SHOP;
    if (!start) { el.innerHTML = '<div class="p-3 small text-muted-tm">ร้านยังไม่ได้ตั้งพิกัด</div>'; return; }
    map = new Map(el, { center: start, zoom: 16, mapId: window.TMPP_MAP_ID || 'DEMO_MAP_ID', streetViewControl: false, mapTypeControl: false });
    marker = new AdvancedMarkerElement({ map: map, position: start, gmpDraggable: true, title: 'ตำแหน่งจัดส่ง' });
    marker.addListener('dragend', function () { setLocation(marker.position.lat, marker.position.lng, 'หมุดบนแผนที่'); });
    map.addListener('click', function (e) { setLocation(e.latLng.lat(), e.latLng.lng(), 'หมุดบนแผนที่'); });
  };
})();
