"""สถานะไรเดอร์ (เปิด/ปิดรับงาน) — งานส่งของและพิกัดสดมาใน M6"""
from django.db import transaction
from django.utils import timezone

from ..models import RiderProfile


def create_rider_profile(user, *, vehicle_plate: str = '') -> RiderProfile:
    return RiderProfile.objects.create(user=user, vehicle_plate=vehicle_plate.strip().upper())


def ensure_rider_profile(user) -> RiderProfile:
    """บัญชีไรเดอร์ที่สร้างจากที่อื่น (เช่น Django Admin) อาจยังไม่มี profile -> สร้างให้"""
    profile, _ = RiderProfile.objects.get_or_create(user=user)
    return profile


def set_online(profile: RiderProfile, *, online: bool) -> RiderProfile:
    with transaction.atomic():
        # lock แถวกันกดรัวจากสองแท็บแล้วสถานะเพี้ยน
        profile = RiderProfile.objects.select_for_update().get(pk=profile.pk)
        if profile.is_online != online:
            profile.is_online = online
            profile.online_since = timezone.now() if online else None
            profile.save(update_fields=['is_online', 'online_since', 'updated_at'])
    return profile


def force_offline(user) -> None:
    RiderProfile.objects.filter(user=user, is_online=True).update(
        is_online=False, online_since=None, updated_at=timezone.now()
    )


def update_vehicle_plate(profile: RiderProfile, plate: str) -> None:
    profile.vehicle_plate = plate.strip().upper()
    profile.save(update_fields=['vehicle_plate', 'updated_at'])
