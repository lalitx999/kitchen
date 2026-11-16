from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('healthz/', views.healthz, name='healthz'),
    path('dev/styleguide/', views.styleguide, name='styleguide'),
    path('dev/styleguide/console/', views.styleguide_console, name='styleguide_console'),
]
