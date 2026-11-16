"""
พิกัดไรเดอร์แบบสด
- มือถือไรเดอร์ส่งพิกัดทุก ~5 วิ ระหว่างเปิดรับงาน -> เก็บ "ตำแหน่งล่าสุด" ใน cache (Redis บน server)
  ไม่เขียนฐานข้อมูลทุกครั้ง · เขียน RiderProfile.current_location ไม่เกินนาทีละครั้ง
- เวลาใช้ของเซิร์ฟเวอร์เสมอ ไม่เชื่อเวลาจากมือถือ
- ไม่มีพิกัดสำรอง: ไม่รับ 0,0 / นอกช่วง / GPS แม่นไม่พอ
หมายเหตุเครื่องพัฒนา: ไม่มี Redis ใช้ cache ในหน่วยความจำ ซึ่ง runserver (process เดียว) ใช้ร่วมกันได้
แต่ server จริงที่มีหลาย worker ต้องใช้ Redis (มีใน docker-compose ของ production)
"""
import math
from dataclasses import asdict, dataclass
from datetime import datetime

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.utils import timezone

from ..models import RiderProfile

LOCATION_TTL_SECONDS = 30 * 60   # จำตำแหน่งล่าสุด 30 นาที
STALE_AFTER_SECONDS = 120        # เก่ากว่า 2 นาที = สัญญาณอาจหาย บอกลูกค้าตรงๆ
DB_SYNC_SECONDS = 60
MIN_INTERVAL_SECONDS = 2         # ส่งถี่กว่านี้ไม่บันทึก (กันมือถือรัว)
MAX_ACCURACY_METERS = 1000


class LocationError(Exception):
    """ข้อความแสดงบนหน้าไรเดอร์ได้"""


@dataclass(frozen=True)
class LiveLocation:
    lat: float
    lng: float
    accuracy: float | None
    heading: float | None
    speed: float | None
    updated_at: str  # ISO (เวลาเซิร์ฟเวอร์)

    def age_seconds(self, now=None) -> int:
        updated = datetime.fromisoformat(self.updated_at)
        return max(0, int(((now or timezone.now()) - updated).total_seconds()))

    def is_stale(self, now=None) -> bool:
        return self.age_seconds(now) > STALE_AFTER_SECONDS


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    """ระยะเส้นตรงบนผิวโลก (เมตร) ใช้แสดงผล ไม่ต้องถาม DB ทุก 5 วิ"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _number(raw, name, *, low, high, required=False):
    if raw in (None, ''):
        if required:
            raise LocationError(f'ไม่มีค่า {name}')
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise LocationError(f'{name} ต้องเป็นตัวเลข') from exc
    if value != value or not (low <= value <= high):  # value != value คือ NaN
        raise LocationError(f'{name} อยู่นอกช่วง')
    return value


def parse(data) -> dict:
    lat = _number(data.get('lat'), 'lat', low=-90, high=90, required=True)
    lng = _number(data.get('lng'), 'lng', low=-180, high=180, required=True)
    if lat == 0 and lng == 0:
        raise LocationError('พิกัด 0,0 ไม่ใช่ตำแหน่งจริง')
    accuracy = _number(data.get('accuracy'), 'accuracy', low=0, high=100000)
    if accuracy is not None and accuracy > MAX_ACCURACY_METERS:
        raise LocationError(f'GPS ยังไม่แม่นพอ (±{int(accuracy)} ม.) ลองออกไปที่โล่ง')
    return {
        'lat': round(lat, 7), 'lng': round(lng, 7), 'accuracy': accuracy,
        'heading': _number(data.get('heading'), 'heading', low=0, high=360),
        'speed': _number(data.get('speed'), 'speed', low=0, high=100),  # เมตร/วินาที
    }


def _key(rider_id) -> str:
    return f'rider:loc:{rider_id}'


def save(profile: RiderProfile, payload: dict) -> LiveLocation:
    previous = get(profile.user_id)
    if previous and previous.age_seconds() < MIN_INTERVAL_SECONDS:
        return previous
    location = LiveLocation(updated_at=timezone.now().isoformat(), **payload)
    cache.set(_key(profile.user_id), asdict(location), LOCATION_TTL_SECONDS)
    # cache.add สำเร็จครั้งเดียวต่อช่วงเวลา -> เขียน DB อย่างมากนาทีละครั้ง
    if cache.add(f'rider:loc-db:{profile.user_id}', 1, DB_SYNC_SECONDS):
        RiderProfile.objects.filter(pk=profile.pk).update(
            current_location=Point(payload['lng'], payload['lat'], srid=4326), location_updated_at=timezone.now(),
        )
    return location


def get(rider_id) -> LiveLocation | None:
    raw = cache.get(_key(rider_id))
    if not raw:
        return None
    try:
        return LiveLocation(**raw)
    except TypeError:
        return None


def clear(rider_id) -> None:
    cache.delete(_key(rider_id))
