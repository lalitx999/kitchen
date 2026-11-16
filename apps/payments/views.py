from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Role
from apps.core.decorators import role_required
from apps.orders.selectors import order_selector

from .selectors import slip_selector
from .services import slip_service


@role_required(Role.CUSTOMER)
@require_POST
def upload_slip(request, order_id):
    order = order_selector.get_customer_order(request.user, order_id)
    try:
        slip_service.submit_slip(order, request.user, request.FILES.get('slip'))
    except slip_service.SlipError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'ได้รับสลิปแล้ว กำลังตรวจสอบ')
    return redirect('orders:detail', order_id=order.pk)


@require_GET
@never_cache
def slip_image(request, slip_id):
    """ส่งรูปสลิปจาก private storage หลังตรวจสิทธิ์ (ไม่มี URL สาธารณะ)"""
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    slip = slip_selector.get_slip_for_viewer(request.user, slip_id)
    response = FileResponse(slip.image.open('rb'))
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
