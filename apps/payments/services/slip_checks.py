"""
ตรวจข้อมูลที่อ่านจากสลิปเทียบกับออเดอร์และบัญชีร้าน (ต้องตรงครบทุกข้อ)
1. มีรหัสธุรกรรม และไม่เคยใช้  2. โอนเข้าบัญชีร้าน  3. ชื่อผู้รับตรง  4. ยอดตรงทุกสตางค์
"""
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings

from .easyslip_client import SlipData, SlipProblem

NAME_PREFIXES = (
    'นางสาว', 'น.ส.', 'นาย', 'นาง', 'บริษัท', 'บจก.', 'หจก.', 'ร้าน',
    'mr.', 'mrs.', 'ms.', 'miss', 'mr', 'mrs', 'ms',
)
MIN_NAME_CHARS = 4
MIN_VISIBLE_DIGITS = 4


class ShopNotConfigured(Exception):
    """ร้านยังไม่ได้ตั้งบัญชี/ชื่อผู้รับ -> ห้ามอนุมัติอัตโนมัติ ส่งให้เจ้าของตรวจเอง"""


def _digits(value) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def masked_account_matches(masked: str, actual: str) -> bool:
    """
    เลขบัญชีในสลิปถูกปิดบัง เช่น xxx-x-x8346-x · เทียบชิดขวาทีละหลัก
    ทุกหลักที่เห็นต้องตรง และต้องเห็นอย่างน้อย 4 หลัก
    """
    pattern = ''.join(ch.lower() for ch in str(masked or '') if ch.isdigit() or ch.lower() == 'x')
    target = _digits(actual)
    if not pattern or not target:
        return False
    visible = 0
    for slip_char, real_char in zip(reversed(pattern), reversed(target)):
        if slip_char == 'x':
            continue
        if slip_char != real_char:
            return False
        visible += 1
    return visible >= MIN_VISIBLE_DIGITS


def shop_accounts() -> list[tuple[str, str]]:
    accounts = []
    if _digits(settings.SHOP_BANK_ACCOUNT):
        accounts.append((settings.SHOP_BANK_CODE.strip(), _digits(settings.SHOP_BANK_ACCOUNT)))
    if _digits(settings.PROMPTPAY_ID):
        accounts.append(('', _digits(settings.PROMPTPAY_ID)))
    return accounts


def receiver_is_shop(slip: SlipData) -> bool:
    accounts = shop_accounts()
    if not accounts:
        raise ShopNotConfigured('ยังไม่ได้ตั้งบัญชีรับเงินของร้าน')
    for masked in slip.receiver_accounts:
        for bank_code, number in accounts:
            if bank_code and slip.receiver_bank_code and bank_code != slip.receiver_bank_code:
                continue
            if masked_account_matches(masked, number):
                return True
    return False


def _normalize_name(value) -> str:
    text = str(value or '').strip().lower()
    for prefix in NAME_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    # เก็บสระ/วรรณยุกต์ไทย (Unicode หมวด M) ไว้ ไม่อย่างนั้นชื่อต่างกันจะดูเหมือนกัน
    return ''.join(ch for ch in text if ch.isalnum() or unicodedata.category(ch).startswith('M'))


def receiver_name_matches(slip_names, shop_names) -> bool:
    """ไม่สนคำนำหน้า/ช่องว่าง/ตัวพิมพ์ · ธนาคารบางแห่งตัดชื่อยาว จึงยอมให้เป็นส่วนต้นของกันได้ (>= 4 ตัว)"""
    for raw in slip_names or []:
        slip = _normalize_name(raw)
        if len(slip) < MIN_NAME_CHARS:
            continue
        for shop in (_normalize_name(n) for n in shop_names):
            if len(shop) >= MIN_NAME_CHARS and (slip == shop or shop.startswith(slip) or slip.startswith(shop)):
                return True
    return False


def check_against_order(slip: SlipData, *, expected_total: Decimal, trans_ref_used) -> Decimal:
    """
    คืนยอดเงินที่อ่านได้ ถ้าผ่านทุกข้อ
    SlipProblem = ไม่ผ่าน (บอกลูกค้า) · ShopNotConfigured = ส่งเจ้าของตรวจ
    trans_ref_used: ฟังก์ชันเช็คว่ารหัสธุรกรรมนี้เคยอนุมัติแล้วหรือยัง
    """
    if not slip.trans_ref:
        raise SlipProblem('ไม่พบรหัสอ้างอิงธุรกรรมในสลิป')
    if slip.is_duplicate or trans_ref_used(slip.trans_ref):
        raise SlipProblem('สลิปนี้ถูกใช้ไปแล้ว')
    if not receiver_is_shop(slip):
        raise SlipProblem('สลิปนี้ไม่ได้โอนเข้าบัญชีของร้าน')
    shop_names = settings.SHOP_ACCOUNT_NAMES
    if not [n for n in shop_names if len(_normalize_name(n)) >= MIN_NAME_CHARS]:
        raise ShopNotConfigured('ยังไม่ได้ตั้งชื่อบัญชีผู้รับของร้าน')
    if not receiver_name_matches(slip.receiver_names, shop_names):
        raise SlipProblem('ชื่อผู้รับในสลิปไม่ตรงกับบัญชีของร้าน')
    try:
        amount = Decimal(str(slip.amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SlipProblem('อ่านยอดเงินจากสลิปไม่ได้') from exc
    if amount != expected_total:
        raise SlipProblem(f'ยอดในสลิป ({amount} บาท) ไม่ตรงกับยอดที่ต้องจ่าย ({expected_total} บาท)')
    return amount
