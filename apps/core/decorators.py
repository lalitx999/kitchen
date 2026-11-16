"""
ตัวตรวจสิทธิ์ที่ทุก view ต้องใช้ (CLAUDE.md กฎข้อ 4)

ยังไม่ล็อกอิน      -> ส่งไปหน้าล็อกอิน แล้วกลับมาหน้าเดิม
ล็อกอินแล้วแต่ผิดบทบาท -> 403 (ไม่ redirect เพื่อไม่ให้วนลูประหว่างหน้า)
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles: str):
    if not roles:
        raise ValueError('role_required ต้องระบุอย่างน้อย 1 บทบาท')
    allowed = frozenset(roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            # role มาจาก User model ใน M1 ใช้ getattr กันพังถ้าไม่มี field
            if not user.is_active or getattr(user, 'role', None) not in allowed:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
