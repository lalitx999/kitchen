"""
ตะกร้าเก็บใน session (ยังไม่ต้องล็อกอินก็ใส่ของได้)
เก็บแค่ id + จำนวน + ตัวเลือก ราคาคิดใหม่จากฐานข้อมูลทุกครั้ง (ไม่เชื่อราคาจากเบราว์เซอร์)
"""
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from apps.catalog.selectors import menu_selector

SESSION_KEY = 'cart_v1'


class CartError(Exception):
    """ข้อความแสดงให้ลูกค้าเห็นได้"""


def _lines(session) -> list[dict]:
    return session.get(SESSION_KEY, {}).get('lines', [])


def _save(session, lines: list[dict]) -> None:
    session[SESSION_KEY] = {'lines': lines}
    session.modified = True


def _line_key(item_id: str, option_ids: list[str], note: str) -> str:
    # เมนูเดียวกัน ตัวเลือกเดียวกัน หมายเหตุเดียวกัน = รวมเป็นบรรทัดเดียว
    raw = f'{item_id}|{",".join(sorted(option_ids))}|{note.strip()}'
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def count(session) -> int:
    return sum(line['qty'] for line in _lines(session))


def add(session, *, item, option_ids: list[str], qty: int, note: str = '') -> None:
    if not item.is_available:
        raise CartError(f'{item.name} หมดแล้ว')
    valid_options = {str(o.pk) for o in item.options.all()}
    option_ids = sorted({str(o) for o in option_ids})
    if not set(option_ids) <= valid_options:
        raise CartError('ตัวเลือกไม่ถูกต้อง ลองเปิดเมนูใหม่')
    qty = max(1, min(int(qty), settings.CART_MAX_QUANTITY_PER_LINE))
    note = (note or '').strip()[:120]

    lines = _lines(session)
    key = _line_key(str(item.pk), option_ids, note)
    for line in lines:
        if line['key'] == key:
            line['qty'] = min(line['qty'] + qty, settings.CART_MAX_QUANTITY_PER_LINE)
            break
    else:
        if len(lines) >= settings.CART_MAX_LINES:
            raise CartError('ตะกร้าเต็มแล้ว')
        lines.append({'key': key, 'item_id': str(item.pk), 'option_ids': option_ids, 'qty': qty, 'note': note})
    _save(session, lines)


def set_quantity(session, key: str, qty: int) -> None:
    lines = _lines(session)
    if qty <= 0:
        lines = [line for line in lines if line['key'] != key]
    else:
        for line in lines:
            if line['key'] == key:
                line['qty'] = min(qty, settings.CART_MAX_QUANTITY_PER_LINE)
    _save(session, lines)


def clear(session) -> None:
    session.pop(SESSION_KEY, None)


@dataclass
class PricedLine:
    key: str
    item: object
    options: list
    qty: int
    note: str
    unit_price: Decimal
    line_total: Decimal
    available: bool


@dataclass
class PricedCart:
    lines: list[PricedLine] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((line.line_total for line in self.lines if line.available), Decimal('0'))

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def has_unavailable(self) -> bool:
        return any(not line.available for line in self.lines)

    @property
    def item_count(self) -> int:
        return sum(line.qty for line in self.lines)


def priced_cart(session, branch) -> PricedCart:
    raw = _lines(session)
    if not raw or branch is None:
        return PricedCart()
    items = menu_selector.items_for_pricing(branch, {line['item_id'] for line in raw})
    priced = PricedCart()
    kept = []
    for line in raw:
        item = items.get(line['item_id'])
        if item is None:
            continue  # เมนูถูกลบไปแล้ว ตัดทิ้งจากตะกร้าเงียบๆ
        options_by_id = {str(o.pk): o for o in item.options.all()}
        options = [options_by_id[o] for o in line['option_ids'] if o in options_by_id]
        unit = item.price + sum((o.extra_price for o in options), Decimal('0'))
        priced.lines.append(PricedLine(
            key=line['key'], item=item, options=options, qty=line['qty'], note=line['note'],
            unit_price=unit, line_total=unit * line['qty'], available=item.is_available,
        ))
        kept.append(line)
    if len(kept) != len(raw):
        _save(session, kept)
    return priced
