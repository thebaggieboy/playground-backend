"""
Enhanced Django Models for Financial Modeling Application
Supports 170+ input variables from enhanced-input-model-page.tsx
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json

User = get_user_model()


class FinancialModel(models.Model):
    """
    Represents a financial model instance with enhanced metadata
    """
    PROJECT_TYPE_CHOICES = [
        ('manufacturing', 'Manufacturing'),
        ('real_estate', 'Real Estate'),
        ('energy', 'Energy & Power'),
        ('oil_gas', 'Oil & Gas'),
        ('healthcare', 'Healthcare'),
        ('technology', 'Technology'),
        ('agriculture', 'Agriculture'),
        ('infrastructure', 'Infrastructure'),
        ('general', 'General'),
    ]
    
    PROJECT_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='financial_models')
    project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES, default='general')
    status = models.CharField(max_length=20, choices=PROJECT_STATUS_CHOICES, default='draft')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_calculated_at = models.DateTimeField(null=True, blank=True)
    completion_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Template reference (if created from template)
    source_template = models.ForeignKey('ModelTemplate', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Calculation status
    is_calculation_in_progress = models.BooleanField(default=False)
    calculation_error = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['owner', '-updated_at']),
            models.Index(fields=['project_type']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_project_type_display()})"


class Scenario(models.Model):
    """
    Scenarios: Base Case, Upside, Downside
    """
    SCENARIO_TYPE_CHOICES = [
        ('base', 'Base Case'),
        ('upside', 'Upside Case'),
        ('downside', 'Downside Case'),
        ('custom', 'Custom Scenario'),
    ]
    
    model = models.ForeignKey(FinancialModel, on_delete=models.CASCADE, related_name='scenarios')
    name = models.CharField(max_length=100)
    scenario_type = models.CharField(max_length=20, choices=SCENARIO_TYPE_CHOICES, default='base')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['scenario_type', 'name']
        unique_together = ('model', 'scenario_type')
    
    def __str__(self):
        return f"{self.model.name} - {self.name}"


# ============================================================================
# INPUT MODELS - Organized by Category (matching enhanced-input-model-page.tsx)
# ============================================================================

class ProjectInformation(models.Model):
    """
    Category 1: Project Information & Timeline
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='project_info')
    
    # Basic Details
    project_name = models.CharField(max_length=255)
    project_location = models.CharField(max_length=255, blank=True)
    industry_sector = models.CharField(max_length=100)
    project_type = models.CharField(max_length=50)  # Greenfield, Brownfield, etc.
    
    # Timeline
    project_commencement_date = models.DateField()
    construction_start_date = models.DateField()
    construction_duration_months = models.IntegerField()
    construction_end_date = models.DateField()
    operations_start_date = models.DateField()
    operations_duration_years = models.IntegerField()
    
    # Capacity & Production (Detail Mode)
    total_capacity = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    capacity_unit = models.CharField(max_length=50, blank=True)
    maximum_plant_availability = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    availability_during_tam = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    commissioning_availability = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    factory_capacity_multiplier = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True)
    
    # Phase Implementation
    number_of_phases = models.IntegerField(default=1)
    phase_1_capacity = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    phase_2_capacity = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    
    # Time Constraints
    days_in_year = models.IntegerField(default=365)
    hours_in_day = models.IntegerField(default=24)


class MacroAssumptions(models.Model):
    """
    Category 2: Macro Economic & General Assumptions
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='macro_assumptions')
    
    # Currency & Exchange
    reporting_currency = models.CharField(max_length=10, default='USD')
    exchange_rate_local_per_usd = models.DecimalField(max_digits=15, decimal_places=5)
    
    # Model Setup
    base_year = models.IntegerField()
    periodicity = models.CharField(max_length=20, default='Annually')  # Monthly, Quarterly, Annually
    number_of_years = models.IntegerField()
    model_tolerance = models.DecimalField(max_digits=10, decimal_places=5, default=0.001)
    
    # Inflation
    local_inflation_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    foreign_inflation_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    longterm_target_inflation = models.DecimalField(max_digits=5, decimal_places=2)  # %
    revenue_opex_escalation_usd = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    # Financial Rates
    discount_rate_wacc = models.DecimalField(max_digits=5, decimal_places=2)  # %
    risk_free_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    benchmark_rate_type = models.CharField(max_length=20, default='SOFR')  # SOFR, MPR, LIBOR, etc.
    benchmark_rate_value = models.DecimalField(max_digits=5, decimal_places=2)  # %
    terminal_growth_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    contingency_buffer = models.DecimalField(max_digits=5, decimal_places=2)  # %


class RevenueProduct(models.Model):
    """
    Revenue products/streams - supports 1-10 products per scenario
    """
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name='revenue_products')
    product_order = models.IntegerField(default=1)
    
    # Product Details
    product_name = models.CharField(max_length=255)
    unit_of_measure = models.CharField(max_length=50)
    
    # Volume & Pricing (Manufacturing/Energy)
    year_1_sales_volume = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unit_price_year_1 = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    volume_growth_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    price_escalation_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    
    # Real Estate Specific
    number_of_units = models.IntegerField(null=True, blank=True)
    gba_gross_building_area = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    lettable_area = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    sale_price_per_unit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    
    # Advanced Parameters
    receivables_days_dso = models.IntegerField(null=True, blank=True)
    revenue_rampup_months = models.IntegerField(null=True, blank=True)
    seasonal_adjustment_factor = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    sales_absorption_period_months = models.IntegerField(null=True, blank=True)  # Real estate
    presales_offplan_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # Real estate
    market_share_target = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    
    class Meta:
        ordering = ['product_order']
        unique_together = ('scenario', 'product_order')


class OperatingExpenses(models.Model):
    """
    Category 4: Operating Expenses
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='operating_expenses')
    
    # Raw Materials & Variable Costs (Manufacturing/Energy)
    raw_material_cost_per_unit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    raw_material_price_escalation = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    variable_cost_pct_revenue = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    fuel_gas_cost_per_mmbtu = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Energy
    
    # Labor & Personnel
    total_headcount = models.IntegerField()
    average_annual_salary = models.DecimalField(max_digits=15, decimal_places=2)
    salary_escalation_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    benefits_payroll_tax_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of salary
    
    # Utilities & Facilities
    power_electricity_cost_annual = models.DecimalField(max_digits=20, decimal_places=2)
    water_gas_utilities_annual = models.DecimalField(max_digits=20, decimal_places=2)
    utilities_escalation_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    property_management_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # Real estate
    
    # Maintenance & Insurance
    regular_maintenance_pct_revenue = models.DecimalField(max_digits=5, decimal_places=2)  # %
    insurance_annual = models.DecimalField(max_digits=20, decimal_places=2)
    tam_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)  # Turn Around Maintenance
    tam_frequency_years = models.IntegerField(null=True, blank=True)
    
    # Additional OpEx
    marketing_sales_pct_revenue = models.DecimalField(max_digits=5, decimal_places=2)  # %
    administrative_expenses_annual = models.DecimalField(max_digits=20, decimal_places=2)
    rent_facilities_annual = models.DecimalField(max_digits=20, decimal_places=2)
    technology_software_annual = models.DecimalField(max_digits=20, decimal_places=2)
    professional_fees_annual = models.DecimalField(max_digits=20, decimal_places=2)
    payables_days_dpo = models.IntegerField()


class CapitalExpenditure(models.Model):
    """
    Category 5: Capital Expenditure
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='capital_expenditure')
    
    # Core CAPEX
    land_cost = models.DecimalField(max_digits=20, decimal_places=2)
    construction_building_cost = models.DecimalField(max_digits=20, decimal_places=2)
    equipment_machinery_cost = models.DecimalField(max_digits=20, decimal_places=2)
    ffe_cost = models.DecimalField(max_digits=20, decimal_places=2)  # Furniture, Fixtures, Equipment
    
    # Real Estate Specific
    carpark_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    amenities_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    apartment_construction_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    hotel_commercial_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    
    # Additional Costs
    contingency_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of total capex
    professional_fees_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of capex
    permits_approvals_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of capex
    vat_on_construction_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    # Capitalized Interest
    capitalize_interest = models.BooleanField(default=True)
    construction_loan_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    
    # CAPEX Phasing
    year_1_drawdown_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    year_2_drawdown_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    year_3_drawdown_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    # Ongoing CAPEX
    replacement_capex_pct_revenue = models.DecimalField(max_digits=5, decimal_places=2)  # %
    expansion_capex = models.DecimalField(max_digits=20, decimal_places=2, default=0)


class DebtFinancing(models.Model):
    """
    Category 6: Debt & Financing
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='debt_financing')
    
    # Funding Mix
    equity_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # %
    debt_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # %
    offplan_presales_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # %
    
    # Debt Terms
    interest_rate_type = models.CharField(max_length=20, default='Floating')  # Fixed, Floating, Mixed
    base_rate_type = models.CharField(max_length=20, default='SOFR')  # SOFR, MPR, LIBOR, Prime
    base_rate_value = models.DecimalField(max_digits=5, decimal_places=2)  # %
    interest_margin_spread = models.DecimalField(max_digits=5, decimal_places=2)  # %
    loan_tenor_years = models.IntegerField()
    
    # Advanced Parameters
    grace_period_months = models.IntegerField(default=0)
    repayment_type = models.CharField(max_length=50, default='Amortizing')  # Amortizing, Bullet, Sculpted
    dsra_requirement_months = models.IntegerField(default=6)  # Debt Service Reserve Account
    dsra_funding_source = models.CharField(max_length=20, default='Cash')  # Cash, Letter of Credit, Mixed
    upfront_fees_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of loan
    commitment_fee_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % p.a.
    
    # Drawdown
    drawdown_linked_to = models.CharField(max_length=50, default='CAPEX Schedule')
    drawdown_frequency = models.CharField(max_length=20, default='Quarterly')


class TaxAssumptions(models.Model):
    """
    Category 7: Tax Assumptions
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='tax_assumptions')
    
    # Core Tax Rates
    corporate_income_tax_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    tax_holiday_years = models.IntegerField(default=0)
    minimum_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # %
    vat_sales_tax_rate = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    # Withholding Taxes
    wht_dividends = models.DecimalField(max_digits=5, decimal_places=2)  # %
    wht_interest = models.DecimalField(max_digits=5, decimal_places=2)  # %
    wht_services = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # %
    wht_rent = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # %
    
    # Other Provisions
    education_tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # % of assessable profit
    tax_loss_carryforward_years = models.IntegerField(default=5)
    
    # Capital Allowances
    initial_allowance_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    annual_allowance_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %


class WorkingCapital(models.Model):
    """
    Category 8: Working Capital
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='working_capital')
    
    # Core Metrics
    initial_wc_pct_year1_opex = models.DecimalField(max_digits=5, decimal_places=2)  # %
    receivables_days_dso = models.IntegerField()
    inventory_days_dio = models.IntegerField()
    payables_days_dpo = models.IntegerField()
    
    # Additional Parameters
    wc_pct_revenue = models.DecimalField(max_digits=5, decimal_places=2)  # %
    minimum_cash_balance = models.DecimalField(max_digits=20, decimal_places=2)
    wc_funding_source = models.CharField(max_length=50, default='From Equity')
    wc_reserve_account = models.BooleanField(default=False)


class DepreciationSchedule(models.Model):
    """
    Category 9: Depreciation by Asset Category
    """
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name='depreciation_schedules')
    
    ASSET_CATEGORY_CHOICES = [
        ('land', 'Land & Land Improvements'),
        ('buildings', 'Buildings & Structures'),
        ('equipment', 'Plant, Equipment & Machinery'),
        ('ffe', 'Furniture, Fixtures & Equipment'),
        ('vehicles_it', 'Vehicles & IT Equipment'),
    ]
    
    DEPRECIATION_METHOD_CHOICES = [
        ('straight_line', 'Straight Line'),
        ('declining_balance', 'Declining Balance'),
        ('units_of_production', 'Units of Production'),
        ('sum_of_years', 'Sum of Years Digits'),
    ]
    
    asset_category = models.CharField(max_length=50, choices=ASSET_CATEGORY_CHOICES)
    depreciation_method = models.CharField(max_length=50, choices=DEPRECIATION_METHOD_CHOICES, default='straight_line')
    asset_value = models.DecimalField(max_digits=20, decimal_places=2)
    useful_life_years = models.IntegerField()
    residual_value_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    class Meta:
        unique_together = ('scenario', 'asset_category')


class DividendPolicy(models.Model):
    """
    Category 10: Dividend & Shareholder
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='dividend_policy')
    
    # Core Policy
    dividend_payout_ratio_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of net income
    dividend_payment_frequency = models.CharField(max_length=20, default='Annually')
    minimum_cash_before_dividend = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Advanced Parameters
    minimum_dscr_for_dividend = models.DecimalField(max_digits=5, decimal_places=2, default=1.3)
    minimum_llcr_for_dividend = models.DecimalField(max_digits=5, decimal_places=2, default=1.5)
    preferred_dividend_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # % p.a.
    share_buyback_provision = models.BooleanField(default=False)
    dividend_wht_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    dividend_reinvestment_option = models.BooleanField(default=False)


class ExitValuation(models.Model):
    """
    Category 11: Exit & Valuation
    """
    scenario = models.OneToOneField(Scenario, on_delete=models.CASCADE, related_name='exit_valuation')
    
    # Core Valuation
    exit_year = models.IntegerField()
    exit_multiple_ev_ebitda = models.DecimalField(max_digits=5, decimal_places=2)  # x
    terminal_growth_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    discount_rate_npv_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    target_irr_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    
    # Alternative Methods
    pe_multiple = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # x
    price_book_multiple = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # x
    revenue_multiple = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # x
    asset_sale_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    transaction_costs_pct = models.DecimalField(max_digits=5, decimal_places=2)  # % of exit value
    valuation_method = models.CharField(max_length=50, default='DCF')  # DCF, Multiple-based, Asset-based, Hybrid
    
    # Return Metrics
    target_equity_irr_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    target_project_irr_pct = models.DecimalField(max_digits=5, decimal_places=2)  # %
    payback_period_target_years = models.IntegerField()
    minimum_moic = models.DecimalField(max_digits=5, decimal_places=2)  # Multiple on Invested Capital


# ============================================================================
# OUTPUT MODELS - Calculated Results
# ============================================================================

class CalculatedStatement(models.Model):
    """
    Stores calculated financial statements (IS, BS, CFS)
    Replaces FinancialStatementLineItem with time-series support
    """
    STATEMENT_TYPE_CHOICES = [
        ('is', 'Income Statement'),
        ('bs', 'Balance Sheet'),
        ('cfs', 'Cash Flow Statement'),
        ('ratio', 'Financial Ratios'),
        ('debt', 'Debt Schedule'),
        ('valuation', 'Valuation Metrics'),
    ]
    
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name='calculated_statements')
    statement_type = models.CharField(max_length=20, choices=STATEMENT_TYPE_CHOICES)
    line_item = models.CharField(max_length=100)
    
    # Store time series data as JSON for efficiency
    # Format: {"2025": 1000000, "2026": 1100000, ...}
    values_by_period = models.JSONField()
    
    # Metadata
    formula_used = models.TextField(blank=True)  # For audit trail
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('scenario', 'statement_type', 'line_item')
        indexes = [
            models.Index(fields=['scenario', 'statement_type']),
        ]


# ============================================================================
# TEMPLATE MODELS
# ============================================================================

class ModelTemplate(models.Model):
    """
    Reusable templates that users can save and load
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    project_type = models.CharField(max_length=50)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_templates')
    is_public = models.BooleanField(default=False)  # Public templates visible to all users
    is_system_template = models.BooleanField(default=False)  # Built-in templates
    
    # Store all input data as JSON for easy loading
    template_data = models.JSONField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


# ============================================================================
# AUDIT & HISTORY
# ============================================================================

class CalculationLog(models.Model):
    """
    Tracks all calculation runs for debugging and audit
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name='calculation_logs')
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)
    
    # Performance metrics
    duration_seconds = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']