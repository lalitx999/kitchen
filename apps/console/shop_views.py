"""Console: ข้อมูลร้าน (ชื่อ พิกัด เวลาเปิด-ปิด) และสวิตช์เปิด/ปิดรับออเดอร์"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import Role
from apps.catalog.forms import BranchForm
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service
from apps.core.decorators import role_required

from .services import audit_service

owner_required = role_required(Role.OWNER)


def _coords_text(branch):
    return f'{branch.location.y:.6f}, {branch.location.x:.6f}' if branch.location else ''


@owner_required
@require_http_methods(['GET', 'POST'])
def shop_settings(request):
    branch = branch_service.get_or_create_main_branch()
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            data = {k: form.cleaned_data[k] for k in ('name', 'phone', 'address', 'latitude', 'longitude', 'opens_at', 'closes_at')}
            changes = branch_service.update_branch(branch, **data)
            if changes:
                audit_service.record(request, action='branch.update', target_type='branch', target_id=branch.pk,
                                     target_label=branch.name, changes=changes)
                messages.success(request, 'บันทึกข้อมูลร้านแล้ว')
            return redirect('console:shop')
    else:
        form = BranchForm(initial={
            'name': branch.name, 'phone': branch.phone, 'address': branch.address,
            'coordinates': _coords_text(branch), 'opens_at': branch.opens_at, 'closes_at': branch.closes_at,
        })
    return render(request, 'console/shop.html', {
        'console_active': 'shop', 'form': form, 'branch': branch, 'shop': menu_selector.shop_status(branch),
    })


@owner_required
@require_POST
def shop_toggle_open(request):
    """HTMX: เปิด/ปิดรับออเดอร์ทันที"""
    branch = branch_service.get_or_create_main_branch()
    is_open = request.POST.get('is_open') == '1'
    if is_open and branch.location is None:
        messages.error(request, 'ตั้งพิกัดร้านก่อน จึงจะเปิดรับออเดอร์ได้')
    elif branch_service.set_open(branch, is_open=is_open):
        audit_service.record(request, action='branch.open' if is_open else 'branch.close', target_type='branch',
                             target_id=branch.pk, target_label=branch.name, changes={'is_open': [not is_open, is_open]})
    return render(request, 'console/_shop_switch.html', {'branch': branch, 'shop': menu_selector.shop_status(branch)})
