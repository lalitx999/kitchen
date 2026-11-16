"""Django Admin สำหรับนักพัฒนาเท่านั้น (เจ้าของร้านใช้ /console/)"""
from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'full_name', 'phone')
    readonly_fields = ('id', 'google_sub', 'last_login', 'created_at', 'updated_at')
    exclude = ('password', 'groups', 'user_permissions')
