def console_badges(request):
    """ตัวเลขบนเมนู Console (สลิปรอตรวจ) — query เฉพาะหน้า /console/ ของเจ้าของร้าน"""
    user = getattr(request, 'user', None)
    if not request.path.startswith('/console/') or not getattr(user, 'is_authenticated', False) or user.role != 'OWNER':
        return {}
    from apps.payments.selectors import slip_selector

    return {'pending_slip_count': slip_selector.pending_review_count()}
