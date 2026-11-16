from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('auth/login/', views.login_view, name='login'),
    path('auth/register/', views.register_view, name='register'),
    path('auth/google/', views.google_login_view, name='google'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('account/', views.account_home, name='account'),
]
