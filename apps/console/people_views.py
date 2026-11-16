"""Console: ค่าส่งไรเดอร์ (D3), ลูกค้า, บันทึกการแก้ไข"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_safe, require_POST

from apps.accounts.models import Role
from apps.accounts.selectors import user_selector
from apps.accounts.services import user_service
from apps.core.decorators import role_required
from apps.delivery.selectors import payout_selector
from apps.delivery.services import payout_service
from apps.orders.selectors import order_selector

from .selectors import audit_selector
from .services import audit_service

owner_required = role_required(Role.OWNER)


# --------------------------------------------------------------------------- ค่าส่งไรเดอร์
@owner_required
@require_safe
def rider_pay_list(request):
    return render(request, 'console/riders/pay_list.html', {
        'console_active': 'rider_pay', 'riders': payout_selector.riders_with_unpaid(),
    })


@owner_required
@require_safe
def rider_pay_detail(request, rider_id):
    rider = payout_selector.get_rider(rider_id)
    return render(request, 'console/riders/pay_detail.html', {
        'console_active': 'rider_pay', 'rider': rider,
        'unpaid_orders': payout_selector.unpaid_orders(rider),
        'unpaid_total': payout_selector.unpaid_total(rider),
        'history': payout_selector.payout_history(rider),
    })


@owner_required
@require_POST
def rider_pay_record(request, rider_id):
    rider = payout_selector.get_rider(rider_id)
    try:
        expected = Decimal(request.POST.get('expected_amount', ''))
        payout = payout_service.record_payout(rider, paid_by=request.user, expected_amount=expected,
                                              note=request.POST.get('note', ''))
    except (InvalidOperation, payout_service.PayoutError) as exc:
        messages.error(request, str(exc) if isinstance(exc, payout_service.PayoutError) else 'ยอดไม่ถูกต้อง')
    else:
        audit_service.record(request, action='rider_payout.create', target_type='rider_payout', target_id=payout.pk,
                             target_label=f'{rider.full_name} ฿{payout.amount}',
                             changes={'amount': [None, str(payout.amount)], 'jobs': [None, payout.job_count]})
        messages.success(request, f'บันทึกจ่ายค่าส่ง {rider.full_name} ฿{payout.amount:,.0f} ({payout.job_count} เที่ยว) แล้ว')
    return redirect('console:rider_pay_detail', rider_id=rider.pk)


# --------------------------------------------------------------------------- ลูกค้า
@owner_required
@require_safe
def customer_list(request):
    query = request.GET.get('q', '')
    page = Paginator(user_selector.list_customers(query), 30).get_page(request.GET.get('page'))
    return render(request, 'console/customers/list.html', {'console_active': 'users', 'page': page, 'query': query})


@owner_required
@require_safe
def customer_detail(request, user_id):
    customer = user_selector.get_customer(user_id)
    return render(request, 'console/customers/detail.html', {
        'console_active': 'users', 'customer': customer,
        'orders': list(order_selector.customer_orders(customer)[:30]),
    })


@owner_required
@require_POST
def customer_toggle_active(request, user_id):
    """ปิดบัญชีลูกค้าที่สั่งปลอม/ก่อกวน (เปิดคืนได้) · ประวัติออเดอร์ไม่หาย"""
    customer = user_selector.get_customer(user_id)
    active = request.POST.get('active') == '1'
    if user_service.set_account_active(customer, active=active):
        audit_service.record(request, action='customer.activate' if active else 'customer.deactivate',
                             target_type='user', target_id=customer.pk, target_label=customer.full_name,
                             changes={'is_active': [not active, active]})
        messages.info(request, f'{"เปิด" if active else "ปิด"}บัญชี {customer.full_name} แล้ว')
    return redirect('console:customer_detail', user_id=customer.pk)


# --------------------------------------------------------------------------- บันทึกการแก้ไข
@owner_required
@require_safe
def audit_list(request):
    action, query = request.GET.get('action', ''), request.GET.get('q', '')
    page = Paginator(audit_selector.list_logs(action=action, query=query), 50).get_page(request.GET.get('page'))
    return render(request, 'console/audit/list.html', {
        'console_active': 'audit', 'page': page, 'action': action, 'query': query,
        'groups': audit_selector.ACTION_GROUPS,
    })
