from django.contrib import admin

from .models import ClientApp, WebhookEvent


@admin.register(ClientApp)
class ClientAppAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "webhook_url", "created_at")
    readonly_fields = ("key_prefix", "created_at")

    def has_add_permission(self, request):
        # Keys must be issued with `manage.py create_client_app` so the raw key is shown once.
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "client_app", "status", "attempts", "created_at")
    list_filter = ("status", "client_app")
    readonly_fields = [field.name for field in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False
