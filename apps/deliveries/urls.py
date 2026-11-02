from rest_framework.routers import SimpleRouter

from .views import DeliveryViewSet

router = SimpleRouter()
router.register("deliveries", DeliveryViewSet, basename="delivery")

urlpatterns = router.urls
