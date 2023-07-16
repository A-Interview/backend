from django.urls import path
from .views import RegisterView, LoginView, LogoutView, DeleteUserView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("delete/<int:id>/", DeleteUserView.as_view(), name="delete_user"),
]
