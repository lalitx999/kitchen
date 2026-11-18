def console_badges(request):
    """ตัวเลขบนเมนู Console (สลิปรอตรวจ) — query เฉพาะหน้า /console/ ของเจ้าของร้าน"""
    user = getattr(request, 'user', None)
    if not request.path.startswith('/console/') or not getattr(user, 'is_authenticated', False) or user.role != 'OWNER':
        return {}
    from apps.catalog.selectors import menu_selector
    from apps.payments.selectors import slip_selector

    branches = menu_selector.all_branches()
    return {
        'pending_slip_count': slip_selector.pending_review_count(),
        # ตัวเลือกสาขาบน sidebar: เมนู/ข้อมูลร้าน/จอครัว ทำงานกับสาขานี้ (1 query)
        'console_branches': branches,
        'console_branch': menu_selector.console_branch(request.session, branches),
    }
