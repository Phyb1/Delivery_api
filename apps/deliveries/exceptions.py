from rest_framework import status
from rest_framework.exceptions import APIException


class DeliveryConflict(APIException):
    """The request is valid but clashes with the delivery's current state (HTTP 409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The delivery is not in a state that allows this action."
    default_code = "delivery_conflict"
