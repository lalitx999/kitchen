from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('apps.core.urls')),
    path('', include('apps.accounts.urls')),      # /auth/... และ /account/
    path('', include('apps.orders.urls')),        # /cart/ /checkout/ /orders/
    path('', include('apps.payments.urls')),      # แนบสลิป + รูปสลิป (ตรวจสิทธิ์)
    path('', include('apps.notifications.urls')), # แจ้งเตือน + service worker ที่ root
    path('rider/', include('apps.delivery.urls')),
    path('console/', include('apps.console.urls')),
]

# Django Admin สำหรับนักพัฒนาเท่านั้น ปิดใน production เป็นค่าเริ่มต้น
if settings.DJANGO_ADMIN_ENABLED:
    urlpatterns.append(path('django-admin/', admin.site.urls))

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
