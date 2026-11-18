"""
แปลงลิงก์ Google Maps ที่เจ้าของร้านวาง -> พิกัด (lat, lng)

รับได้ 3 แบบ:
1. ลิงก์เต็ม  https://www.google.com/maps/place/.../@13.75,100.50,17z/data=...!3d13.7563!4d100.5018
2. ลิงก์สั้นจากปุ่ม "แชร์" ในแอป  https://maps.app.goo.gl/xxxx  (ต้องตามลิงก์ไปดูปลายทาง)
3. ตัวเลขพิกัดตรงๆ  13.7563, 100.5018

ลิงก์สั้นต้องเรียกออกไปที่ Google ใน request (ข้อยกเว้นของกฎ "ห้ามเรียก API ภายนอกใน request"):
ใช้เฉพาะหน้าตั้งค่าร้านของเจ้าของ นานๆ ครั้ง ต้องรู้ผลทันทีว่าลิงก์ใช้ได้ไหม จึงตั้ง timeout สั้นและ
ตามได้เฉพาะโดเมนของ Google (กัน SSRF: ห้ามพาเซิร์ฟเวอร์ไปเรียกที่อื่น)
"""
import re
from decimal import Decimal
from urllib.parse import unquote, urljoin, urlsplit

import requests

TIMEOUT_SECONDS = 5
MAX_REDIRECTS = 5
SHORT_HOSTS = {'maps.app.goo.gl', 'goo.gl'}
GOOGLE_HOST = re.compile(r'^(?:[a-z0-9-]+\.)*google\.(?:com|co\.th)$')
_NUM = r'(-?\d{1,3}\.\d+)'
_RAW_COORDS = re.compile(rf'^\s*{_NUM}\s*,\s*{_NUM}\s*$')
# เรียงจากแม่นสุด: !3d!4d = หมุดของสถานที่ · @lat,lng = จุดกึ่งกลางจอ (ใช้เป็นทางสุดท้าย)
_URL_PATTERNS = [
    re.compile(rf'!3d{_NUM}!4d{_NUM}'),
    re.compile(rf'[?&](?:q|query|ll|destination|daddr|center)=(?:loc:)?\s*{_NUM}\s*,\s*\+?{_NUM}'),
    re.compile(rf'/(?:search|place|dir)/(?:[^/]*/)*?{_NUM}\s*,\s*\+?{_NUM}'),
    re.compile(rf'@{_NUM},{_NUM}'),
]


class InvalidMapsLink(Exception):
    """ข้อความแสดงให้เจ้าของร้านเห็นได้"""


def _valid(lat: Decimal, lng: Decimal) -> tuple[Decimal, Decimal]:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        raise InvalidMapsLink('พิกัดในลิงก์ไม่ถูกต้อง')
    return lat.quantize(Decimal('0.000001')), lng.quantize(Decimal('0.000001'))


def coordinates_from_url(url: str) -> tuple[Decimal, Decimal] | None:
    text = unquote(unquote(url)).replace('+', ' ')
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return _valid(Decimal(match.group(1)), Decimal(match.group(2)))
    return None


def _is_google(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    return parts.scheme == 'https' and (GOOGLE_HOST.match(host) is not None or host in SHORT_HOSTS)


def _expand_short_link(url: str) -> str:
    """ตาม redirect ทีละขั้นเอง (ไม่ใช้ allow_redirects) เพื่อตรวจทุกปลายทางว่ายังเป็นของ Google"""
    current = url
    for _ in range(MAX_REDIRECTS):
        try:
            response = requests.get(current, allow_redirects=False, timeout=TIMEOUT_SECONDS, stream=True,
                                    headers={'User-Agent': 'Mozilla/5.0 (TMPP shop settings)'})
            response.close()
        except requests.RequestException as exc:
            raise InvalidMapsLink('เปิดลิงก์สั้นไม่ได้ตอนนี้ ลองใหม่ หรือใช้ลิงก์เต็มจาก Google Maps') from exc
        location = response.headers.get('Location')
        if response.status_code not in (301, 302, 303, 307, 308) or not location:
            return current
        current = urljoin(current, location)
        if not _is_google(current):
            raise InvalidMapsLink('ลิงก์นี้ไม่ได้พาไปที่ Google Maps')
        if coordinates_from_url(current):
            return current
    return current


def parse_maps_input(value: str) -> tuple[str, Decimal, Decimal] | None:
    """
    คืน (ลิงก์ที่จะเก็บ, lat, lng) · ว่าง = None (ลบพิกัด)
    วางตัวเลขพิกัดมา -> สร้างลิงก์ Google Maps ให้ เพื่อให้ลูกค้า/ไรเดอร์กดนำทางได้เหมือนกัน
    """
    value = (value or '').strip()
    if not value:
        return None
    raw = _RAW_COORDS.match(value)
    if raw:
        lat, lng = _valid(Decimal(raw.group(1)), Decimal(raw.group(2)))
        return f'https://www.google.com/maps?q={lat},{lng}', lat, lng
    if not value.startswith(('http://', 'https://')):
        value = 'https://' + value
    value = value.replace('http://', 'https://', 1)
    if not _is_google(value):
        raise InvalidMapsLink('วางลิงก์จาก Google Maps เท่านั้น (google.com/maps หรือ maps.app.goo.gl)')
    if len(value) > 500:
        raise InvalidMapsLink('ลิงก์ยาวเกินไป ใช้ปุ่ม "แชร์" ในแอป Google Maps เพื่อได้ลิงก์สั้น')

    coords = coordinates_from_url(value)
    if coords is None and (urlsplit(value).hostname or '').lower() in SHORT_HOSTS:
        coords = coordinates_from_url(_expand_short_link(value))
    if coords is None:
        raise InvalidMapsLink(
            'ลิงก์นี้ไม่มีพิกัด: ใน Google Maps ให้กดค้างที่ตำแหน่งร้านจนมีหมุดแดง แล้วกด "แชร์" คัดลอกลิงก์มาวาง'
        )
    return value, coords[0], coords[1]
