"""
Enhanced Django Serializers for Financial Modeling Application
Supports complete input/output serialization for 170+ variables
"""

from rest_framework import serializers
from decimal import Decimal
from .models import (
    FinancialModel, Scenario, ProjectInformation, MacroAssumptions,
    RevenueProduct, OperatingExpenses, CapitalExpenditure, DebtFinancing,
    TaxAssumptions, WorkingCapital, DepreciationSchedule, DividendPolicy,
    ExitValuation, CalculatedStatement, ModelTemplate, CalculationLog
)


# ============================================================================
# INPUT SERIALIZERS - Matching enhanced-input-model-page.tsx structure
# ============================================================================

class ProjectInformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectInformation
        exclude = ['id', 'scenario']


class MacroAssumptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacroAssumptions
        exclude = ['id', 'scenario']


class RevenueProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueProduct
        exclude = ['id', 'scenario']
        
    def validate_product_order(self, value):
        if value < 1 or value > 10:
            raise serializers.ValidationError("Product order must be between 1 and 10")
        return value


class OperatingExpensesSerializer(serializers.ModelSerializer):
    total_staff_cost_calculated = serializers.SerializerMethodField()
    
    class Meta:
        model = OperatingExpenses
        exclude = ['id', 'scenario']
    
    def get_total_staff_cost_calculated(self, obj):
        """Calculate: Headcount × Avg Salary × (1 + Benefits%)"""
        base_cost = Decimal(obj.total_headcount) * obj.average_annual_salary
        with_benefits = base_cost * (1 + obj.benefits_payroll_tax_pct / 100)
        return float(with_benefits)


class CapitalExpenditureSerializer(serializers.ModelSerializer):
    total_hard_costs = serializers.SerializerMethodField()
    total_capex = serializers.SerializerMethodField()
    interest_during_construction = serializers.SerializerMethodField()
    total_development_cost = serializers.SerializerMethodField()
    
    class Meta:
        model = CapitalExpenditure
        exclude = ['id', 'scenario']
    
    def get_total_hard_costs(self, obj):
        """Calculate sum of all hard costs"""
        hard_costs = (
            obj.land_cost + 
            obj.construction_building_cost + 
            obj.equipment_machinery_cost + 
            obj.ffe_cost
        )
        # Add real estate specific costs if present
        if obj.carpark_cost:
            hard_costs += obj.carpark_cost
        if obj.amenities_cost:
            hard_costs += obj.amenities_cost
        if obj.apartment_construction_cost:
            hard_costs += obj.apartment_construction_cost
        if obj.hotel_commercial_cost:
            hard_costs += obj.hotel_commercial_cost
        
        return float(hard_costs)
    
    def get_total_capex(self, obj):
        """Calculate total CAPEX including soft costs"""
        hard_costs = Decimal(str(self.get_total_hard_costs(obj)))
        
        contingency = hard_costs * obj.contingency_pct / 100
        prof_fees = hard_costs * obj.professional_fees_pct / 100
        permits = hard_costs * obj.permits_approvals_pct / 100
        vat = hard_costs * obj.vat_on_construction_pct / 100
        
        total = hard_costs + contingency + prof_fees + permits + vat
        return float(total)
    
    def get_interest_during_construction(self, obj):
        """Estimate IDC based on construction loan rate and duration"""
        if not obj.capitalize_interest or not obj.construction_loan_interest_rate:
            return 0
        
        # Simplified IDC calculation
        # Assumes average debt balance of 50% of total capex over construction period
        total_capex = Decimal(str(self.get_total_capex(obj)))
        
        # Get construction duration from project info (if available)
        try:
            construction_months = obj.scenario.project_info.construction_duration_months
            construction_years = Decimal(construction_months) / 12
        except:
            construction_years = Decimal('3')  # Default 3 years
        
        avg_balance = total_capex * Decimal('0.5')
        idc = avg_balance * obj.construction_loan_interest_rate / 100 * construction_years
        
        return float(idc)
    
    def get_total_development_cost(self, obj):
        """Total CAPEX + IDC"""
        total_capex = Decimal(str(self.get_total_capex(obj)))
        idc = Decimal(str(self.get_interest_during_construction(obj)))
        return float(total_capex + idc)


class DebtFinancingSerializer(serializers.ModelSerializer):
    all_in_interest_rate = serializers.SerializerMethodField()
    equity_amount = serializers.SerializerMethodField()
    debt_amount = serializers.SerializerMethodField()
    total_project_cost = serializers.SerializerMethodField()
    
    class Meta:
        model = DebtFinancing
        exclude = ['id', 'scenario']
    
    def get_all_in_interest_rate(self, obj):
        """Base rate + spread"""
        return float(obj.base_rate_value + obj.interest_margin_spread)
    
    def get_total_project_cost(self, obj):
        """Get from CAPEX total development cost"""
        try:
            capex = obj.scenario.capital_expenditure
            capex_serializer = CapitalExpenditureSerializer(capex)
            return capex_serializer.get_total_development_cost(capex)
        except:
            return 0
    
    def get_equity_amount(self, obj):
        """Calculate equity amount from percentage"""
        total_cost = Decimal(str(self.get_total_project_cost(obj)))
        return float(total_cost * obj.equity_percentage / 100)
    
    def get_debt_amount(self, obj):
        """Calculate debt amount from percentage"""
        total_cost = Decimal(str(self.get_total_project_cost(obj)))
        return float(total_cost * obj.debt_percentage / 100)


class TaxAssumptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxAssumptions
        exclude = ['id', 'scenario']


class WorkingCapitalSerializer(serializers.ModelSerializer):
    cash_cycle_days = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkingCapital
        exclude = ['id', 'scenario']
    
    def get_cash_cycle_days(self, obj):
        """DSO + DIO - DPO"""
        return obj.receivables_days_dso + obj.inventory_days_dio - obj.payables_days_dpo


class DepreciationScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepreciationSchedule
        exclude = ['id', 'scenario']


class DividendPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = DividendPolicy
        exclude = ['id', 'scenario']


class ExitValuationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExitValuation
        exclude = ['id', 'scenario']


# ============================================================================
# SCENARIO SERIALIZER - Complete with all inputs
# ============================================================================

class ScenarioDetailSerializer(serializers.ModelSerializer):
    """
    Complete scenario with all input categories
    Used for GET requests to retrieve all data
    """
    project_info = ProjectInformationSerializer(required=False)
    macro_assumptions = MacroAssumptionsSerializer(required=False)
    revenue_products = RevenueProductSerializer(many=True, required=False)
    operating_expenses = OperatingExpensesSerializer(required=False)
    capital_expenditure = CapitalExpenditureSerializer(required=False)
    debt_financing = DebtFinancingSerializer(required=False)
    tax_assumptions = TaxAssumptionsSerializer(required=False)
    working_capital = WorkingCapitalSerializer(required=False)
    depreciation_schedules = DepreciationScheduleSerializer(many=True, required=False)
    dividend_policy = DividendPolicySerializer(required=False)
    exit_valuation = ExitValuationSerializer(required=False)
    
    class Meta:
        model = Scenario
        fields = [
            'id', 'name', 'scenario_type', 'is_active', 'created_at',
            'project_info', 'macro_assumptions', 'revenue_products',
            'operating_expenses', 'capital_expenditure', 'debt_financing',
            'tax_assumptions', 'working_capital', 'depreciation_schedules',
            'dividend_policy', 'exit_valuation'
        ]


class ScenarioCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Writable scenario serializer for POST/PUT/PATCH
    Accepts nested input data
    """
    project_info = ProjectInformationSerializer(required=False)
    macro_assumptions = MacroAssumptionsSerializer(required=False)
    revenue_products = RevenueProductSerializer(many=True, required=False)
    operating_expenses = OperatingExpensesSerializer(required=False)
    capital_expenditure = CapitalExpenditureSerializer(required=False)
    debt_financing = DebtFinancingSerializer(required=False)
    tax_assumptions = TaxAssumptionsSerializer(required=False)
    working_capital = WorkingCapitalSerializer(required=False)
    depreciation_schedules = DepreciationScheduleSerializer(many=True, required=False)
    dividend_policy = DividendPolicySerializer(required=False)
    exit_valuation = ExitValuationSerializer(required=False)
    
    class Meta:
        model = Scenario
        fields = [
            'id', 'model', 'name', 'scenario_type', 'is_active',
            'project_info', 'macro_assumptions', 'revenue_products',
            'operating_expenses', 'capital_expenditure', 'debt_financing',
            'tax_assumptions', 'working_capital', 'depreciation_schedules',
            'dividend_policy', 'exit_valuation'
        ]
    
    def create(self, validated_data):
        """Handle nested creation of all input categories"""
        # Extract nested data
        project_info_data = validated_data.pop('project_info', None)
        macro_data = validated_data.pop('macro_assumptions', None)
        revenue_products_data = validated_data.pop('revenue_products', [])
        opex_data = validated_data.pop('operating_expenses', None)
        capex_data = validated_data.pop('capital_expenditure', None)
        debt_data = validated_data.pop('debt_financing', None)
        tax_data = validated_data.pop('tax_assumptions', None)
        wc_data = validated_data.pop('working_capital', None)
        depreciation_data = validated_data.pop('depreciation_schedules', [])
        dividend_data = validated_data.pop('dividend_policy', None)
        valuation_data = validated_data.pop('exit_valuation', None)
        
        # Create scenario
        scenario = Scenario.objects.create(**validated_data)
        
        # Create nested objects
        if project_info_data:
            ProjectInformation.objects.create(scenario=scenario, **project_info_data)
        
        if macro_data:
            MacroAssumptions.objects.create(scenario=scenario, **macro_data)
        
        for product_data in revenue_products_data:
            RevenueProduct.objects.create(scenario=scenario, **product_data)
        
        if opex_data:
            OperatingExpenses.objects.create(scenario=scenario, **opex_data)
        
        if capex_data:
            CapitalExpenditure.objects.create(scenario=scenario, **capex_data)
        
        if debt_data:
            DebtFinancing.objects.create(scenario=scenario, **debt_data)
        
        if tax_data:
            TaxAssumptions.objects.create(scenario=scenario, **tax_data)
        
        if wc_data:
            WorkingCapital.objects.create(scenario=scenario, **wc_data)
        
        for dep_data in depreciation_data:
            DepreciationSchedule.objects.create(scenario=scenario, **dep_data)
        
        if dividend_data:
            DividendPolicy.objects.create(scenario=scenario, **dividend_data)
        
        if valuation_data:
            ExitValuation.objects.create(scenario=scenario, **valuation_data)
        
        return scenario
    
    def update(self, instance, validated_data):
        """Handle nested updates"""
        # Update nested OneToOne fields
        one_to_one_fields = {
            'project_info': (ProjectInformation, ProjectInformationSerializer),
            'macro_assumptions': (MacroAssumptions, MacroAssumptionsSerializer),
            'operating_expenses': (OperatingExpenses, OperatingExpensesSerializer),
            'capital_expenditure': (CapitalExpenditure, CapitalExpenditureSerializer),
            'debt_financing': (DebtFinancing, DebtFinancingSerializer),
            'tax_assumptions': (TaxAssumptions, TaxAssumptionsSerializer),
            'working_capital': (WorkingCapital, WorkingCapitalSerializer),
            'dividend_policy': (DividendPolicy, DividendPolicySerializer),
            'exit_valuation': (ExitValuation, ExitValuationSerializer),
        }
        
        for field_name, (model_class, serializer_class) in one_to_one_fields.items():
            if field_name in validated_data:
                nested_data = validated_data.pop(field_name)
                try:
                    nested_instance = getattr(instance, field_name)
                    # Update existing
                    for attr, value in nested_data.items():
                        setattr(nested_instance, attr, value)
                    nested_instance.save()
                except model_class.DoesNotExist:
                    # Create new
                    model_class.objects.create(scenario=instance, **nested_data)
        
        # Handle many-to-many like fields (revenue_products, depreciation_schedules)
        if 'revenue_products' in validated_data:
            products_data = validated_data.pop('revenue_products')
            # Delete existing and recreate (simpler than complex update logic)
            instance.revenue_products.all().delete()
            for product_data in products_data:
                RevenueProduct.objects.create(scenario=instance, **product_data)
        
        if 'depreciation_schedules' in validated_data:
            dep_data = validated_data.pop('depreciation_schedules')
            instance.depreciation_schedules.all().delete()
            for schedule_data in dep_data:
                DepreciationSchedule.objects.create(scenario=instance, **schedule_data)
        
        # Update scenario fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        return instance


# ============================================================================
# FINANCIAL MODEL SERIALIZERS
# ============================================================================

class ScenarioListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for scenario list"""
    class Meta:
        model = Scenario
        fields = ['id', 'name', 'scenario_type', 'is_active', 'created_at']


class FinancialModelListSerializer(serializers.ModelSerializer):
    """List view of financial models"""
    project_type_display = serializers.CharField(source='get_project_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = FinancialModel
        fields = [
            'id', 'name', 'project_type', 'project_type_display',
            'status', 'status_display', 'completion_percentage',
            'created_at', 'updated_at', 'last_calculated_at'
        ]


class FinancialModelDetailSerializer(serializers.ModelSerializer):
    """Detail view with scenarios"""
    scenarios = ScenarioListSerializer(many=True, read_only=True)
    project_type_display = serializers.CharField(source='get_project_type_display', read_only=True)
    
    class Meta:
        model = FinancialModel
        fields = [
            'id', 'name', 'project_type', 'project_type_display', 'status',
            'created_at', 'updated_at', 'last_calculated_at',
            'completion_percentage', 'is_calculation_in_progress',
            'calculation_error', 'scenarios'
        ]


class FinancialModelCreateSerializer(serializers.ModelSerializer):
    """Create new financial model"""
    class Meta:
        model = FinancialModel
        fields = ['name', 'project_type']
    
    def create(self, validated_data):
        # Set owner from request context
        validated_data['owner'] = self.context['request'].user
        model = FinancialModel.objects.create(**validated_data)
        
        # Auto-create Base Case scenario
        Scenario.objects.create(
            model=model,
            name='Base Case',
            scenario_type='base'
        )
        
        return model

    def to_representation(self, instance):
        return FinancialModelDetailSerializer(instance, context=self.context).data



# ============================================================================
# OUTPUT SERIALIZERS - Calculated Results
# ============================================================================

class CalculatedStatementSerializer(serializers.ModelSerializer):
    statement_type_display = serializers.CharField(source='get_statement_type_display', read_only=True)
    
    class Meta:
        model = CalculatedStatement
        fields = [
            'id', 'statement_type', 'statement_type_display',
            'line_item', 'values_by_period', 'calculated_at'
        ]


# ============================================================================
# TEMPLATE SERIALIZERS
# ============================================================================

class ModelTemplateSerializer(serializers.ModelSerializer):
    """For saving and loading templates"""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = ModelTemplate
        fields = [
            'id', 'name', 'description', 'project_type',
            'is_public', 'template_data', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class TemplateCreateFromScenarioSerializer(serializers.Serializer):
    """
    Serializer for creating a template from an existing scenario
    """
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    is_public = serializers.BooleanField(default=False)
    scenario_id = serializers.IntegerField()
    
    def validate_scenario_id(self, value):
        """Ensure scenario exists and user has access"""
        user = self.context['request'].user
        try:
            scenario = Scenario.objects.get(id=value, model__owner=user)
            return value
        except Scenario.DoesNotExist:
            raise serializers.ValidationError("Scenario not found or access denied")
    
    def create(self, validated_data):
        """Create template from scenario data"""
        user = self.context['request'].user
        scenario_id = validated_data['scenario_id']
        scenario = Scenario.objects.get(id=scenario_id)
        
        # Serialize all scenario data
        scenario_serializer = ScenarioDetailSerializer(scenario)
        template_data = scenario_serializer.data
        
        # Create template
        template = ModelTemplate.objects.create(
            name=validated_data['name'],
            description=validated_data.get('description', ''),
            project_type=scenario.model.project_type,
            created_by=user,
            is_public=validated_data.get('is_public', False),
            template_data=template_data
        )
        
        return template


# ============================================================================
# CALCULATION LOG SERIALIZER
# ============================================================================

class CalculationLogSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(source='triggered_by.username', read_only=True)
    
    class Meta:
        model = CalculationLog
        fields = [
            'id', 'status', 'started_at', 'completed_at',
            'duration_seconds', 'error_message', 'triggered_by_name'
        ]