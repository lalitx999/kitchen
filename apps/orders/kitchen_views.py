"""
จอครัว (KDS) — ใช้ได้ทั้งพนักงานครัวและเจ้าของร้าน
หน้าแรกโหลดครั้งเดียว แล้ว HTMX ถาม /kitchen/board/ ทุก 5 วินาที (เฉพาะตอนแท็บเปิด)
"""
import json

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Role
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service, menu_service
from apps.console.services import audit_service
from apps.core.decorators import role_required

from .selectors import kitchen_selector
from .services import kitchen_service

kitchen_required = role_required(Role.KITCHEN, Role.OWNER)


def _toast(response, message, level='warning'):
    response['HX-Trigger'] = json.dumps({'tmpp:toast': {'message': message, 'level': level}}, ensure_ascii=True)
    return response


def _shop_context():
    branch = branch_service.get_or_create_main_branch()
    return {'branch': branch, 'shop': menu_selector.shop_status(branch)}


@kitchen_required
@require_GET
def kitchen_home(request):
    branch = branch_service.get_or_create_main_branch()
    categories, uncategorized = menu_selector.console_menu(branch)
    return render(request, 'orders/kitchen/home.html', {
        **kitchen_selector.board(), **_shop_context(),
        'menu_items': [item for c in categories for item in c.menu] + uncategorized,
    })


@kitchen_required
@require_GET
@never_cache
def kitchen_board(request):
    return render(request, 'orders/kitchen/_board.html', kitchen_selector.board())


@kitchen_required
@require_POST
def kitchen_action(request, order_id):
    order = kitchen_selector.get_kitchen_order(order_id)
    response = None
    try:
        if order is None:
            raise kitchen_service.KitchenError('ไม่พบออเดอร์')
        action = request.POST.get('action', '')
        if action == 'cancel':
            # เหตุผลมาจากกล่องถามของ HTMX (hx-prompt) หรือช่องในฟอร์ม
            reason = request.POST.get('reason') or request.headers.get('HX-Prompt', '')
            kitchen_service.cancel(order, actor=request.user, reason=reason)
            audit_service.record(request, action='order.cancel', target_type='order', target_id=order.pk,
                                 target_label=order.order_number, changes={'reason': reason})
        else:
            kitchen_service.apply_action(order, action, actor=request.user)
    except kitchen_service.KitchenError as exc:
        response = _toast(render(request, 'orders/kitchen/_board.html', kitchen_selector.board()), str(exc))
    return response or render(request, 'orders/kitchen/_board.html', kitchen_selector.board())


@kitchen_required
@require_POST
def kitchen_toggle_shop(request):
    """ครัวปิดรับออเดอร์ชั่วคราวได้ เช่น ออเดอร์ล้น ของหมด"""
    branch = branch_service.get_or_create_main_branch()
    is_open = request.POST.get('is_open') == '1'
    if is_open and branch.location is None:
        response = render(request, 'orders/kitchen/_shop_switch.html', _shop_context())
        return _toast(response, 'ร้านยังไม่ได้ตั้งพิกัด ให้เจ้าของร้านตั้งก่อน')
    if branch_service.set_open(branch, is_open=is_open):
        audit_service.record(request, action='branch.open' if is_open else 'branch.close', target_type='branch',
                             target_id=branch.pk, target_label=branch.name, changes={'is_open': [not is_open, is_open]})
    return render(request, 'orders/kitchen/_shop_switch.html', _shop_context())


@kitchen_required
@require_POST
def kitchen_toggle_item(request, item_id):
    """ปุ่ม "หมด/มีขาย" บนจอครัว"""
    branch = branch_service.get_or_create_main_branch()
    item = menu_selector.get_branch_item(branch, item_id)
    available = request.POST.get('available') == '1'
    if menu_service.set_available(item, available=available):
        audit_service.record(request, action='menu_item.available' if available else 'menu_item.sold_out',
                             target_type='menuitem', target_id=item.pk, target_label=item.name,
                             changes={'is_available': [not available, available]})
    return render(request, 'orders/kitchen/_menu_item.html', {'item': item})
