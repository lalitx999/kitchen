from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.catalog.selectors import menu_selector

from .selectors.health_selector import check_dependencies


@require_safe
def home(request):
    """หน้าร้าน: ข้อมูลร้าน + เมนูจริงจากฐานข้อมูล (3-4 query คงที่)"""
    branch = menu_selector.get_storefront_branch()
    categories, uncategorized = menu_selector.storefront_menu(branch) if branch else ([], [])
    return render(request, 'core/home.html', {
        'branch': branch,
        'shop': menu_selector.shop_status(branch),
        'categories': categories,
        'uncategorized': uncategorized,
    })


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
