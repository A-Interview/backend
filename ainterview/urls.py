from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="AInterview API",
        default_version="v1",
        description="Ainterview의 API 명세서입니다.",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("api/users/", include("users.urls")),
    path("api/forms/", include("forms.urls")),
    # path(r'swagger(?P<format>\.json|\.yaml)', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path(
        "swagger.<str:format>",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    # path(r'swagger', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path(
        r"redoc", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc-v1"
    ),
    # prometheus metrics at localhost:8000/metrics
    # path("", include("django_prometheus.urls")),


    path("admin/", admin.site.urls),
    path("api/", include("speak_to_chat.urls")),
]
