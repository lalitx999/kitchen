"""ตรวจรูปที่ผู้ใช้อัปโหลด (สลิป, รูปส่งของ) ใช้ร่วมกันทุก app"""
import io

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
CONTENT_TYPES = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


class InvalidImage(Exception):
    """ข้อความแสดงให้ผู้ใช้เห็นได้"""


def read_uploaded_image(uploaded, *, max_bytes: int) -> tuple[bytes, str]:
    """คืน (ข้อมูลไฟล์, นามสกุล) ถ้าเป็นรูป JPG/PNG/WEBP จริงและไม่ใหญ่เกิน · อ่านจบแล้ว seek(0) ให้"""
    if uploaded is None:
        raise InvalidImage('กรุณาเลือกรูป')
    if uploaded.size > max_bytes:
        raise InvalidImage(f'รูปใหญ่เกิน {max_bytes // (1024 * 1024)} MB')
    data = uploaded.read()
    uploaded.seek(0)
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()  # เป็นรูปจริง ไม่ใช่ไฟล์อื่นที่ตั้งชื่อ .jpg
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise InvalidImage('ไฟล์นี้ไม่ใช่รูปภาพ (ใช้ JPG / PNG)') from exc
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImage('รองรับเฉพาะรูป JPG, PNG, WEBP')
    return data, ALLOWED_FORMATS[fmt]
