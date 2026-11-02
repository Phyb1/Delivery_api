from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Delivery
from .permissions import (
    ADMIN,
    CLIENT_APP,
    RIDER,
    VENDOR,
    CanCancelDeliveries,
    CanPostDeliveries,
    IsRider,
)
from .serializers import DeliveryCreateSerializer, DeliverySerializer

UUID_REGEX = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


class DeliveryViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Deliveries API. State changes are delegated to ``services``."""

    serializer_class = DeliverySerializer
    lookup_value_regex = UUID_REGEX

    permission_classes_by_action = {
        "create": [CanPostDeliveries],
        "accept": [IsRider],
        "pickup": [IsRider],
        "deliver": [IsRider],
        "cancel": [CanCancelDeliveries],
    }

    def get_permissions(self):
        classes = self.permission_classes_by_action.get(self.action, [])
        return [IsAuthenticated(), *(cls() for cls in classes)]

    def get_queryset(self):
        """Each principal only sees the deliveries relevant to them."""
        user = self.request.user
        role = getattr(user, "role", None)
        queryset = Delivery.objects.select_related("rider", "vendor", "client_app")

        if role == CLIENT_APP:
            queryset = queryset.filter(client_app=user)
        elif role == VENDOR:
            queryset = queryset.filter(vendor=user)
        elif role == RIDER:
            queryset = queryset.filter(Q(status=Delivery.Status.POSTED) | Q(rider=user))
        elif role != ADMIN:
            queryset = queryset.none()

        status_filter = self.request.query_params.get("status")
        if status_filter in Delivery.Status.values:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = DeliveryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery = services.create_delivery(owner=request.user, **serializer.validated_data)
        return Response(self.get_serializer(delivery).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        delivery = services.accept_delivery(delivery_id=pk, rider=request.user)
        return Response(self.get_serializer(delivery).data)

    @action(detail=True, methods=["post"])
    def pickup(self, request, pk=None):
        delivery = services.mark_picked_up(delivery_id=pk, rider=request.user)
        return Response(self.get_serializer(delivery).data)

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        delivery = services.mark_delivered(delivery_id=pk, rider=request.user)
        return Response(self.get_serializer(delivery).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        delivery = services.cancel_delivery(delivery_id=pk, actor=request.user)
        return Response(self.get_serializer(delivery).data)
