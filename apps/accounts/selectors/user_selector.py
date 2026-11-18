from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404

from ..models import STAFF_ROLES, Role, User


def list_staff_accounts() -> QuerySet[User]:
    # ดึง rider_profile มาด้วยใน query เดียว (กัน N+1 ตอนแสดงทะเบียนรถ/สถานะในตาราง)
    return (
        User.objects.filter(role__in=STAFF_ROLES)
        .select_related('rider_profile', 'branch')
        .only(
            'id', 'email', 'full_name', 'phone', 'role', 'is_active', 'last_login', 'created_at', 'branch_id',
            'branch__id', 'branch__name',
            'rider_profile__id', 'rider_profile__vehicle_plate', 'rider_profile__is_online',
        )
        .order_by('role', 'full_name')
    )


def get_staff_account(user_id) -> User:
    return get_object_or_404(User.objects.select_related('rider_profile', 'branch'), pk=user_id, role__in=STAFF_ROLES)


def count_users_by_role() -> dict[str, int]:
    counts = {role: 0 for role in Role.values}
    rows = User.objects.filter(is_active=True).values('role').annotate(total=Count('id'))
    for row in rows:
        counts[row['role']] = row['total']
    return counts


def email_exists(email: str) -> bool:
    return User.objects.filter(email__iexact=email.strip()).exists()


def list_customers(query: str = ''):
    """ลูกค้า + จำนวนออเดอร์ที่ส่งสำเร็จ + ยอดรวม (query เดียว ไม่วนนับทีละคน)"""
    from django.db.models import Max, Q, Sum

    done = Q(orders__status='COMPLETED')
    qs = (
        User.objects.filter(role=Role.CUSTOMER)
        .annotate(
            completed_orders=Count('orders', filter=done),
            total_spent=Sum('orders__total', filter=done),
            last_order_at=Max('orders__created_at'),
        )
        .only('id', 'email', 'full_name', 'phone', 'is_active', 'created_at', 'google_sub')
    )
    query = (query or '').strip()
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
    return qs.order_by('-created_at')


def get_customer(user_id) -> User:
    return get_object_or_404(User, pk=user_id, role=Role.CUSTOMER)
