from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('start/', views.app_start, name='start'),
    path('branches/', views.branch_picker, name='branches'),
    path('branches/<uuid:branch_id>/', views.select_branch, name='select_branch'),
    path('healthz/', views.healthz, name='healthz'),
    path('dev/styleguide/', views.styleguide, name='styleguide'),
    path('dev/styleguide/console/', views.styleguide_console, name='styleguide_console'),
]
