from django.urls import path

from . import views

app_name = 'delivery'

urlpatterns = [
    path('', views.rider_home, name='rider_home'),
    path('status/', views.rider_set_status, name='rider_set_status'),
    path('jobs/', views.rider_jobs, name='rider_jobs'),
    path('jobs/<uuid:order_id>/', views.rider_job_action, name='rider_job_action'),
    path('jobs/<uuid:order_id>/complete/', views.rider_complete, name='rider_complete'),
    path('location/', views.rider_location, name='rider_location'),
    path('proofs/<uuid:order_id>/photo/', views.delivery_proof_photo, name='proof_photo'),
]
