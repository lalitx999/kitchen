"""
แอปไรเดอร์ (มือถือ) แถบล่าง 4 แท็บ: หน้าแรก / งาน / รายได้ / โปรไฟล์
  หน้าแรก: สถานะรับงาน + สรุปวันนี้ + งานของฉัน + งานใหม่ (โหลดใหม่ทุก 5 วิ)
  หน้างาน (นำทาง): แผนที่ + แผ่นล่าง ถึงร้าน -> รับอาหาร -> ถ่ายรูปส่ง -> หน้าส่งสำเร็จ
ทุกหน้ากรองด้วยไรเดอร์ที่ล็อกอิน (selector) งานคนอื่นได้ 404
"""
import json

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe, require_POST

from apps.accounts.models import Role
from apps.core.decorators import role_required

from apps.orders.models import OrderStatus

from .selectors import job_selector, payout_selector, rider_selector
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


def _get_my_job_or_404(request, order_id):
    job = job_selector.get_my_job(request.user, order_id)
    if job is None:
        raise Http404
    return job


def _job_context(request, job):
    """หน้างาน: เป้าหมายตอนนี้ = ร้าน (ก่อนรับอาหาร) หรือบ้านลูกค้า (กำลังไปส่ง)"""
    going_to_customer = job.status == OrderStatus.DELIVERING
    target = job.delivery_location if going_to_customer else job.branch.location
    return {
        'job': job, 'going_to_customer': going_to_customer,
        'target': target, 'target_label': 'บ้านลูกค้า' if going_to_customer else 'ร้าน',
        'can_release': job.status in job_selector.ASSIGNABLE_STATUSES,
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
        'arrive': lambda: job_service.arrive_at_shop(order, request.user),
        'pickup': lambda: job_service.pick_up(order, request.user),
    }
    action = request.POST.get('action')
    error = None
    try:
        if order is None or action not in actions:
            raise job_service.JobError('ไม่พบงาน')
        actions[action]()
    except job_service.JobError as exc:
        error = str(exc)

    # กดจากหน้างาน (แผ่นล่าง) -> คืนแผ่นล่างใหม่ · คืนงานแล้วไม่ใช่งานเราแล้ว -> กลับหน้าแรก
    if request.headers.get('HX-Target') == 'job-sheet' and order is not None:
        if action == 'release' and error is None:
            response = HttpResponse(status=204)
            response['HX-Redirect'] = reverse('delivery:rider_home')
            return response
        job = _get_my_job_or_404(request, order.pk)
        response = render(request, 'delivery/_job_sheet.html', _job_context(request, job))
        return _toast(response, error) if error else response
    response = render(request, 'delivery/_jobs.html', _jobs_context(request, profile))
    return _toast(response, error) if error else response


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
        if order is not None and order.rider_id == request.user.pk:
            return redirect('delivery:rider_job', order_id=order.pk)
        return redirect('delivery:rider_home')
    return redirect('delivery:rider_job_done', order_id=order.pk)


@rider_required
@require_safe
def rider_job(request, order_id):
    """หน้างาน (นำทาง): แผนที่เต็มจอ + แผ่นล่าง · ส่งเสร็จแล้วไปหน้าสรุป"""
    job = _get_my_job_or_404(request, order_id)
    if job.status == OrderStatus.COMPLETED:
        return redirect('delivery:rider_job_done', order_id=job.pk)
    return render(request, 'delivery/job.html', {
        **_job_context(request, job), 'profile': _profile_for(request),
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY, 'google_maps_map_id': settings.GOOGLE_MAPS_MAP_ID,
    })


@rider_required
@require_safe
@never_cache
def rider_job_sheet(request, order_id):
    """HTMX: แผ่นล่างของหน้างาน โหลดใหม่ทุก 5 วิ (ครัวกด "อาหารพร้อม" แล้วปุ่มรับอาหารขึ้นเอง)"""
    job = _get_my_job_or_404(request, order_id)
    if job.status == OrderStatus.COMPLETED:
        response = HttpResponse(status=204)
        response['HX-Redirect'] = reverse('delivery:rider_job_done', args=[job.pk])
        return response
    return render(request, 'delivery/_job_sheet.html', _job_context(request, job))


@rider_required
@require_safe
def rider_job_done(request, order_id):
    """สรุปหลังส่งสำเร็จ: ค่าส่ง เวลาที่ใช้ รูปหลักฐาน"""
    job = _get_my_job_or_404(request, order_id)
    if job.status != OrderStatus.COMPLETED:
        return redirect('delivery:rider_job', order_id=job.pk)
    minutes = None
    if job.picked_up_at and job.completed_at:
        minutes = max(1, round((job.completed_at - job.picked_up_at).total_seconds() / 60))
    return render(request, 'delivery/job_done.html', {
        'job': job, 'minutes': minutes, 'photo_count': job_selector.proof_photo_count(job),
        'today': job_selector.today_summary(request.user),
    })


@rider_required
@require_safe
def rider_history(request):
    """แท็บ "งาน": ทั้งหมด / กำลังส่ง / สำเร็จ / ยกเลิก"""
    tab = request.GET.get('tab', 'all')
    if tab not in job_selector.HISTORY_TABS:
        tab = 'all'
    return render(request, 'delivery/history.html', {
        'tab': tab, 'jobs': job_selector.history(request.user, tab), 'history_days': job_selector.HISTORY_DAYS,
    })


@rider_required
@require_safe
def rider_earnings(request):
    """แท็บ "รายได้": วันนี้ / 7 วัน / ยอดที่ร้านยังไม่ได้จ่าย / ประวัติการจ่าย (ร้านบันทึกใน Console)"""
    return render(request, 'delivery/earnings.html', {
        'today': job_selector.today_summary(request.user),
        'week': job_selector.week_summary(request.user),
        'unpaid_total': payout_selector.unpaid_total(request.user),
        'unpaid_orders': payout_selector.unpaid_orders(request.user, limit=20),
        'payouts': payout_selector.payout_history(request.user, limit=10),
    })


@rider_required
@require_safe
def rider_profile(request):
    """แท็บ "โปรไฟล์": ข้อมูลไรเดอร์ เสียง แจ้งเตือน ติดตั้งแอป ออกจากระบบ"""
    return render(request, 'delivery/profile.html', {'profile': _profile_for(request)})


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
