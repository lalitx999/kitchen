from django.db.models import QuerySet

from ..models import AuditLog


def recent_logs(limit: int = 20) -> QuerySet[AuditLog]:
    return (
        AuditLog.objects.select_related('actor')
        .only('id', 'action', 'target_type', 'target_label', 'created_at', 'actor__full_name')
        .order_by('-created_at')[:limit]
    )


def list_logs(*, action: str = '', query: str = ''):
    from django.db.models import Q

    qs = AuditLog.objects.select_related('actor').order_by('-created_at')
    if action:
        qs = qs.filter(action__startswith=action)
    query = (query or '').strip()
    if query:
        qs = qs.filter(Q(target_label__icontains=query) | Q(actor__full_name__icontains=query) | Q(target_id=query))
    return qs


ACTION_GROUPS = [
    ('', 'ทั้งหมด'), ('order.', 'ออเดอร์'), ('slip.', 'สลิป'), ('menu', 'เมนู'), ('category.', 'หมวด'),
    ('branch.', 'ร้าน'), ('staff.', 'พนักงาน'), ('customer.', 'ลูกค้า'), ('rider_payout.', 'จ่ายค่าส่ง'),
]
