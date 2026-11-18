"""
คิดค่าส่งจากระยะทาง (ฝั่งเซิร์ฟเวอร์เท่านั้น)
ระยะ = เส้นตรงบนผิวโลกจากพิกัดร้านถึงหมุดลูกค้า (PostGIS) ถนนจริงอาจไกลกว่านี้เล็กน้อย
"""
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point

from apps.catalog.models import Branch

TWO_PLACES = Decimal('0.01')


class InvalidLocation(Exception):
    pass


@dataclass(frozen=True)
class DeliveryQuote:
    distance_km: Decimal
    fee: Decimal
    rider_fee: Decimal
    within_range: bool


def make_point(latitude, longitude) -> Point:
    try:
        lat, lng = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise InvalidLocation('ไม่มีพิกัดจัดส่ง') from exc
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        raise InvalidLocation('พิกัดจัดส่งไม่ถูกต้อง')
    return Point(lng, lat, srid=4326)


def distance_km(branch: Branch, point: Point) -> Decimal:
    if branch.location is None:
        raise InvalidLocation('ร้านยังไม่ได้ตั้งพิกัด')
    # ให้ PostGIS คำนวณแบบ geodesic (เมตรจริงบนทรงรีโลก) ไม่ใช่องศา
    meters = (
        Branch.objects.filter(pk=branch.pk)
        .annotate(d=Distance('location', point))
        .values_list('d', flat=True)
        .get()
        .m
    )
    return (Decimal(str(meters)) / 1000).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def quote_for_distance(km: Decimal, branch: Branch) -> DeliveryQuote:
    """อัตราค่าส่งตั้งที่ร้าน (Console > ข้อมูลร้าน) · ลูกค้าจ่าย fee, ไรเดอร์ได้ rider_fee, ส่วนต่างเป็นของร้าน"""
    extra_km = max(Decimal('0'), km - branch.delivery_base_km)
    # กม.ที่เกินปัดขึ้นเป็นจำนวนเต็ม (เกิน 0.2 กม. ก็คิด 1 กม.) เหมือนระบบเดิม
    extra_units = Decimal(math.ceil(extra_km))
    fee = branch.delivery_base_fare + extra_units * branch.delivery_per_km_fare
    rider_fee = branch.rider_base_fare + extra_units * branch.rider_per_km_fare
    return DeliveryQuote(
        distance_km=km,
        fee=fee.quantize(TWO_PLACES),
        rider_fee=rider_fee.quantize(TWO_PLACES),
        within_range=km <= branch.max_delivery_km,
    )


def quote_delivery(branch: Branch, point: Point) -> DeliveryQuote:
    return quote_for_distance(distance_km(branch, point), branch)


@dataclass(frozen=True)
class FeeRow:
    km: int
    fee: Decimal
    rider_fee: Decimal

    @property
    def shop_fee(self) -> Decimal:
        return self.fee - self.rider_fee


def fee_table(branch: Branch) -> list[FeeRow]:
    """ตัวอย่างค่าส่งทุก 1 กม. ให้เจ้าของเห็นว่าใครได้เท่าไร (หน้าข้อมูลร้าน)"""
    rows = []
    top = int(min(branch.max_delivery_km, Decimal('15')))
    for km in range(1, max(top, 1) + 1):
        q = quote_for_distance(Decimal(km), branch)
        rows.append(FeeRow(km=km, fee=q.fee, rider_fee=q.rider_fee))
    return rows
