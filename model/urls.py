from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FinancialModelViewSet,
    ScenarioViewSet,
    CalculatedStatementViewSet,
    ModelTemplateViewSet,
    CalculationLogViewSet
)

router = DefaultRouter()
router.register(r'models', FinancialModelViewSet, basename='financialmodel')
router.register(r'scenarios', ScenarioViewSet, basename='scenario')
router.register(r'results', CalculatedStatementViewSet, basename='results')
router.register(r'templates', ModelTemplateViewSet, basename='template')
router.register(r'calculation-logs', CalculationLogViewSet, basename='calculationlog')

urlpatterns = [
    path('api/', include(router.urls)),
]