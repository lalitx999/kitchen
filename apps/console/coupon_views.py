"""Console: คูปองส่วนลด (เพิ่ม แก้ไข เปิด/ปิด ลบ) · เรียกผ่าน orders.coupon_service/selector เท่านั้น"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.accounts.models import Role
from apps.catalog.selectors import menu_selector
from apps.core.decorators import role_required
from apps.orders.selectors import coupon_selector
from apps.orders.services import coupon_service

from .forms import CouponForm
from .services import audit_service

owner_required = role_required(Role.OWNER)


def _data(form):
    data = dict(form.cleaned_data)
    data['branch'] = menu_selector.get_branch(data.get('branch'), active_only=False) if data.get('branch') else None
    return data


def _local(dt):
    # ช่อง datetime-local ต้องการรูปแบบ 2026-11-18T10:00 (เวลาไทย)
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M') if dt else ''


def _audit(request, action, coupon, changes=None):
    audit_service.record(request, action=action, target_type='coupon', target_id=coupon.pk,
                         target_label=f'{coupon.code} ({coupon.name})', changes=changes or {})


@owner_required
@require_safe
def coupon_list(request):
    return render(request, 'console/coupons/list.html', {
        'console_active': 'coupons', 'coupons': coupon_selector.console_coupons(),
    })


@owner_required
@require_http_methods(['GET', 'POST'])
def coupon_create(request):
    branches = menu_selector.all_branches()
    form = CouponForm(request.POST or None, branches=branches)
    if request.method == 'POST' and form.is_valid():
        try:
            coupon = coupon_service.create_coupon(_data(form))
        except coupon_service.CouponError as exc:
            form.add_error(None, str(exc))
        else:
            _audit(request, 'coupon.create', coupon, {'summary': [None, coupon.summary]})
            messages.success(request, f'เพิ่มคูปอง {coupon.code} แล้ว')
            return redirect('console:coupons')
    return render(request, 'console/coupons/form.html', {'console_active': 'coupons', 'form': form, 'coupon': None})


@owner_required
@require_http_methods(['GET', 'POST'])
def coupon_edit(request, coupon_id):
    coupon = coupon_selector.get_coupon(coupon_id)
    branches = menu_selector.all_branches()
    if request.method == 'POST':
        form = CouponForm(request.POST, branches=branches)
        if form.is_valid():
            try:
                changes = coupon_service.update_coupon(coupon, _data(form))
            except coupon_service.CouponError as exc:
                form.add_error(None, str(exc))
            else:
                if changes:
                    _audit(request, 'coupon.update', coupon, changes)
                    messages.success(request, f'บันทึกคูปอง {coupon.code} แล้ว')
                return redirect('console:coupons')
    else:
        form = CouponForm(branches=branches, initial={
            'code': coupon.code, 'name': coupon.name, 'kind': coupon.kind, 'value': coupon.value,
            'max_discount': coupon.max_discount, 'min_subtotal': coupon.min_subtotal,
            'starts_at': _local(coupon.starts_at), 'ends_at': _local(coupon.ends_at), 'usage_limit': coupon.usage_limit,
            'per_customer_limit': coupon.per_customer_limit, 'branch': str(coupon.branch_id or ''),
            'show_in_checkout': coupon.show_in_checkout, 'is_active': coupon.is_active,
        })
    return render(request, 'console/coupons/form.html', {'console_active': 'coupons', 'form': form, 'coupon': coupon})


@owner_required
@require_POST
def coupon_toggle(request, coupon_id):
    coupon = coupon_selector.get_coupon(coupon_id)
    active = request.POST.get('active') == '1'
    if coupon_service.set_active(coupon, active=active):
        _audit(request, 'coupon.activate' if active else 'coupon.deactivate', coupon, {'is_active': [not active, active]})
    return redirect('console:coupons')


@owner_required
@require_POST
def coupon_delete(request, coupon_id):
    coupon = coupon_selector.get_coupon(coupon_id)
    _audit(request, 'coupon.delete', coupon, {'summary': [coupon.summary, None]})
    coupon_service.delete_coupon(coupon)
    messages.info(request, f'ลบคูปอง {coupon.code} แล้ว (ออเดอร์ที่เคยใช้ยังเก็บส่วนลดไว้)')
    return redirect('console:coupons')
