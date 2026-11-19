"""Console: ข้อมูลร้าน (ชื่อ พิกัด เวลาเปิด-ปิด) และสวิตช์เปิด/ปิดรับออเดอร์"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import Role
from apps.catalog.forms import BranchForm
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service
from apps.core.decorators import role_required
from apps.orders.services import pricing_service

from .services import audit_service

owner_required = role_required(Role.OWNER)


RATE_FIELDS = ('delivery_base_km', 'delivery_base_fare', 'delivery_per_km_fare',
               'rider_base_fare', 'rider_per_km_fare', 'max_delivery_km')
KITCHEN_FIELDS = ('kitchen_warn_minutes', 'kitchen_late_minutes')


def _initial(branch):
    initial = {
        'name': branch.name, 'phone': branch.phone, 'address': branch.address,
        # ร้านเก่าที่มีพิกัดแต่ยังไม่มีลิงก์: แสดงเป็นตัวเลขพิกัด บันทึกครั้งต่อไปจะได้ลิงก์ให้เอง
        'maps_link': branch.maps_url or (f'{branch.location.y:.6f}, {branch.location.x:.6f}' if branch.location else ''),
        'opens_at': branch.opens_at, 'closes_at': branch.closes_at,
    }
    initial.update({f: getattr(branch, f) for f in RATE_FIELDS + KITCHEN_FIELDS})
    return initial


@owner_required
@require_http_methods(['GET', 'POST'])
def shop_settings(request):
    branch = branch_service.get_console_branch(request.session)
    if request.method == 'POST':
        form = BranchForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            changes = branch_service.update_branch(
                branch,
                latitude=data['latitude'], longitude=data['longitude'],
                images={f: data.get(f) for f in ('storefront_image', 'cover_image') if data.get(f)},
                remove_images=[f for f in ('storefront_image', 'cover_image') if data.get(f'remove_{f}')],
                **{k: data[k] for k in ('name', 'phone', 'address', 'maps_url', 'opens_at', 'closes_at') + RATE_FIELDS + KITCHEN_FIELDS},
            )
            if changes:
                audit_service.record(request, action='branch.update', target_type='branch', target_id=branch.pk,
                                     target_label=branch.name, changes=changes)
                messages.success(request, 'บันทึกข้อมูลร้านแล้ว')
            return redirect('console:shop')
    else:
        form = BranchForm(initial=_initial(branch))
    return render(request, 'console/shop.html', {
        'console_active': 'shop', 'form': form, 'branch': branch, 'shop': menu_selector.shop_status(branch),
        'fee_examples': pricing_service.fee_table(branch),
    })


@owner_required
@require_POST
def shop_toggle_open(request):
    """HTMX: เปิด/ปิดรับออเดอร์ทันที"""
    branch = branch_service.get_console_branch(request.session)
    is_open = request.POST.get('is_open') == '1'
    if is_open and branch.location is None:
        messages.error(request, 'ตั้งพิกัดร้านก่อน จึงจะเปิดรับออเดอร์ได้')
    elif branch_service.set_open(branch, is_open=is_open):
        audit_service.record(request, action='branch.open' if is_open else 'branch.close', target_type='branch',
                             target_id=branch.pk, target_label=branch.name, changes={'is_open': [not is_open, is_open]})
    return render(request, 'console/_shop_switch.html', {'branch': branch, 'shop': menu_selector.shop_status(branch)})
