from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Liveness probe for load balancers and uptime monitors."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.deliveries.urls")),
]
