from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.decorators import role_required
from apps.core.http import client_ip

from .forms import LoginForm, ProfileForm, RegisterForm
from .models import Role
from .services import auth_service, user_service

BACKEND = 'django.contrib.auth.backends.ModelBackend'


@sensitive_post_parameters('password')
@never_cache
@require_http_methods(['GET', 'POST'])
def login_view(request):
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if request.user.is_authenticated:
        return redirect(auth_service.redirect_url_after_login(request, request.user, next_url))

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = auth_service.authenticate_user(
                request, email=form.cleaned_data['email'], password=form.cleaned_data['password'],
                ip=client_ip(request),
            )
        except auth_service.LoginLocked as exc:
            minutes = max(1, exc.retry_after_seconds // 60)
            form.add_error(None, f'ใส่รหัสผ่านผิดหลายครั้ง ลองใหม่ในอีก {minutes} นาที')
        else:
            if user is None:
                # ไม่บอกว่าอีเมลหรือรหัสผ่านผิด กันคนไล่เช็คว่าอีเมลไหนมีบัญชี
                form.add_error(None, 'อีเมลหรือรหัสผ่านไม่ถูกต้อง')
            else:
                login(request, user, backend=BACKEND)
                return redirect(auth_service.redirect_url_after_login(request, user, next_url))

    return render(request, 'accounts/login.html', {
        'form': form, 'next': next_url, 'google_client_id': settings.GOOGLE_CLIENT_ID,
    })


@sensitive_post_parameters('password1', 'password2')
@never_cache
@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect(auth_service.home_url_for(request.user))

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            user = auth_service.register_customer(
                full_name=data['full_name'], email=data['email'], phone=data['phone'], password=data['password1'],
            )
        except auth_service.EmailAlreadyUsed:
            form.add_error('email', 'อีเมลนี้มีบัญชีแล้ว ลองเข้าสู่ระบบ')
        else:
            login(request, user, backend=BACKEND)
            messages.success(request, f'สมัครสมาชิกเรียบร้อย ยินดีต้อนรับคุณ {user.get_short_name()}')
            return redirect(auth_service.home_url_for(user))

    return render(request, 'accounts/register.html', {
        'form': form, 'google_client_id': settings.GOOGLE_CLIENT_ID,
    })


@require_POST
def google_login_view(request):
    try:
        identity = auth_service.verify_google_credential(request.POST.get('credential', ''))
        user = auth_service.login_or_register_with_google(identity)
    except auth_service.GoogleLoginError as exc:
        messages.error(request, str(exc))
        return redirect('accounts:login')
    login(request, user, backend=BACKEND)
    return redirect(auth_service.redirect_url_after_login(request, user, request.POST.get('next')))


@require_POST
def logout_view(request):
    # ออกจากระบบด้วย POST เท่านั้น (ลิงก์ GET ถูกเว็บอื่นฝังรูปแล้วพาออกจากระบบได้)
    logout(request)
    messages.info(request, 'ออกจากระบบแล้ว')
    return redirect(settings.LOGOUT_REDIRECT_URL)


@role_required(Role.CUSTOMER)
@require_http_methods(['GET', 'POST'])
def account_home(request):
    user = request.user
    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            if user_service.update_profile(user, **form.cleaned_data):
                messages.success(request, 'บันทึกข้อมูลแล้ว')
            return redirect('accounts:account')
    else:
        form = ProfileForm(initial={'full_name': user.full_name, 'phone': user.phone})
    return render(request, 'accounts/account_home.html', {'form': form})
