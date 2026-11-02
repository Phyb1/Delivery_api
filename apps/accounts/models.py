from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """A person who uses the API: a vendor posting deliveries, a rider, or an admin."""

    class Role(models.TextChoices):
        VENDOR = "vendor", "Vendor"
        RIDER = "rider", "Rider"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VENDOR)
    phone = models.CharField(max_length=32, blank=True)

    objects = UserManager()

    def __str__(self):
        return f"{self.username} ({self.role})"
