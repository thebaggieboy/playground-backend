from django.contrib import admin
from .models import (
    FinancialModel, Scenario, ProjectInformation, MacroAssumptions,
    RevenueProduct, OperatingExpenses, CapitalExpenditure, DebtFinancing,
    TaxAssumptions, WorkingCapital, DepreciationSchedule, DividendPolicy,
    ExitValuation, CalculatedStatement, ModelTemplate, CalculationLog
)

@admin.register(FinancialModel)
class FinancialModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'project_type', 'status', 'created_at']
    list_filter = ['project_type', 'status']
    search_fields = ['name', 'owner__username']

@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ['name', 'model', 'scenario_type', 'is_active']
    list_filter = ['scenario_type', 'is_active']

@admin.register(CalculatedStatement)
class CalculatedStatementAdmin(admin.ModelAdmin):
    list_display = ['scenario', 'statement_type', 'line_item', 'calculated_at']
    list_filter = ['statement_type']

@admin.register(ModelTemplate)
class ModelTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'project_type', 'created_by', 'is_public', 'created_at']
    list_filter = ['project_type', 'is_public']

@admin.register(CalculationLog)
class CalculationLogAdmin(admin.ModelAdmin):
    list_display = ['scenario', 'status', 'started_at', 'duration_seconds']
    list_filter = ['status']
    readonly_fields = ['started_at', 'completed_at', 'error_traceback']

# Register all input models for admin editing
admin.site.register(ProjectInformation)
admin.site.register(MacroAssumptions)
admin.site.register(RevenueProduct)
admin.site.register(OperatingExpenses)
admin.site.register(CapitalExpenditure)
admin.site.register(DebtFinancing)
admin.site.register(TaxAssumptions)
admin.site.register(WorkingCapital)
admin.site.register(DepreciationSchedule)
admin.site.register(DividendPolicy)
admin.site.register(ExitValuation)