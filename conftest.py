"""ตั้งค่าที่ทุก test ใช้ร่วมกัน"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    # ไฟล์ที่ test อัปโหลด (รูปเมนู, สลิป) ลงโฟลเดอร์ชั่วคราว ไม่ปนกับไฟล์จริงของเครื่อง
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'private_media'
