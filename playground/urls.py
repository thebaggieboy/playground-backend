from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import UserViewSet

from model.views import (
    FinancialModelViewSet,
    ScenarioViewSet,
    CalculatedStatementViewSet,
    ModelTemplateViewSet,
    CalculationLogViewSet
)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'models', FinancialModelViewSet, basename='financialmodel')
router.register(r'scenarios', ScenarioViewSet, basename='scenario')
router.register(r'results', CalculatedStatementViewSet, basename='results')
router.register(r'templates', ModelTemplateViewSet, basename='template')
router.register(r'calculation-logs', CalculationLogViewSet, basename='calculationlog')

urlpatterns = [

    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('', include('rest_framework.urls', namespace='rest_framework')),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
    ]

if settings.DEBUG:
    # Serving static and media files during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)