import json

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_safe, require_http_methods, require_POST

from apps.accounts.models import Role
from apps.catalog.selectors import menu_selector
from apps.core.decorators import role_required

from .forms import CheckoutForm
from .services import cart_service, order_service, pricing_service
from .selectors import order_selector

customer_required = role_required(Role.CUSTOMER)


def _branch():
    return menu_selector.get_storefront_branch()


def _toast(response: HttpResponse, message: str, level: str = 'success') -> HttpResponse:
    # HX-Trigger: ให้ JS ฝั่งหน้าเว็บแสดง toast และปิด modal (ดู static/js/app.js)
    # ต้อง ensure_ascii=True: header HTTP เป็น ASCII ถ้าใส่ภาษาไทยตรงๆ Django จะเข้ารหัส MIME แล้ว HTMX อ่าน JSON ไม่ได้
    response['HX-Trigger'] = json.dumps({'tmpp:toast': {'message': message, 'level': level}}, ensure_ascii=True)
    return response


# --------------------------------------------------------------------------- เลือกเมนู
@require_safe
def item_sheet(request, item_id):
    """HTMX: เนื้อหา modal เลือกตัวเลือก/จำนวน ของเมนูหนึ่ง"""
    branch = _branch()
    item = menu_selector.get_branch_item(branch, item_id) if branch else None
    if item is None or not item.is_available:
        return _toast(HttpResponse(status=204), 'เมนูนี้หมดแล้ว', 'warning')
    return render(request, 'orders/_item_sheet.html', {'item': item})


@require_POST
def cart_add(request):
    branch = _branch()
    item = menu_selector.get_branch_item(branch, request.POST.get('item_id')) if branch else None
    try:
        if item is None:
            raise cart_service.CartError('ไม่พบเมนู')
        cart_service.add(
            request.session, item=item, option_ids=request.POST.getlist('option_ids'),
            qty=int(request.POST.get('qty') or 1), note=request.POST.get('note', ''),
        )
    except (cart_service.CartError, ValueError) as exc:
        message = str(exc) if isinstance(exc, cart_service.CartError) else 'จำนวนไม่ถูกต้อง'
        return _toast(render(request, 'orders/_cart_badges.html', {'cart_count': cart_service.count(request.session)}), message, 'warning')
    response = render(request, 'orders/_cart_badges.html', {'cart_count': cart_service.count(request.session)})
    return _toast(response, f'เพิ่ม {item.name} ลงตะกร้าแล้ว')


# --------------------------------------------------------------------------- ตะกร้า
def _cart_context(request):
    branch = _branch()
    cart = cart_service.priced_cart(request.session, branch)
    return {'cart': cart, 'branch': branch, 'shop': menu_selector.shop_status(branch)}


@require_safe
def cart_page(request):
    return render(request, 'orders/cart.html', _cart_context(request))


@require_POST
def cart_update(request):
    """HTMX: เปลี่ยนจำนวน / ลบ แล้วคืนเนื้อหาตะกร้าใหม่ทั้งก้อน + ตัวเลขบนไอคอนตะกร้า"""
    try:
        qty = int(request.POST.get('qty', 0))
    except ValueError:
        qty = 0
    cart_service.set_quantity(request.session, request.POST.get('key', ''), qty)
    context = _cart_context(request)
    context['cart_count'] = cart_service.count(request.session)
    return render(request, 'orders/_cart_body.html', {**context, 'oob_badges': True})


# --------------------------------------------------------------------------- ชำระเงิน / สั่ง
@customer_required
@require_http_methods(['GET', 'POST'])
def checkout(request):
    context = _cart_context(request)
    cart = context['cart']
    if cart.is_empty:
        messages.info(request, 'ตะกร้ายังว่าง เลือกเมนูก่อน')
        return redirect('core:home')

    user = request.user
    form = CheckoutForm(request.POST or None, initial={'recipient_name': user.full_name, 'recipient_phone': user.phone})
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            order = order_service.place_order(
                customer=user, branch=context['branch'], cart=cart,
                details=order_service.DeliveryDetails(
                    recipient_name=data['recipient_name'], recipient_phone=data['recipient_phone'],
                    address_text=data['address_text'], address_note=data['address_note'],
                    latitude=data['latitude'], longitude=data['longitude'], note=data['note'],
                ),
            )
        except order_service.OrderError as exc:
            form.add_error(None, str(exc))
        else:
            cart_service.clear(request.session)
            messages.success(request, f'สร้างออเดอร์ {order.order_number} แล้ว')
            return redirect('orders:detail', order_id=order.pk)

    context.update({
        'form': form,
        'saved_addresses': order_selector.saved_addresses(user),
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'google_maps_map_id': settings.GOOGLE_MAPS_MAP_ID,
        'shop_location': context['branch'].location if context['branch'] else None,
    })
    return render(request, 'orders/checkout.html', context)


@customer_required
@require_POST
def checkout_quote(request):
    """HTMX: คิดค่าส่งทันทีที่ได้พิกัด (ราคาจริงคิดซ้ำอีกครั้งตอนกดสั่ง)"""
    context = _cart_context(request)
    quote, error = None, ''
    try:
        point = pricing_service.make_point(request.POST.get('latitude'), request.POST.get('longitude'))
        quote = pricing_service.quote_delivery(context['branch'], point)
    except pricing_service.InvalidLocation as exc:
        error = str(exc)
    return render(request, 'orders/_quote.html', {**context, 'quote': quote, 'error': error,
                                                  'max_km': context['branch'].max_delivery_km if context['branch'] else None})


# --------------------------------------------------------------------------- ออเดอร์ของฉัน
@customer_required
@require_safe
def order_list(request):
    orders = list(order_selector.customer_orders(request.user)[:50])
    active = [o for o in orders if o.is_active]
    past = [o for o in orders if not o.is_active]
    return render(request, 'orders/order_list.html', {'active_orders': active, 'past_orders': past})


@customer_required
@require_safe
def order_detail(request, order_id):
    order = order_selector.get_customer_order(request.user, order_id)
    # import ในฟังก์ชัน กัน import วน (payments/delivery ใช้ orders)
    from apps.delivery.selectors import job_selector
    from apps.payments.selectors import slip_selector

    return render(request, 'orders/order_detail.html', {
        'order': order, **slip_selector.payment_context(order), 'tracking': job_selector.tracking_for_order(order),
    })


@customer_required
@require_safe
def order_tracking(request, order_id):
    """HTMX ทุก 10 วิ ระหว่างกำลังไปส่ง: ระยะไรเดอร์ถึงบ้าน + อายุของตำแหน่ง"""
    from apps.delivery.selectors import job_selector

    order = order_selector.get_customer_order(request.user, order_id)
    return render(request, 'orders/_tracking.html', {'order': order, 'tracking': job_selector.tracking_for_order(order)})


@customer_required
@require_safe
def order_status(request, order_id):
    """
    HTMX polling: ถ้าสถานะเปลี่ยน ส่ง event ให้หน้าเว็บเล่นเสียงแจ้งลูกค้า แล้วโหลดหน้าใหม่
    (ข้อมูลหลายส่วนเปลี่ยนพร้อมกัน) · ไม่มี JS ก็ยังโหลดใหม่ได้ด้วย HX-Refresh ตอนเสียงปิด
    """
    order = order_selector.get_customer_order_status(request.user, order_id)
    if order.status != request.GET.get('current'):
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'tmpp-order-changed'
        return response
    return HttpResponse(status=204)


@customer_required
@require_POST
def order_cancel(request, order_id):
    order = order_selector.get_customer_order(request.user, order_id)
    try:
        order_service.cancel_by_customer(order, request.user)
    except order_service.OrderError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, f'ยกเลิกออเดอร์ {order.order_number} แล้ว')
    return redirect('orders:detail', order_id=order.pk)
