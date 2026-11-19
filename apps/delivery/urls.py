from django.urls import path

from . import views

app_name = 'delivery'

urlpatterns = [
    path('', views.rider_home, name='rider_home'),
    path('status/', views.rider_set_status, name='rider_set_status'),
    path('jobs/', views.rider_jobs, name='rider_jobs'),
    path('jobs/<uuid:order_id>/', views.rider_job_action, name='rider_job_action'),
    path('jobs/<uuid:order_id>/complete/', views.rider_complete, name='rider_complete'),
    path('job/<uuid:order_id>/', views.rider_job, name='rider_job'),
    path('job/<uuid:order_id>/sheet/', views.rider_job_sheet, name='rider_job_sheet'),
    path('job/<uuid:order_id>/done/', views.rider_job_done, name='rider_job_done'),
    path('history/', views.rider_history, name='rider_history'),
    path('earnings/', views.rider_earnings, name='rider_earnings'),
    path('profile/', views.rider_profile, name='rider_profile'),
    path('location/', views.rider_location, name='rider_location'),
    path('proofs/<uuid:order_id>/photo/', views.delivery_proof_photo, name='proof_photo'),
    path('proofs/<uuid:order_id>/photo/<int:index>/', views.delivery_proof_photo, name='proof_photo_n'),
]
