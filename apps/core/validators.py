import re

from django.core.exceptions import ValidationError

_THAI_PHONE = re.compile(r'^0\d{9}$')


def normalize_thai_phone(value: str) -> str:
    """เหลือแต่ตัวเลข: '081-234-5678' -> '0812345678'"""
    return re.sub(r'\D', '', value or '')


def validate_thai_phone(value: str) -> None:
    if not _THAI_PHONE.match(value or ''):
        raise ValidationError('เบอร์โทรต้องเป็นตัวเลข 10 หลัก ขึ้นต้นด้วย 0')
