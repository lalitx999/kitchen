from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('notifications/', views.notification_list, name='list'),
    path('notifications/read-all/', views.notification_read_all, name='read_all'),
    path('notifications/<uuid:notification_id>/', views.notification_open, name='open'),
    path('notifications/devices/', views.device_register, name='device_register'),
    path('notifications/devices/remove/', views.device_unregister, name='device_unregister'),
    path('firebase-messaging-sw.js', views.service_worker, name='service_worker'),
]
