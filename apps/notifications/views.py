import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe, require_POST

from .selectors import notification_selector
from .services import notify_service


@login_required
@require_safe
def notification_list(request):
    # ใช้ layout ตามบทบาท ให้หน้าตาเหมือนส่วนอื่นที่ผู้ใช้คนนั้นใช้อยู่
    layout = {
        'RIDER': 'layouts/rider.html', 'KITCHEN': 'layouts/kitchen.html', 'OWNER': 'layouts/console.html',
    }.get(request.user.role, 'layouts/customer.html')
    return render(request, 'notifications/list.html', {
        'notifications': notification_selector.recent(request.user), 'layout_template': layout,
        'console_active': 'notifications',
    })


@login_required
@require_safe
def notification_open(request, notification_id):
    """กดแจ้งเตือน -> ทำเป็นอ่านแล้ว -> ไปหน้าที่เกี่ยวข้อง (เฉพาะ path ในเว็บเรา)"""
    n = notify_service.mark_read(request.user, notification_id)
    target = n.url if n and n.url else '/'
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = '/'
    return redirect(target)


@login_required
@require_POST
def notification_read_all(request):
    notify_service.mark_all_read(request.user)
    return redirect('notifications:list')


@login_required
@require_POST
def device_register(request):
    """เบราว์เซอร์ได้ FCM token แล้วส่งมาเก็บ (JSON {token})"""
    try:
        token = json.loads(request.body or b'{}').get('token', '')
        notify_service.register_device(request.user, token, request.headers.get('User-Agent', ''))
    except (ValueError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'token ไม่ถูกต้อง'}, status=400)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def device_unregister(request):
    try:
        token = json.loads(request.body or b'{}').get('token', '')
    except ValueError:
        token = ''
    notify_service.unregister_device(request.user, token)
    return JsonResponse({'ok': True})


@require_safe
@cache_control(no_cache=True)
def service_worker(request):
    """
    service worker ของ Firebase ต้องอยู่ที่ root ของโดเมน (/firebase-messaging-sw.js)
    ถึงจะรับ push ได้ทุกหน้า · ใส่ค่าฝั่งเว็บ (เปิดเผยได้) จาก settings
    """
    config = notification_selector.push_config()
    body = render_to_string('notifications/firebase-messaging-sw.js', {
        'config': config, 'offline_icon': static('img/icon-192.png'),
    })
    response = HttpResponse(body, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    return response
