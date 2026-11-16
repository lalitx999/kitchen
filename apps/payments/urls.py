from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('orders/<uuid:order_id>/slip/', views.upload_slip, name='upload_slip'),
    path('payments/slips/<uuid:slip_id>/image/', views.slip_image, name='slip_image'),
]
