"""
หน้าไรเดอร์ (มือถือ): สถานะรับงาน, งานของฉัน, งานใหม่, ส่งพิกัดสด
รายการงานโหลดใหม่ทุก 5 วินาทีด้วย HTMX (เฉพาะตอนแท็บเปิด)
"""
import json

from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe, require_POST

from apps.accounts.models import Role
from apps.core.decorators import role_required

from .selectors import job_selector, rider_selector
from .services import job_service, live_location_service, rider_service

rider_required = role_required(Role.RIDER)


def _profile_for(request):
    return rider_selector.get_profile(request.user) or rider_service.ensure_rider_profile(request.user)


def _toast(response, message, level='warning'):
    response['HX-Trigger'] = json.dumps({'tmpp:toast': {'message': message, 'level': level}}, ensure_ascii=True)
    return response


def _jobs_context(request, profile):
    return {
        'profile': profile,
        'my_jobs': job_selector.my_jobs(request.user),
        'available_jobs': job_selector.available_jobs() if profile.is_online else [],
        'today': job_selector.today_summary(request.user),
    }


@rider_required
@require_safe
def rider_home(request):
    profile = _profile_for(request)
    return render(request, 'delivery/rider_home.html', _jobs_context(request, profile))


@rider_required
@require_safe
@never_cache
def rider_jobs(request):
    return render(request, 'delivery/_jobs.html', _jobs_context(request, _profile_for(request)))


@rider_required
@require_POST
def rider_set_status(request):
    """HTMX: เปิด/ปิดรับงาน แล้วคืนการ์ดสถานะ + รายการงานใหม่"""
    online = request.POST.get('online') == '1'
    profile = _profile_for(request)
    if not online and job_selector.has_active_jobs(request.user):
        response = render(request, 'delivery/_status_card.html', {'profile': profile, 'oob_jobs': False})
        return _toast(response, 'ยังมีงานค้าง ส่งให้เสร็จหรือคืนงานก่อน')
    profile = rider_service.set_online(profile, online=online)
    if not online:
        live_location_service.clear(request.user.pk)
    return render(request, 'delivery/_status_card.html', {**_jobs_context(request, profile), 'oob_jobs': True})


@rider_required
@require_POST
def rider_job_action(request, order_id):
    """รับงาน / คืนงาน / รับอาหารแล้ว"""
    profile = _profile_for(request)
    order = job_selector.get_job(order_id)
    actions = {
        'accept': lambda: job_service.accept(order, request.user, profile=profile),
        'release': lambda: job_service.release(order, request.user),
        'pickup': lambda: job_service.pick_up(order, request.user),
    }
    response = None
    try:
        if order is None or request.POST.get('action') not in actions:
            raise job_service.JobError('ไม่พบงาน')
        actions[request.POST['action']]()
    except job_service.JobError as exc:
        response = _toast(render(request, 'delivery/_jobs.html', _jobs_context(request, profile)), str(exc))
    return response or render(request, 'delivery/_jobs.html', _jobs_context(request, profile))


@rider_required
@require_POST
def rider_complete(request, order_id):
    """ส่งสำเร็จ: ฟอร์มธรรมดา (มีรูปจากกล้อง) ไม่ใช่ HTMX"""
    order = job_selector.get_job(order_id)
    try:
        if order is None:
            raise job_service.JobError('ไม่พบงาน')
        job_service.complete(order, request.user, photos=request.FILES.getlist('photos'),
                             latitude=request.POST.get('latitude'), longitude=request.POST.get('longitude'))
    except job_service.JobError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'ส่ง {order.order_number} สำเร็จ ได้ค่าส่ง ฿{order.rider_fee:.0f}')
    return redirect('delivery:rider_home')


@rider_required
@require_POST
def rider_location(request):
    """มือถือส่งพิกัดมาที่นี่ (JSON) ระหว่างเปิดรับงาน"""
    profile = _profile_for(request)
    if not profile.is_online:
        return JsonResponse({'ok': False, 'error': 'ปิดรับงานอยู่ ไม่บันทึกตำแหน่ง'}, status=409)
    try:
        data = json.loads(request.body or b'{}')
        location = live_location_service.save(profile, live_location_service.parse(data))
        job_service.check_near_customers(request.user, location)
    except (ValueError, live_location_service.LocationError) as exc:
        message = str(exc) if isinstance(exc, live_location_service.LocationError) else 'ข้อมูลไม่ถูกต้อง'
        return JsonResponse({'ok': False, 'error': message}, status=400)
    return JsonResponse({'ok': True, 'updated_at': location.updated_at})


@require_safe
@never_cache
def delivery_proof_photo(request, order_id, index=0):
    """รูปหลักฐานการส่ง: เจ้าของร้าน, ลูกค้าเจ้าของออเดอร์, ไรเดอร์คนส่ง เท่านั้น"""
    user = request.user
    if not user.is_authenticated:
        return redirect('accounts:login')
    photo = job_selector.get_proof_photo_for_viewer(user, order_id, index)
    if photo is None:
        raise Http404
    response = FileResponse(photo.photo.open('rb'))
    response['Cache-Control'] = 'private, no-store'
    return response
