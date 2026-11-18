from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_safe, require_http_methods, require_POST

from apps.accounts.models import Role
from apps.accounts.selectors import user_selector
from apps.accounts.services.auth_service import EmailAlreadyUsed
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service
from apps.core.decorators import role_required
from apps.orders.selectors import order_selector

from .forms import StaffCreateForm, StaffPasswordForm
from .selectors import audit_selector
from .services import staff_service

owner_required = role_required(Role.OWNER)


@owner_required
@require_safe
def overview(request):
    branch = branch_service.get_console_branch(request.session)
    return render(request, 'console/overview.html', {
        'console_active': 'overview',
        'role_counts': user_selector.count_users_by_role(),
        'recent_logs': audit_selector.recent_logs(limit=10),
        'today': order_selector.today_summary(),
        'daily_sales': order_selector.daily_sales(days=7),
        'top_items': order_selector.top_items(days=30, limit=5),
        'recent_orders': order_selector.console_orders(status='active')[:8],
        'branch': branch,
        'shop': menu_selector.shop_status(branch),
    })


@sensitive_post_parameters('password')
@owner_required
@require_http_methods(['GET', 'POST'])
def staff_list(request):
    branches = menu_selector.all_branches()
    form = StaffCreateForm(request.POST or None, branches=branches)
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        data['branch'] = menu_selector.get_branch(data.get('branch'), active_only=False)
        try:
            user = staff_service.create_staff(request, **data)
        except EmailAlreadyUsed:
            form.add_error('email', 'อีเมลนี้มีบัญชีแล้ว')
        else:
            messages.success(request, f'สร้างบัญชี {user.get_role_display()} "{user.full_name}" แล้ว')
            return redirect('console:staff')

    return render(request, 'console/staff.html', {
        'console_active': 'staff',
        'staff_accounts': user_selector.list_staff_accounts(),
        'form': form,
        'branches': branches,
        'form_open': request.method == 'POST',
    })


@owner_required
@require_POST
def staff_move_branch(request, user_id):
    """HTMX: ย้ายพนักงานครัวไปสาขาอื่น แล้วคืนแถวที่อัปเดต"""
    staff_user = user_selector.get_staff_account(user_id)
    branch = menu_selector.get_branch(request.POST.get('branch'), active_only=False)
    if branch is not None and staff_user.role == Role.KITCHEN:
        staff_service.move_staff_branch(request, staff_user, branch)
    staff_user = user_selector.get_staff_account(user_id)
    return render(request, 'console/_staff_row.html', {'staff': staff_user, 'branches': menu_selector.all_branches()})


@owner_required
@require_POST
def staff_toggle_active(request, user_id):
    """HTMX: เปิด/ปิดบัญชี แล้วคืนแถวตารางที่อัปเดต"""
    staff_user = user_selector.get_staff_account(user_id)
    staff_service.set_staff_active(request, staff_user, active=request.POST.get('active') == '1')
    staff_user = user_selector.get_staff_account(user_id)
    return render(request, 'console/_staff_row.html', {'staff': staff_user, 'branches': menu_selector.all_branches()})


@sensitive_post_parameters('new_password')
@owner_required
@require_http_methods(['GET', 'POST'])
def staff_password(request, user_id):
    staff_user = user_selector.get_staff_account(user_id)
    form = StaffPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        staff_service.reset_staff_password(request, staff_user, new_password=form.cleaned_data['new_password'])
        messages.success(request, f'ตั้งรหัสผ่านใหม่ให้ {staff_user.full_name} แล้ว เครื่องที่ล็อกอินอยู่จะหลุดออก')
        return redirect('console:staff')
    return render(request, 'console/staff_password.html', {
        'console_active': 'staff', 'staff': staff_user, 'form': form,
    })
