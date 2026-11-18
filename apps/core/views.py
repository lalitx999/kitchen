from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from apps.accounts.services.auth_service import home_url_for
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service

from .selectors.health_selector import check_dependencies


@require_safe
def home(request):
    """
    หน้าร้าน: ข้อมูลร้าน + เมนูจริงจากฐานข้อมูล (3-4 query คงที่)
    หลายสาขาและลูกค้ายังไม่ได้เลือก -> แสดงรายการสาขาให้เลือกก่อน
    """
    branches = menu_selector.active_branches()
    branch = menu_selector.customer_branch(request.session, branches)
    if branch is None and len(branches) > 1:
        return render(request, 'core/branch_picker.html', {
            'branches': [(b, menu_selector.shop_status(b)) for b in branches],
        })
    categories, uncategorized = menu_selector.storefront_menu(branch) if branch else ([], [])
    return render(request, 'core/home.html', {
        'branch': branch,
        'shop': menu_selector.shop_status(branch),
        'categories': categories,
        'uncategorized': uncategorized,
        'has_many_branches': len(branches) > 1,
    })


@require_safe
def branch_picker(request):
    """ลูกค้ากด "เปลี่ยนสาขา" """
    branches = menu_selector.active_branches()
    if len(branches) <= 1:
        return redirect('core:home')
    current = menu_selector.customer_branch(request.session, branches)
    return render(request, 'core/branch_picker.html', {
        'branches': [(b, menu_selector.shop_status(b)) for b in branches], 'current': current,
    })


@require_POST
def select_branch(request, branch_id):
    branch = menu_selector.get_branch(branch_id)
    if branch is None:
        messages.error(request, 'ไม่พบสาขานี้ หรือสาขาปิดใช้งานแล้ว')
        return redirect('core:home')
    if branch_service.select_customer_branch(request.session, branch):
        messages.info(request, f'เปลี่ยนเป็น{branch.name} แล้ว ล้างตะกร้าเดิม (สั่งได้ทีละสาขา)')
    return redirect('core:home')


@require_safe
@never_cache
def app_start(request):
    """
    หน้าเริ่มของแอปที่ติดตั้งบนหน้าจอโฮม (manifest start_url)
    ไรเดอร์/ครัว/เจ้าของเปิดแอปแล้วไปหน้าของตัวเองทันที ไม่ค้างที่หน้าร้านของลูกค้า
    """
    if request.user.is_authenticated:
        return redirect(home_url_for(request.user))
    return redirect('core:home')


@require_safe
@never_cache
def healthz(request):
    status = check_dependencies()
    ok = all(status.values())
    return JsonResponse({'ok': ok, **status}, status=200 if ok else 503)


@require_safe
def styleguide(request):
    """หน้ารวมปุ่ม การ์ด badge ฟอร์ม ไว้ตรวจธีม เปิดเฉพาะตอน DEBUG"""
    if not settings.DEBUG:
        raise Http404
    return render(request, 'core/styleguide.html')


@require_safe
def styleguide_console(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, 'core/styleguide_console.html', {'console_active': 'overview', 'pending_slip_count': 2})
