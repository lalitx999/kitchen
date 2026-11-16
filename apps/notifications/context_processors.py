from .selectors import notification_selector


def notifications(request):
    """ตัวเลขแจ้งเตือนที่ยังไม่อ่าน (1 query เบาๆ เฉพาะคนที่ล็อกอิน) + ค่าตั้งค่า push"""
    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return {}
    return {
        'unread_notifications': notification_selector.unread_count(user),
        'push_config': notification_selector.push_config(),
    }
