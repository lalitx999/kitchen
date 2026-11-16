from django import template

register = template.Library()


@register.filter
def audit_change(value) -> str:
    """แสดงค่าใน AuditLog.changes: [ก่อน, หลัง] -> "ก่อน → หลัง" · ค่าเดี่ยว (เช่น เหตุผล) แสดงตรงๆ"""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        before, after = ('-' if v in (None, '') else v for v in value)
        return f'{before} → {after}'
    return str(value)


@register.filter
def ago_th(value) -> str:
    """เวลาที่ผ่านมาเป็นภาษาไทย: เมื่อสักครู่ / 5 นาทีที่แล้ว / 2 ชม.ที่แล้ว / 3 วันที่แล้ว"""
    from django.utils import timezone

    if not value:
        return ''
    seconds = max(0, int((timezone.now() - value).total_seconds()))
    if seconds < 60:
        return 'เมื่อสักครู่'
    if seconds < 3600:
        return f'{seconds // 60} นาทีที่แล้ว'
    if seconds < 86400:
        return f'{seconds // 3600} ชม.ที่แล้ว'
    if seconds < 7 * 86400:
        return f'{seconds // 86400} วันที่แล้ว'
    return timezone.localtime(value).strftime('%d/%m/%Y')
