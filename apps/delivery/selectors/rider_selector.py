from ..models import RiderProfile


def get_profile(user) -> RiderProfile | None:
    # ดึงด้วย user_id ของคนที่ล็อกอินเท่านั้น ไม่รับ id จาก URL (ไรเดอร์ดูของคนอื่นไม่ได้)
    return RiderProfile.objects.filter(user_id=user.pk).first()
