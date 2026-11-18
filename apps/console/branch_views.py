"""Console: จัดการสาขา (เพิ่ม, เปิด/ซ่อนจากลูกค้า, สลับสาขาที่กำลังจัดการ)"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import Role
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service
from apps.core.decorators import role_required

from .forms import BranchCreateForm
from .services import audit_service

owner_required = role_required(Role.OWNER)


@owner_required
@require_http_methods(['GET', 'POST'])
def branch_list(request):
    main = branch_service.get_or_create_main_branch()
    form = BranchCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        branch = branch_service.create_branch(name=form.cleaned_data['name'], copy_rates_from=main)
        audit_service.record(request, action='branch.create', target_type='branch', target_id=branch.pk,
                             target_label=branch.name, changes={'name': [None, branch.name]})
        # สลับไปสาขาใหม่ทันที แล้วพาไปตั้งข้อมูลร้าน (พิกัด/รูป/เวลา) ต่อ
        branch_service.switch_console_branch(request.session, branch)
        messages.success(request, f'เพิ่ม "{branch.name}" แล้ว ตั้งพิกัดและเมนู แล้วกด "แสดงให้ลูกค้าเห็น"')
        return redirect('console:shop')
    branches = menu_selector.all_branches()
    return render(request, 'console/branches.html', {
        'console_active': 'branches', 'form': form,
        'rows': [(b, menu_selector.shop_status(b)) for b in branches],
        'current': menu_selector.console_branch(request.session),
    })


@owner_required
@require_POST
def branch_switch(request, branch_id):
    branch = menu_selector.get_branch(branch_id, active_only=False)
    if branch is not None:
        branch_service.switch_console_branch(request.session, branch)
        messages.info(request, f'กำลังจัดการ: {branch.name}')
    next_url = request.POST.get('next') or ''
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('console:overview')


@owner_required
@require_POST
def branch_toggle_active(request, branch_id):
    branch = menu_selector.get_branch(branch_id, active_only=False)
    if branch is None:
        messages.error(request, 'ไม่พบสาขา')
        return redirect('console:branches')
    active = request.POST.get('active') == '1'
    try:
        if branch_service.set_active(branch, active=active):
            audit_service.record(request, action='branch.show' if active else 'branch.hide', target_type='branch',
                                 target_id=branch.pk, target_label=branch.name, changes={'is_active': [not active, active]})
            messages.success(request, f'{branch.name}: {"ลูกค้าเห็นแล้ว" if active else "ซ่อนจากลูกค้าแล้ว"}')
    except branch_service.BranchError as exc:
        messages.error(request, str(exc))
    return redirect('console:branches')
