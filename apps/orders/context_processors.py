from .services import cart_service


def cart(request):
    # อ่านจาก session อย่างเดียว ไม่ query ฐานข้อมูล (ทุกหน้าเรียก)
    session = getattr(request, 'session', None)
    return {'cart_count': cart_service.count(session) if session is not None else 0}
