"""Console: คิวสลิปที่ต้องตรวจเอง (EasySlip ใช้ไม่ได้ / โหมด MANUAL)"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Role
from apps.core.decorators import role_required
from apps.payments.selectors import slip_selector
from apps.payments.services import slip_service

from .services import audit_service

owner_required = role_required(Role.OWNER)


@owner_required
@require_GET
def slip_queue(request):
    return render(request, 'console/slips/queue.html', {
        'console_active': 'slips',
        'queue': slip_selector.review_queue(),
        'recent': slip_selector.recent_reviewed(limit=15),
    })


@owner_required
@require_POST
def slip_approve(request, slip_id):
    slip = slip_selector.get_reviewable(slip_id)
    try:
        slip_service.approve_manually(slip, request.user, trans_ref=request.POST.get('trans_ref', ''))
    except slip_service.SlipError as exc:
        messages.error(request, str(exc))
    else:
        audit_service.record(request, action='slip.approve', target_type='slip', target_id=slip.pk,
                             target_label=slip.order.order_number, changes={'status': [slip.status, 'APPROVED']})
        messages.success(request, f'อนุมัติสลิป {slip.order.order_number} แล้ว ออเดอร์เข้าครัว')
    return redirect('console:slips')


@owner_required
@require_POST
def slip_reject(request, slip_id):
    slip = slip_selector.get_reviewable(slip_id)
    reason = request.POST.get('reason', '')
    try:
        slip_service.reject_manually(slip, request.user, reason=reason)
    except slip_service.SlipError as exc:
        messages.error(request, str(exc))
    else:
        audit_service.record(request, action='slip.reject', target_type='slip', target_id=slip.pk,
                             target_label=slip.order.order_number, changes={'status': [slip.status, 'REJECTED'], 'reason': reason})
        messages.info(request, f'ปฏิเสธสลิป {slip.order.order_number} แล้ว ลูกค้าแนบใหม่ได้')
    return redirect('console:slips')
