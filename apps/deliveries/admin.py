from django.contrib import admin

from .models import Delivery, DeliveryEvent


class DeliveryEventInline(admin.TabularInline):
    model = DeliveryEvent
    extra = 0
    can_delete = False
    readonly_fields = ("status_from", "status_to", "actor", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "vendor", "client_app", "rider", "fee", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("id", "external_reference", "pickup_address", "dropoff_address")
    readonly_fields = ("created_at", "updated_at")
    inlines = [DeliveryEventInline]
