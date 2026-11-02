from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class DispatchUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Dispatch", {"fields": ("role", "phone")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Dispatch", {"fields": ("role", "phone")}),)
    list_display = ("username", "email", "role", "is_staff")
    list_filter = (*UserAdmin.list_filter, "role")
