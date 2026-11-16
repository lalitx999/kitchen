"""
QR พร้อมเพย์แบบระบุยอด (มาตรฐาน EMVCo / Thai QR Payment)
ลูกค้าสแกนแล้วแอปธนาคารใส่ยอดให้เอง ลดการโอนผิดยอด
"""
import base64
import io
from decimal import Decimal, InvalidOperation

import qrcode
from django.conf import settings

PROMPTPAY_AID = 'A000000677010111'


class PromptPayNotConfigured(Exception):
    pass


def _field(tag: str, value: str) -> str:
    return f'{tag}{len(value):02d}{value}'


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode('ascii'):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f'{crc:04X}'


def _proxy(promptpay_id: str) -> str:
    digits = ''.join(ch for ch in promptpay_id if ch.isdigit())
    if len(digits) == 10 and digits.startswith('0'):
        return _field('01', '0066' + digits[1:])   # เบอร์มือถือ: 08x -> 00668x
    if len(digits) == 13:
        return _field('02', digits)                # เลขประจำตัวประชาชน / นิติบุคคล
    if len(digits) == 15:
        return _field('03', digits)                # e-Wallet ID
    raise PromptPayNotConfigured('PROMPTPAY_ID ต้องเป็นเบอร์ 10 หลัก เลขบัตร 13 หลัก หรือ e-Wallet 15 หลัก')


def build_payload(promptpay_id: str, amount) -> str:
    try:
        value = Decimal(str(amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('ยอดเงินไม่ถูกต้อง') from exc
    if value <= 0:
        raise ValueError('ยอดเงินต้องมากกว่า 0')
    merchant = _field('00', PROMPTPAY_AID) + _proxy(promptpay_id)
    payload = ''.join([
        _field('00', '01'),           # payload format
        _field('01', '12'),           # 12 = QR ใช้ครั้งเดียว (ระบุยอด)
        _field('29', merchant),
        _field('53', '764'),          # THB
        _field('54', f'{value:.2f}'),
        _field('58', 'TH'),
        '6304',                       # CRC ต่อท้าย
    ])
    return payload + _crc16_ccitt(payload)


def qr_data_uri(amount) -> str:
    if not settings.PROMPTPAY_ID:
        raise PromptPayNotConfigured('ร้านยังไม่ได้ตั้งค่าพร้อมเพย์')
    image = qrcode.make(build_payload(settings.PROMPTPAY_ID, amount), box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


def masked_promptpay_id() -> str:
    digits = ''.join(ch for ch in settings.PROMPTPAY_ID if ch.isdigit())
    return f'{"x" * max(0, len(digits) - 4)}{digits[-4:]}' if digits else ''
