"""
คูปองส่วนลด: ตรวจเงื่อนไข + คิดส่วนลด (ที่เดียว ใช้ทั้งตอนกดใช้คูปองและตอนสั่งจริง)
- ส่วนลดคิดจากยอดอาหาร (ส่งฟรี = ลดเท่าค่าส่ง) และไม่เกินยอดที่ต้องจ่าย
- นับการใช้จากออเดอร์ที่ยังไม่ถูกยกเลิก (ไม่จ่ายจนหมดเวลา = คืนสิทธิ์ให้อัตโนมัติ)
- ตอนสั่งจริงล็อกแถวคูปอง (select_for_update) กันกดพร้อมกันจนเกินจำนวนที่ตั้ง
"""
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from ..models import Coupon, CouponKind, Order, OrderStatus

TWO = Decimal('0.01')
CODE_RE = re.compile(r'^[A-Z0-9_-]{3,30}$')


class CouponError(Exception):
    """ข้อความแสดงให้ลูกค้า/เจ้าของเห็นได้"""


@dataclass(frozen=True)
class CouponResult:
    coupon: Coupon
    discount: Decimal


def normalize_code(code: str) -> str:
    return re.sub(r'\s+', '', (code or '')).upper()


def _used(coupon: Coupon, customer=None) -> int:
    qs = Order.objects.filter(coupon=coupon).exclude(status=OrderStatus.CANCELLED)
    if customer is not None:
        qs = qs.filter(customer=customer)
    return qs.count()


def discount_for(coupon: Coupon, *, subtotal: Decimal, delivery_fee: Decimal | None) -> Decimal:
    if coupon.kind == CouponKind.FREE_DELIVERY:
        amount = delivery_fee or Decimal('0')
    elif coupon.kind == CouponKind.PERCENT:
        amount = (subtotal * coupon.value / Decimal('100')).quantize(TWO, rounding=ROUND_HALF_UP)
        if coupon.max_discount:
            amount = min(amount, coupon.max_discount)
    else:
        amount = min(coupon.value, subtotal)
    return max(Decimal('0'), amount).quantize(TWO)


def check(coupon: Coupon, *, customer, branch, subtotal: Decimal, delivery_fee: Decimal | None = None) -> CouponResult:
    now = timezone.now()
    if not coupon.is_active:
        raise CouponError('คูปองนี้ปิดใช้งานแล้ว')
    if coupon.starts_at and now < coupon.starts_at:
        raise CouponError(f'คูปองนี้ใช้ได้ตั้งแต่ {timezone.localtime(coupon.starts_at):%d/%m %H:%M} น.')
    if coupon.ends_at and now >= coupon.ends_at:
        raise CouponError('คูปองนี้หมดอายุแล้ว')
    if coupon.branch_id and branch is not None and coupon.branch_id != branch.pk:
        raise CouponError('คูปองนี้ใช้กับสาขาอื่น')
    if subtotal < coupon.min_subtotal:
        raise CouponError(f'สั่งอาหารอีก ฿{(coupon.min_subtotal - subtotal):,.0f} ถึงจะใช้คูปองนี้ได้')
    if coupon.usage_limit is not None and _used(coupon) >= coupon.usage_limit:
        raise CouponError('คูปองนี้ถูกใช้ครบจำนวนแล้ว')
    if coupon.per_customer_limit and customer is not None and customer.is_authenticated \
            and _used(coupon, customer) >= coupon.per_customer_limit:
        raise CouponError('คุณใช้คูปองนี้ครบสิทธิ์แล้ว')
    return CouponResult(coupon=coupon, discount=discount_for(coupon, subtotal=subtotal, delivery_fee=delivery_fee))


def find(code: str) -> Coupon:
    code = normalize_code(code)
    coupon = Coupon.objects.filter(code=code).first() if code else None
    if coupon is None:
        raise CouponError('ไม่พบคูปองนี้ ตรวจรหัสอีกครั้ง')
    return coupon


def apply(code: str, *, customer, branch, subtotal: Decimal, delivery_fee: Decimal | None = None) -> CouponResult:
    """ลูกค้ากดใช้คูปอง (ยังไม่สั่ง): ตรวจเงื่อนไขแล้วบอกส่วนลด"""
    return check(find(code), customer=customer, branch=branch, subtotal=subtotal, delivery_fee=delivery_fee)


def lock_and_check(code: str, *, customer, branch, subtotal: Decimal, delivery_fee: Decimal) -> CouponResult:
    """ตอนสั่งจริง: ต้องเรียกใน transaction.atomic() เดียวกับการสร้างออเดอร์"""
    assert transaction.get_connection().in_atomic_block, 'ต้องเรียกใน transaction'
    coupon = Coupon.objects.select_for_update().filter(code=normalize_code(code)).first()
    if coupon is None:
        raise CouponError('ไม่พบคูปองนี้ ตรวจรหัสอีกครั้ง')
    return check(coupon, customer=customer, branch=branch, subtotal=subtotal, delivery_fee=delivery_fee)


# --------------------------------------------------------------------------- เจ้าของร้าน (Console)
COUPON_FIELDS = ('code', 'name', 'kind', 'value', 'max_discount', 'min_subtotal', 'starts_at', 'ends_at',
                 'usage_limit', 'per_customer_limit', 'branch', 'show_in_checkout', 'is_active')


def _validate(data: dict, *, exclude_pk=None) -> dict:
    data = dict(data)
    data['code'] = normalize_code(data.get('code', ''))
    if not CODE_RE.match(data['code']):
        raise CouponError('รหัสคูปองใช้ A-Z, 0-9, - หรือ _ ยาว 3-30 ตัว')
    if Coupon.objects.filter(code=data['code']).exclude(pk=exclude_pk).exists():
        raise CouponError('มีคูปองรหัสนี้แล้ว')
    if data['kind'] == CouponKind.PERCENT and not (Decimal('0') < data['value'] <= Decimal('100')):
        raise CouponError('ส่วนลดเป็น % ต้องอยู่ระหว่าง 1-100')
    if data['kind'] == CouponKind.AMOUNT and data['value'] <= 0:
        raise CouponError('ใส่จำนวนเงินที่ลด')
    if data['kind'] == CouponKind.FREE_DELIVERY:
        data['value'] = Decimal('0')
    if data['kind'] != CouponKind.PERCENT:
        data['max_discount'] = None
    if data.get('starts_at') and data.get('ends_at') and data['ends_at'] <= data['starts_at']:
        raise CouponError('วันหมดอายุต้องหลังวันเริ่มใช้')
    return data


def create_coupon(data: dict) -> Coupon:
    return Coupon.objects.create(**_validate(data))


def update_coupon(coupon: Coupon, data: dict) -> dict:
    """คืน {field: [ก่อน, หลัง]} สำหรับ AuditLog"""
    data = _validate(data, exclude_pk=coupon.pk)
    changes = {}
    for field in COUPON_FIELDS:
        new = data.get(field)
        old = getattr(coupon, field)
        if old != new:
            changes[field] = [str(old if old is not None else ''), str(new if new is not None else '')]
            setattr(coupon, field, new)
    if changes:
        coupon.save()
    return changes


def set_active(coupon: Coupon, *, active: bool) -> bool:
    if coupon.is_active == active:
        return False
    coupon.is_active = active
    coupon.save(update_fields=['is_active', 'updated_at'])
    return True


def delete_coupon(coupon: Coupon) -> None:
    """ออเดอร์ที่เคยใช้ยังเก็บรหัสคูปองและส่วนลดไว้ (coupon_code, discount)"""
    coupon.delete()
