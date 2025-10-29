# users/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.AuthRootView.as_view(), name="auth-root"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.UserProfileView.as_view(), name="profile"),
    path("users/", views.UserListView.as_view(), name="user-list"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="user-detail"),
    path("users/add/", views.UserCreateView.as_view(), name="user-add"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user-edit"),
    path(
        "users/<int:pk>/toggle/",
        views.UserToggleActiveView.as_view(),
        name="user-toggle",
    ),
    path(
        "users/<int:pk>/reset-password/",
        views.UserResetPasswordView.as_view(),
        name="user-reset-password",
    ),
    path("roles/", views.RoleListView.as_view(), name="role-list"),
    path("audit-logs/", views.AuditLogListView.as_view(), name="audit-log-list"),
]
