"""Console: ดูออเดอร์ทั้งหมด ค้นหา กรองสถานะ และยกเลิกพร้อมเหตุผล"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Role
from apps.core.decorators import role_required
from apps.orders.forms import CancelOrderForm
from apps.orders.models import OrderStatus
from apps.orders.selectors import order_selector
from apps.orders.services import order_service

from .services import audit_service

owner_required = role_required(Role.OWNER)


@owner_required
@require_GET
def order_list(request):
    status = request.GET.get('status', 'active')
    query = request.GET.get('q', '')
    page = Paginator(order_selector.console_orders(status=status, query=query), 30).get_page(request.GET.get('page'))
    return render(request, 'console/orders/list.html', {
        'console_active': 'orders', 'page': page, 'status': status, 'query': query,
        'counts': order_selector.status_counts(), 'statuses': OrderStatus.choices,
    })


@owner_required
@require_GET
def order_detail(request, order_id):
    order = order_selector.get_console_order(order_id)
    return render(request, 'console/orders/detail.html', {
        'console_active': 'orders', 'order': order, 'cancel_form': CancelOrderForm(),
    })


@owner_required
@require_POST
def order_cancel(request, order_id):
    order = order_selector.get_console_order(order_id)
    form = CancelOrderForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'กรุณาระบุเหตุผลที่ยกเลิก')
        return redirect('console:order_detail', order_id=order.pk)
    try:
        order_service.cancel_by_staff(order, request.user, form.cleaned_data['reason'])
    except order_service.OrderError as exc:
        messages.error(request, str(exc))
    else:
        audit_service.record(request, action='order.cancel', target_type='order', target_id=order.pk,
                             target_label=order.order_number,
                             changes={'status': [order.status, OrderStatus.CANCELLED], 'reason': form.cleaned_data['reason']})
        messages.info(request, f'ยกเลิก {order.order_number} แล้ว')
    return redirect('console:order_detail', order_id=order.pk)


@owner_required
@require_GET
def order_export(request):
    """ดาวน์โหลด CSV ออเดอร์ตามช่วงวันที่ (เปิดใน Excel ภาษาไทยได้ เพราะมี BOM)"""
    import csv
    from datetime import date, timedelta

    from django.http import StreamingHttpResponse
    from django.utils import timezone

    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get('start', ''))
        end = date.fromisoformat(request.GET.get('end', ''))
    except ValueError:
        start, end = today.replace(day=1), today
    if end < start or (end - start) > timedelta(days=366):
        messages.error(request, 'ช่วงวันที่ไม่ถูกต้อง (ไม่เกิน 1 ปี)')
        return redirect('console:orders')

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    header = ['เลขออเดอร์', 'สั่งเมื่อ', 'จ่ายเมื่อ', 'ส่งถึงเมื่อ', 'สถานะ', 'ค่าอาหาร', 'ค่าส่ง', 'รวม',
              'ส่วนของไรเดอร์', 'ระยะ(กม.)', 'ผู้รับ', 'เบอร์', 'บัญชีลูกค้า', 'ไรเดอร์', 'เหตุผลยกเลิก']

    def fmt(dt):
        return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M') if dt else ''

    def rows():
        yield '\ufeff'  # BOM ให้ Excel อ่าน UTF-8 ภาษาไทยถูก
        yield writer.writerow(header)
        for o in order_selector.export_rows(start, end):
            yield writer.writerow([
                o.order_number, fmt(o.created_at), fmt(o.paid_at), fmt(o.completed_at), o.get_status_display(),
                o.subtotal, o.delivery_fee, o.total, o.rider_fee, o.distance_km, o.recipient_name,
                o.recipient_phone, o.customer.email, o.rider.full_name if o.rider else '', o.cancelled_reason,
            ])

    audit_service.record(request, action='order.export', target_type='order', target_id='-',
                         target_label=f'{start} ถึง {end}')
    response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="tmpp-orders-{start}-{end}.csv"'
    return response
