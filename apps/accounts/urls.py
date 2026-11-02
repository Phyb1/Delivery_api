from django.urls import path

from .views import LoginView, MeView, RegisterView

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/token/", LoginView.as_view(), name="token"),
    path("auth/me/", MeView.as_view(), name="me"),
]
