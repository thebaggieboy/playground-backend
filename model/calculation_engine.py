"""
Financial Calculation Engine
Implements 3-statement financial model with formulas
Based on standard financial modeling practices
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Optional
import logging

from .models import (
    Scenario, CalculatedStatement, CalculationLog,
    ProjectInformation, MacroAssumptions, RevenueProduct,
    OperatingExpenses, CapitalExpenditure, DebtFinancing,
    TaxAssumptions, WorkingCapital, DepreciationSchedule,
    DividendPolicy, ExitValuation
)

logger = logging.getLogger(__name__)


class InvalidIndustryLibraryInputError(ValueError):
    pass


class CalculationInputError(ValueError):
    pass


class CalculationEngine:
    """
    Main calculation engine for 3-statement financial models
    """
    
    def __init__(self):
        self.scenario = None
        self.periods = []
        self.results = {}
        
        # Cached related models for sensitivity overrides
        self.macro = None
        self.project_info = None
        self.opex = None
        self.capex = None
        self.tax = None
        self.debt = None
        self.valuation = None
        self.revenue_products = []
        self.dep_schedules = []
        
    def calculate_scenario(self, scenario: Scenario, user=None, save_results=True, overrides=None):
        """
        Main entry point for calculating a complete scenario
        Returns: dict with calculation results
        """
        self.scenario = scenario
        self._prepare_scenario(overrides)
        self._validate_scenario_inputs()
        
        # Create calculation log
        log = None
        if save_results:
            log = CalculationLog.objects.create(
                scenario=scenario,
                triggered_by=user,
                status='running'
            )
        
        start_time = timezone.now()
        
        try:
            # Step 1: Generate time periods
            self.periods = self._generate_periods()
            
            # Step 2: Calculate Revenue
            revenue_schedule = self._calculate_revenue()
            
            # Step 3: Calculate Operating Expenses
            opex_schedule = self._calculate_opex(revenue_schedule)
            
            # Step 4: Calculate Depreciation
            depreciation_schedule = self._calculate_depreciation()
            
            # Step 5: Calculate CAPEX Schedule
            capex_schedule = self._calculate_capex(revenue_schedule)
            
            # Step 6: Calculate Debt Schedule
            debt_schedule = self._calculate_debt(capex_schedule)
            
            # Step 7: Build Income Statement
            income_statement = self._build_income_statement(
                revenue_schedule, opex_schedule, depreciation_schedule, debt_schedule
            )
            
            # Step 8: Build Cash Flow Statement
            cash_flow_statement = self._build_cash_flow_statement(
                income_statement, capex_schedule, debt_schedule, depreciation_schedule
            )
            
            # Step 9: Build Balance Sheet
            balance_sheet = self._build_balance_sheet(
                income_statement, cash_flow_statement, capex_schedule, 
                debt_schedule, depreciation_schedule
            )
            self._validate_statement_outputs(
                income_statement, balance_sheet, cash_flow_statement, debt_schedule
            )
            
            # Step 10: Calculate Financial Ratios
            ratios = self._calculate_ratios(
                income_statement, balance_sheet, cash_flow_statement, debt_schedule
            )
            
            # Step 11: Calculate Valuation Metrics
            valuation = self._calculate_valuation(
                income_statement, cash_flow_statement, debt_schedule
            )

            self._validate_balance_sheet(balance_sheet)
            
            # Step 12: Save all results
            if save_results:
                with transaction.atomic():
                    self._save_results(
                        income_statement, balance_sheet, cash_flow_statement,
                        ratios, valuation, debt_schedule,
                        revenue_schedule, opex_schedule, capex_schedule, depreciation_schedule
                    )
            
            # Update log
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            if log:
                log.status = 'success'
                log.completed_at = end_time
                log.duration_seconds = Decimal(str(duration))
                log.save()
                
            if not save_results:
                return {
                    'status': 'success',
                    'npv': float(valuation.get('NPV', 0)),
                    'irr': float(valuation['IRR (%)']) if valuation.get('IRR (%)') is not None else None,
                    'peak_revenue': float(max(income_statement.get('Total Revenue', {str(self.periods[0]): 0}).values())),
                    'peak_ebitda': float(max(income_statement.get('EBITDA', {str(self.periods[0]): 0}).values())),
                    'duration_seconds': duration
                }
            
            return self._prepare_for_json({
                'status': 'success',
                'periods_calculated': len(self.periods),
                'duration_seconds': duration
            })
            
        except Exception as e:
            logger.error(f"Calculation error for scenario {scenario.id}: {str(e)}")
            
            # Update log
            if log:
                end_time = timezone.now()
                duration = (end_time - start_time).total_seconds()
                log.status = 'failed'
                log.completed_at = end_time
                log.duration_seconds = Decimal(str(duration))
                log.error_message = str(e)
                import traceback
                log.error_traceback = traceback.format_exc()
                log.save()
            
            raise

    def _validate_scenario_inputs(self):
        required_relations = {
            "project_info": self.project_info,
            "macro_assumptions": self.macro,
            "operating_expenses": self.opex,
            "capital_expenditure": self.capex,
            "debt_financing": self.debt,
            "tax_assumptions": self.tax,
            "working_capital": getattr(self, "working_capital", None),
            "exit_valuation": self.valuation,
        }
        missing = [name for name, value in required_relations.items() if value is None]
        if missing:
            raise CalculationInputError(
                "Complete the required model sections before calculation: " + ", ".join(missing) + "."
            )
        if not self.revenue_products:
            raise CalculationInputError("At least one revenue product is required.")
        if not self.dep_schedules:
            raise CalculationInputError("At least one asset depreciation schedule is required.")

        project = self.project_info
        macro = self.macro
        capex = self.capex
        debt = self.debt
        if macro.periodicity.lower() not in {"annual", "annually", "yearly"}:
            raise CalculationInputError(
                "The current model engine supports annual forecasts only. Select Annually for model periodicity."
            )
        if macro.number_of_years < 1 or macro.number_of_years > 100:
            raise CalculationInputError("Forecast duration must be between 1 and 100 years.")
        if project.operations_duration_years < 1:
            raise CalculationInputError("Operating life must be at least one year.")
        if project.construction_duration_months < 0:
            raise CalculationInputError("Construction duration cannot be negative.")
        if project.construction_start_date.year < macro.base_year:
            raise CalculationInputError(
                "The forecast base year must be on or before the construction start year."
            )
        if project.operations_start_date <= project.construction_start_date:
            raise CalculationInputError("Operations must start after construction begins.")
        if project.operations_start_date.year >= macro.base_year + macro.number_of_years:
            raise CalculationInputError("The forecast must include at least one operating year.")
        if project.total_capacity is None or project.total_capacity <= 0:
            raise CalculationInputError("Project rated capacity must be greater than zero.")
        if project.days_in_year not in (365, 366):
            raise CalculationInputError("Days in year must be either 365 or 366.")
        if project.hours_in_day < 1 or project.hours_in_day > 24:
            raise CalculationInputError("Hours in day must be between 1 and 24.")

        drawdowns = [
            capex.year_1_drawdown_pct,
            capex.year_2_drawdown_pct,
            capex.year_3_drawdown_pct,
        ]
        if any(value < 0 for value in drawdowns) or sum(drawdowns) != Decimal("100"):
            raise CalculationInputError("Construction drawdown percentages must be non-negative and total 100%.")

        funding_mix = debt.debt_percentage + debt.equity_percentage
        if debt.debt_percentage < 0 or debt.equity_percentage < 0 or funding_mix != Decimal("100"):
            raise CalculationInputError("Debt and equity percentages must be non-negative and total 100%.")
        if debt.loan_tenor_years < 1:
            raise CalculationInputError("Debt tenor must be at least one year.")
        if debt.grace_period_months < 0:
            raise CalculationInputError("Debt grace period cannot be negative.")
        if debt.base_rate_value + debt.interest_margin_spread < 0:
            raise CalculationInputError("The all-in debt interest rate cannot be negative.")
        if debt.upfront_fees_pct < 0 or debt.commitment_fee_pct < 0:
            raise CalculationInputError("Debt fees cannot be negative.")
        if any(
            value < 0
            for value in (
                self.working_capital.receivables_days_dso,
                self.working_capital.inventory_days_dio,
                self.working_capital.payables_days_dpo,
            )
        ):
            raise CalculationInputError("Working-capital day assumptions cannot be negative.")
        if self.working_capital.minimum_cash_balance < 0:
            raise CalculationInputError("Minimum cash balance cannot be negative.")
        if debt.dsra_requirement_months < 0 or debt.dsra_requirement_months > 12:
            raise CalculationInputError("DSRA coverage must be between 0 and 12 months.")
        if debt.dsra_funding_source.lower() not in {"cash"}:
            raise CalculationInputError(
                "Only cash-funded DSRA is supported; letters of credit and mixed funding are not modeled."
            )

        for product in self.revenue_products:
            volume = product.year_1_sales_volume
            price = product.unit_price_year_1
            is_property_sale = bool(product.number_of_units and product.sale_price_per_unit)
            if not is_property_sale and (
                volume is None or volume <= 0 or price is None or price <= 0
            ):
                raise CalculationInputError(
                    f"Revenue product '{product.product_name}' needs positive year-one volume and price."
                )
            if product.volume_growth_rate is not None and product.volume_growth_rate <= -100:
                raise CalculationInputError(
                    f"Revenue product '{product.product_name}' growth must be greater than -100%."
                )
            if product.price_escalation_rate is not None and product.price_escalation_rate <= -100:
                raise CalculationInputError(
                    f"Revenue product '{product.product_name}' price escalation must be greater than -100%."
                )
        for schedule in self.dep_schedules:
            if schedule.useful_life_years < 0 or not Decimal("0") <= schedule.residual_value_pct <= Decimal("100"):
                raise CalculationInputError(
                    f"Depreciation inputs for '{schedule.get_asset_category_display()}' are invalid."
                )
            if schedule.depreciation_method == "units_of_production":
                raise CalculationInputError(
                    "Units-of-production depreciation requires asset-specific production units, which are not currently provided."
                )
        if self.valuation.discount_rate_npv_pct <= -100:
            raise CalculationInputError("The project discount rate must be greater than -100%.")
        if not 1 <= self.valuation.exit_year <= macro.number_of_years:
            raise CalculationInputError("Exit year must fall within the forecast horizon.")
        if not Decimal("0") <= self.valuation.transaction_costs_pct <= Decimal("100"):
            raise CalculationInputError("Exit transaction costs must be between 0% and 100%.")
        if self.debt.repayment_type.strip().lower().startswith("sculpted"):
            raise CalculationInputError(
                "Sculpted repayment requires a debt-service schedule, which is not yet provided."
            )

    def _validate_balance_sheet(self, balance_sheet):
        checks = balance_sheet.get("Balance Check (should be 0)", {})
        tolerance = Decimal(str(self.macro.model_tolerance))
        for period, difference in checks.items():
            assets = abs(balance_sheet.get("Total Assets", {}).get(period, Decimal("0")))
            allowed_difference = max(Decimal("0.01"), assets * tolerance)
            if abs(difference) > allowed_difference:
                raise CalculationInputError(
                    f"Balance sheet does not balance in {period}: difference {difference} "
                    f"exceeds tolerance {allowed_difference}."
                )

    def _validate_statement_outputs(
        self, income_statement, balance_sheet, cash_flow_statement, debt_schedule
    ):
        required_lines = (
            (income_statement, ("Total Revenue", "EBITDA", "EBIT", "EBT", "Net Income")),
            (
                balance_sheet,
                ("Cash", "Debt Service Reserve Account", "Total Assets", "Total Liabilities", "Total Equity", "Balance Check (should be 0)"),
            ),
            (
                cash_flow_statement,
                ("Changes in Working Capital", "Cash Flow from Operations", "Cash Flow from Investing", "Cash Balance (End)", "DSRA Closing Balance", "Equity Drawdowns", "Dividends Paid"),
            ),
            (
                debt_schedule,
                ("Opening Balance", "Drawdowns", "Principal Repayment", "Interest Expense", "Closing Balance"),
            ),
        )
        expected_periods = set(self.periods)
        for statement, lines in required_lines:
            for line in lines:
                values = statement.get(line)
                if not isinstance(values, dict) or set(values) != expected_periods:
                    raise CalculationInputError(
                        f"Calculation did not produce a complete '{line}' schedule for every forecast year."
                    )

    
    def _prepare_scenario(self, overrides):
        def relation(name, default=None):
            try:
                return getattr(self.scenario, name)
            except ObjectDoesNotExist:
                return default

        self.macro = relation("macro_assumptions")
        self.project_info = relation("project_info")
        self.opex = relation("operating_expenses")
        self.capex = relation("capital_expenditure")
        self.tax = relation("tax_assumptions")
        self.debt = relation("debt_financing")
        self.valuation = relation("exit_valuation")
        self.working_capital = relation("working_capital")
        self.dividend_policy = relation("dividend_policy")
        self.revenue_products = list(self.scenario.revenue_products.all())
        self.dep_schedules = list(self.scenario.depreciation_schedules.all())

        if not overrides: return
        
        if 'revenue_growth_adj' in overrides:
            adj = Decimal(str(overrides['revenue_growth_adj']))
            for p in self.revenue_products:
                if p.volume_growth_rate is not None:
                    p.volume_growth_rate += adj

        if 'opex_margin_adj' in overrides and self.opex:
            adj = Decimal(str(overrides['opex_margin_adj']))
            if self.opex.total_headcount:
                self.opex.total_headcount = int(self.opex.total_headcount * (1 + float(adj)))
            if self.opex.administrative_expenses_annual:
                self.opex.administrative_expenses_annual *= (1 + adj)
            if self.opex.rent_facilities_annual:
                self.opex.rent_facilities_annual *= (1 + adj)
            if self.opex.technology_software_annual:
                self.opex.technology_software_annual *= (1 + adj)
            if self.opex.professional_fees_annual:
                self.opex.professional_fees_annual *= (1 + adj)
                
        if 'capex_cost_adj' in overrides and self.capex:
            adj = Decimal(str(overrides['capex_cost_adj']))
            if self.capex.land_cost:
                self.capex.land_cost *= (1 + adj)
            if self.capex.construction_building_cost:
                self.capex.construction_building_cost *= (1 + adj)
            if self.capex.equipment_machinery_cost:
                self.capex.equipment_machinery_cost *= (1 + adj)
            if self.capex.ffe_cost:
                self.capex.ffe_cost *= (1 + adj)
                
        if 'discount_rate_adj' in overrides and self.macro:
            adj = Decimal(str(overrides['discount_rate_adj']))
            if self.macro.discount_rate_wacc is not None:
                self.macro.discount_rate_wacc += adj

    def _prepare_for_json(self, data):
        """Recursively convert Decimal to float for JSON serialization"""
        if isinstance(data, dict):
            return {k: self._prepare_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_for_json(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self._prepare_for_json(item) for item in data)
        elif isinstance(data, Decimal) or type(data).__name__ == 'Decimal':
            return float(data)
        return data
    
    def _generate_periods(self) -> List[str]:
        """
        Generate annual forecast periods from the configured base year.
        """
        if not self.macro or self.macro.base_year is None or self.macro.number_of_years is None:
            raise CalculationInputError("A valid forecast base year and duration are required.")
        return [str(self.macro.base_year + i) for i in range(self.macro.number_of_years)]
    
    def _calculate_revenue(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate revenue for all products across all periods
        Returns: {'ProductName': {'2025': 1000000, '2026': 1150000, ...}}
        """
        revenue_schedule = {}
        operations_start = self.project_info.operations_start_date
        operations_year = operations_start.year

        for product in self.revenue_products:
            product_revenue = {}
            volume_year_one = Decimal(str(product.year_1_sales_volume or "0"))
            price_year_one = Decimal(str(product.unit_price_year_1 or "0"))
            volume_growth = Decimal(str(product.volume_growth_rate or "0")) / Decimal("100")
            price_growth = Decimal(str(product.price_escalation_rate or "0")) / Decimal("100")
            is_property_sale = bool(product.number_of_units and product.sale_price_per_unit)
            total_sale_units = Decimal(str(product.number_of_units or 0))
            remaining_units = total_sale_units
            absorption_months = Decimal(str(product.sales_absorption_period_months or 24))

            if (
                volume_year_one == 0
                and self.project_info.industry_sector == "Energy & Power"
                and self.project_info.industry_sub_type == "Solar"
                and product.unit_of_measure.strip().lower() in {"mwh", "mwh/year", "mwh per year"}
            ):
                scope = f"{self.project_info.industry_sector}:{self.project_info.industry_sub_type}:project"
                inputs = self.project_info.industry_library_inputs
                project_inputs = inputs.get(scope, {}) if isinstance(inputs, dict) else {}
                p50_yield = project_inputs.get("p50Yield")
                if p50_yield not in (None, ""):
                    try:
                        volume_year_one = Decimal(str(p50_yield))
                    except (InvalidOperation, ValueError, TypeError) as exc:
                        raise InvalidIndustryLibraryInputError(
                            "Solar P50 annual yield must be a valid number."
                        ) from exc
                    if not volume_year_one.is_finite() or volume_year_one < 0:
                        raise InvalidIndustryLibraryInputError(
                            "Solar P50 annual yield must be finite and non-negative."
                        )

            for period in self.periods:
                year = int(period)
                operating_fraction = self._operating_fraction_in_year(year, operations_start)
                if operating_fraction == 0:
                    product_revenue[period] = Decimal("0")
                    continue

                years_from_operations = year - operations_year
                price = price_year_one * ((Decimal("1") + price_growth) ** years_from_operations)
                if is_property_sale:
                    units_sold = min(remaining_units, total_sale_units * min(
                        Decimal("1"),
                        Decimal("12") * operating_fraction / absorption_months,
                    ))
                    remaining_units -= units_sold
                    revenue = units_sold * Decimal(str(product.sale_price_per_unit)) * (
                        (Decimal("1") + price_growth) ** years_from_operations
                    )
                else:
                    ramp_months = Decimal(str(product.revenue_rampup_months or 0))
                    if ramp_months > 0 and year == operations_year:
                        active_months = operating_fraction * Decimal("12")
                        if ramp_months >= active_months:
                            operating_fraction *= active_months / (Decimal("2") * ramp_months)
                        else:
                            operating_fraction = (
                                active_months - ramp_months / Decimal("2")
                            ) / Decimal("12")
                    volume = volume_year_one * (
                        (Decimal("1") + volume_growth) ** years_from_operations
                    ) * operating_fraction
                    revenue = volume * price

                seasonal_factor = Decimal(str(product.seasonal_adjustment_factor or 1))
                product_revenue[period] = (revenue * seasonal_factor).quantize(Decimal("0.01"))
            revenue_schedule[product.product_name] = product_revenue

        return revenue_schedule

    @staticmethod
    def _add_years(value, years):
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year + years)

    def _operating_fraction_in_year(self, year, operations_start):
        period_start = datetime(year, 1, 1).date()
        period_end = datetime(year + 1, 1, 1).date()
        operations_end = self._add_years(
            operations_start,
            self.project_info.operations_duration_years,
        )
        active_start = max(period_start, operations_start)
        active_end = min(period_end, operations_end)
        if active_end <= active_start:
            return Decimal("0")
        return Decimal((active_end - active_start).days) / Decimal((period_end - period_start).days)
    
    def _calculate_opex(self, revenue_schedule) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate annual operating costs, prorated for partial operating years.
        """
        opex_schedule = {}
        opex = self.opex
        macro = self.macro
        operations_start = self.project_info.operations_start_date
        operations_year = operations_start.year
        annual_staff = Decimal(opex.total_headcount) * opex.average_annual_salary
        annual_staff *= Decimal("1") + opex.benefits_payroll_tax_pct / Decimal("100")
        annual_utilities = opex.power_electricity_cost_annual + opex.water_gas_utilities_annual
        annual_other = (
            opex.administrative_expenses_annual
            + opex.rent_facilities_annual
            + opex.technology_software_annual
            + opex.professional_fees_annual
        )
        revenue_total = {
            period: sum((product.get(period, Decimal("0")) for product in revenue_schedule.values()), Decimal("0"))
            for period in self.periods
        }
        inflation = Decimal("1") + macro.local_inflation_rate / Decimal("100")
        staff_escalation = Decimal("1") + opex.salary_escalation_rate / Decimal("100")
        utilities_escalation = Decimal("1") + opex.utilities_escalation_rate / Decimal("100")
        fixed_schedule = {
            "Staff Costs": {},
            "Utilities": {},
            "Other Operating Expenses": {},
            "Insurance": {},
        }

        for period in self.periods:
            year = int(period)
            operating_fraction = self._operating_fraction_in_year(year, operations_start)
            operating_year = max(0, year - operations_year)
            fixed_schedule["Staff Costs"][period] = (
                annual_staff * staff_escalation ** operating_year * operating_fraction
            ).quantize(Decimal("0.01"))
            fixed_schedule["Utilities"][period] = (
                annual_utilities * utilities_escalation ** operating_year * operating_fraction
            ).quantize(Decimal("0.01"))
            fixed_schedule["Other Operating Expenses"][period] = (
                annual_other * inflation ** operating_year * operating_fraction
            ).quantize(Decimal("0.01"))
            fixed_schedule["Insurance"][period] = (
                opex.insurance_annual * inflation ** operating_year * operating_fraction
            ).quantize(Decimal("0.01"))

        opex_schedule.update(fixed_schedule)

        variable_costs = {}
        maintenance = {}
        marketing = {}
        property_management = {}
        for period in self.periods:
            revenue = revenue_total[period]
            variable_costs[period] = (
                revenue * Decimal(str(opex.variable_cost_pct_revenue or 0)) / Decimal("100")
            ).quantize(Decimal("0.01"))
            maintenance[period] = (
                revenue * opex.regular_maintenance_pct_revenue / Decimal("100")
            ).quantize(Decimal("0.01"))
            marketing[period] = (
                revenue * opex.marketing_sales_pct_revenue / Decimal("100")
            ).quantize(Decimal("0.01"))
            property_management[period] = (
                revenue * Decimal(str(opex.property_management_pct or 0)) / Decimal("100")
            ).quantize(Decimal("0.01"))
        opex_schedule["Variable Operating Costs"] = variable_costs
        opex_schedule["Maintenance"] = maintenance
        opex_schedule["Marketing & Sales"] = marketing
        if opex.property_management_pct:
            opex_schedule["Property Management"] = property_management

        if opex.tam_cost and opex.tam_frequency_years:
            tam_schedule = {}
            for period in self.periods:
                year = int(period)
                operating_year = year - operations_year
                is_operating = self._operating_fraction_in_year(year, operations_start) > 0
                due = is_operating and operating_year > 0 and operating_year % opex.tam_frequency_years == 0
                tam_schedule[period] = (
                    (opex.tam_cost * self._operating_fraction_in_year(year, operations_start)).quantize(Decimal("0.01"))
                    if due else Decimal("0")
                )
            opex_schedule["TAM Expenses"] = tam_schedule

        return opex_schedule
    
    def _calculate_depreciation(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate asset depreciation with straight-line, declining-balance and SYD methods.
        """
        depreciation_schedule = {}
        operations_start = self.project_info.operations_start_date
        operations_year = operations_start.year

        for schedule in self.dep_schedules:
            category_dep = {}
            life = schedule.useful_life_years
            residual = schedule.asset_value * schedule.residual_value_pct / Decimal("100")
            net_book_value = schedule.asset_value

            for period in self.periods:
                year = int(period)
                operating_fraction = self._operating_fraction_in_year(year, operations_start)
                year_number = year - operations_year
                depreciation = Decimal("0")
                if life > 0 and year_number >= 0 and year_number < life and operating_fraction > 0:
                    if schedule.depreciation_method == "straight_line":
                        annual = (schedule.asset_value - residual) / Decimal(life)
                    elif schedule.depreciation_method == "declining_balance":
                        annual = max(
                            Decimal("0"),
                            net_book_value * Decimal("2") / Decimal(life),
                        )
                    elif schedule.depreciation_method == "sum_of_years":
                        denominator = Decimal(life * (life + 1)) / Decimal("2")
                        remaining_life = Decimal(life - year_number)
                        annual = (schedule.asset_value - residual) * remaining_life / denominator
                    else:
                        raise CalculationInputError(
                            f"Depreciation method '{schedule.depreciation_method}' is not supported."
                        )
                    depreciation = min(
                        max(Decimal("0"), net_book_value - residual),
                        annual * operating_fraction,
                    )
                    net_book_value -= depreciation
                category_dep[period] = depreciation.quantize(Decimal("0.01"))

            depreciation_schedule[schedule.get_asset_category_display()] = category_dep

        return depreciation_schedule
    
    def _calculate_capex(self, revenue_schedule) -> Dict[str, Decimal]:
        """
        Phase initial investment, expansion and revenue-linked sustaining CAPEX.
        """
        capex = self.capex
        project = self.project_info
        hard_costs = sum((
            capex.land_cost,
            capex.construction_building_cost,
            capex.equipment_machinery_cost,
            capex.ffe_cost,
            capex.carpark_cost or Decimal("0"),
            capex.amenities_cost or Decimal("0"),
            capex.apartment_construction_cost or Decimal("0"),
            capex.hotel_commercial_cost or Decimal("0"),
        ), Decimal("0"))
        soft_cost_pct = (
            capex.contingency_pct
            + capex.professional_fees_pct
            + capex.permits_approvals_pct
            + capex.vat_on_construction_pct
        )
        initial_capex = hard_costs * (Decimal("1") + soft_cost_pct / Decimal("100"))
        phases = (
            capex.year_1_drawdown_pct,
            capex.year_2_drawdown_pct,
            capex.year_3_drawdown_pct,
        )
        construction_start_year = project.construction_start_date.year
        revenue_total = {
            period: sum((product.get(period, Decimal("0")) for product in revenue_schedule.values()), Decimal("0"))
            for period in self.periods
        }
        operations_year = project.operations_start_date.year
        capex_schedule = {}

        for period in self.periods:
            year = int(period)
            construction_year = year - construction_start_year
            value = (
                initial_capex * phases[construction_year] / Decimal("100")
                if 0 <= construction_year < len(phases)
                else Decimal("0")
            )
            operating_fraction = self._operating_fraction_in_year(
                year,
                project.operations_start_date,
            )
            if operating_fraction > 0:
                value += (
                    revenue_total[period]
                    * capex.replacement_capex_pct_revenue
                    / Decimal("100")
                )
                if year == operations_year:
                    value += capex.expansion_capex
            capex_schedule[period] = value.quantize(Decimal("0.01"))

        return capex_schedule
    
    def _calculate_debt(self, capex_schedule) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate annual debt drawdowns, interest and amortization / bullet repayment.
        """
        debt_schedule = {
            'Opening Balance': {},
            'Drawdowns': {},
            'Capitalized Interest': {},
            'Upfront Fees': {},
            'Commitment Fees': {},
            'Principal Repayment': {},
            'Interest Expense': {},
            'Closing Balance': {},
        }
        debt = self.debt
        capex = self.capex
        project = self.project_info
        hard_costs = sum((
            capex.land_cost,
            capex.construction_building_cost,
            capex.equipment_machinery_cost,
            capex.ffe_cost,
            capex.carpark_cost or Decimal("0"),
            capex.amenities_cost or Decimal("0"),
            capex.apartment_construction_cost or Decimal("0"),
            capex.hotel_commercial_cost or Decimal("0"),
        ), Decimal("0"))
        initial_capex = hard_costs * (
            Decimal("1")
            + (
                capex.contingency_pct
                + capex.professional_fees_pct
                + capex.permits_approvals_pct
                + capex.vat_on_construction_pct
            ) / Decimal("100")
        )
        debt_facility = initial_capex * debt.debt_percentage / Decimal("100")
        remaining_facility = debt_facility
        annual_rate = (
            debt.base_rate_value + debt.interest_margin_spread
        ) / Decimal("100")
        operations_year = project.operations_start_date.year
        grace_years = (debt.grace_period_months + 11) // 12
        repayment_start_year = operations_year + grace_years
        maturity_year = operations_year + debt.loan_tenor_years - 1
        repayment_mode = debt.repayment_type.strip().lower()
        is_bullet = repayment_mode.startswith("bullet")
        if not is_bullet and not repayment_mode.startswith("amortizing"):
            raise CalculationInputError(
                f"Repayment type '{debt.repayment_type}' needs a custom schedule and is not supported by this MVP."
            )
        closing_balance = Decimal("0")

        for period in self.periods:
            year = int(period)
            opening_balance = closing_balance
            debt_schedule["Opening Balance"][period] = opening_balance
            construction_offset = year - project.construction_start_date.year
            facility_before_draw = remaining_facility
            if 0 <= construction_offset <= 2:
                eligible_drawdown = max(Decimal("0"), capex_schedule.get(period, Decimal("0"))) * (
                    debt.debt_percentage / Decimal("100")
                )
                drawdown = min(remaining_facility, eligible_drawdown)
            else:
                drawdown = Decimal("0")
            remaining_facility -= drawdown
            is_construction = year < operations_year
            capitalized_interest = Decimal("0")
            if is_construction and capex.capitalize_interest:
                capitalization_rate = (
                    capex.construction_loan_interest_rate
                    if capex.construction_loan_interest_rate is not None
                    else debt.base_rate_value + debt.interest_margin_spread
                ) / Decimal("100")
                capitalized_interest = max(
                    Decimal("0"),
                    (opening_balance + drawdown / Decimal("2")) * capitalization_rate,
                ).quantize(Decimal("0.01"))
                capex_schedule[period] = (
                    capex_schedule.get(period, Decimal("0")) + capitalized_interest
                ).quantize(Decimal("0.01"))

            upfront_fee = (
                drawdown * Decimal(str(debt.upfront_fees_pct)) / Decimal("100")
            ).quantize(Decimal("0.01"))
            commitment_fee = Decimal("0")
            if year <= maturity_year:
                undrawn_commitment = max(
                    Decimal("0"),
                    facility_before_draw - drawdown / Decimal("2"),
                )
                commitment_fee = (
                    undrawn_commitment * Decimal(str(debt.commitment_fee_pct)) / Decimal("100")
                ).quantize(Decimal("0.01"))

            operating_interest = Decimal("0")
            if not (is_construction and capex.capitalize_interest):
                operating_interest = max(
                    Decimal("0"),
                    (opening_balance + drawdown / Decimal("2")) * annual_rate,
                ).quantize(Decimal("0.01"))
            total_interest_expense = operating_interest + upfront_fee + commitment_fee
            debt_schedule["Capitalized Interest"][period] = capitalized_interest
            debt_schedule["Upfront Fees"][period] = upfront_fee
            debt_schedule["Commitment Fees"][period] = commitment_fee
            debt_schedule["Drawdowns"][period] = (drawdown + capitalized_interest).quantize(Decimal("0.01"))
            debt_schedule["Interest Expense"][period] = total_interest_expense.quantize(Decimal("0.01"))

            principal = Decimal("0")
            balance_before_repayment = opening_balance + drawdown + capitalized_interest
            if balance_before_repayment > 0 and year >= repayment_start_year:
                if year >= maturity_year or is_bullet:
                    principal = balance_before_repayment
                else:
                    remaining_payments = maturity_year - year + 1
                    payment = self._calculate_pmt(
                        balance_before_repayment,
                        annual_rate,
                        remaining_payments,
                    )
                    principal = min(
                        balance_before_repayment,
                        max(Decimal("0"), payment - operating_interest),
                    )
            debt_schedule["Principal Repayment"][period] = principal.quantize(Decimal("0.01"))
            closing_balance = max(Decimal("0"), balance_before_repayment - principal)
            debt_schedule["Closing Balance"][period] = closing_balance.quantize(Decimal("0.01"))

        return debt_schedule
    
    def _calculate_pmt(self, pv: Decimal, rate: Decimal, nper: int) -> Decimal:
        """
        Calculate payment amount using PMT formula
        PMT = PV * (rate * (1 + rate)^nper) / ((1 + rate)^nper - 1)
        """
        if rate == 0:
            return pv / Decimal(nper)
        
        rate_decimal = Decimal(str(rate))
        factor = (1 + rate_decimal) ** nper
        pmt = pv * (rate_decimal * factor) / (factor - 1)
        return pmt
    
    def _build_income_statement(
        self, revenue_schedule, opex_schedule, depreciation_schedule, debt_schedule
    ) -> Dict[str, Dict[str, Decimal]]:
        is_data: Dict[str, Dict[str, Decimal]] = {}
        tax = self.tax
        total_revenue = {
            period: sum(
                (values.get(period, Decimal("0")) for values in revenue_schedule.values()),
                Decimal("0"),
            )
            for period in self.periods
        }
        total_opex = {
            period: sum(
                (values.get(period, Decimal("0")) for values in opex_schedule.values()),
                Decimal("0"),
            )
            for period in self.periods
        }
        depreciation = {
            period: sum(
                (values.get(period, Decimal("0")) for values in depreciation_schedule.values()),
                Decimal("0"),
            )
            for period in self.periods
        }
        ebitda = {period: total_revenue[period] - total_opex[period] for period in self.periods}
        ebit = {period: ebitda[period] - depreciation[period] for period in self.periods}
        interest = debt_schedule["Interest Expense"]
        ebt = {
            period: ebit[period] - interest.get(period, Decimal("0"))
            for period in self.periods
        }

        operations_year = self.project_info.operations_start_date.year
        losses = []
        income_tax = {}
        education_tax = {}
        tax_expense = {}
        net_income = {}
        for period in self.periods:
            year = int(period)
            taxable_profit = ebt[period]
            if taxable_profit < 0:
                if tax.tax_loss_carryforward_years > 0:
                    losses.append([year, -taxable_profit])
                taxable_profit = Decimal("0")
            else:
                remaining = taxable_profit
                carryforward = []
                for loss_year, loss_amount in losses:
                    if year - loss_year <= tax.tax_loss_carryforward_years and remaining > 0:
                        applied = min(remaining, loss_amount)
                        loss_amount -= applied
                        remaining -= applied
                    if loss_amount > 0 and year - loss_year <= tax.tax_loss_carryforward_years:
                        carryforward.append([loss_year, loss_amount])
                losses = carryforward
                taxable_profit = remaining

            holiday_active = year < operations_year + tax.tax_holiday_years
            tax_rate = Decimal("0") if holiday_active else tax.corporate_income_tax_rate / Decimal("100")
            income_tax[period] = (taxable_profit * tax_rate).quantize(Decimal("0.01"))
            education_tax[period] = (
                Decimal("0")
                if holiday_active
                else (
                    taxable_profit * tax.education_tax_pct / Decimal("100")
                ).quantize(Decimal("0.01"))
            )
            tax_expense[period] = income_tax[period] + education_tax[period]
            net_income[period] = ebt[period] - tax_expense[period]

        is_data["Total Revenue"] = total_revenue
        is_data["Total Operating Expenses"] = total_opex
        is_data["EBITDA"] = ebitda
        is_data["Depreciation"] = depreciation
        is_data["EBIT"] = ebit
        is_data["Interest Expense"] = interest
        is_data["EBT"] = ebt
        is_data["Corporate Tax"] = income_tax
        is_data["Education Tax"] = education_tax
        is_data["Tax Expense"] = tax_expense
        is_data["Net Income"] = net_income
        return is_data
    
    def _build_cash_flow_statement(
        self, income_statement, capex_schedule, debt_schedule, depreciation_schedule
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Build cash flow statement
        """
        cfs_data: Dict[str, Dict[str, Decimal]] = {}
        
        try:
            # Operating Cash Flow
            # Start with Net Income
            cfs_data['Net Income'] = income_statement['Net Income']
            
            # Add back Depreciation (non-cash)
            cfs_data['Depreciation'] = income_statement['Depreciation']
            
            # Changes in Working Capital
            changes_in_wc = {p: Decimal('0') for p in self.periods}
            wc_assets = {p: Decimal('0') for p in self.periods}
            wc_liabilities = {p: Decimal('0') for p in self.periods}
            
            if getattr(self, 'working_capital', None):
                rec_days = Decimal(str(self.working_capital.receivables_days_dso))
                pay_days = Decimal(str(self.working_capital.payables_days_dpo))
                inv_days = Decimal(str(self.working_capital.inventory_days_dio))
                day_count = Decimal(str(self.project_info.days_in_year or 365))
                day_count = Decimal(str(self.project_info.days_in_year or 365))

                prev_nwc = Decimal('0')
                for period in self.periods:
                    revenue = income_statement['Total Revenue'].get(period, Decimal('0'))
                    opex = income_statement['Total Operating Expenses'].get(period, Decimal('0'))
                    
                    ar = revenue * rec_days / day_count
                    inv = opex * inv_days / day_count
                    ap = opex * pay_days / day_count
                    
                    wc_assets[period] = (ar + inv).quantize(Decimal('0.01'))
                    wc_liabilities[period] = ap.quantize(Decimal('0.01'))
                    
                    current_nwc = ar + inv - ap
                    changes_in_wc[period] = (current_nwc - prev_nwc).quantize(Decimal('0.01'))
                    prev_nwc = current_nwc
            
            self._wc_assets = wc_assets
            self._wc_liabilities = wc_liabilities
            cfs_data['Changes in Working Capital'] = changes_in_wc
            
            # Cash Flow from Operations
            cfo = {}
            for period in self.periods:
                cfo[period] = (
                    income_statement['Net Income'][period] +
                    income_statement['Depreciation'][period] -
                    changes_in_wc[period]
                )
            
            cfs_data['Cash Flow from Operations'] = cfo
            
            # Investing Cash Flow
            # CAPEX (negative)
            capex_cf = {p: -capex_schedule.get(p, Decimal('0')) for p in self.periods}
            cfs_data['Capital Expenditure'] = capex_cf
            
            cfs_data['Cash Flow from Investing'] = capex_cf
            
            # Financing Cash Flow
            # Debt Drawdowns (positive)
            cfs_data['Debt Drawdowns'] = debt_schedule['Drawdowns']
            
            # Debt Repayment (negative)
            debt_repayment = {p: -debt_schedule['Principal Repayment'][p] for p in self.periods}
            cfs_data['Debt Repayment'] = debt_repayment
            
            # Interest (negative)
            interest_cf = {p: -debt_schedule['Interest Expense'][p] for p in self.periods}
            cfs_data['Interest Paid'] = interest_cf
            
            # Cash Flow from Financing & Net Cash Flow
            cff = {}
            equity_drawdowns = {}
            dividends_paid = {}
            net_cf = {}
            cash_balance = Decimal('0')
            cash_end = {}
            minimum_cash = self.working_capital.minimum_cash_balance if getattr(self, 'working_capital', None) else Decimal("0")
            dsra_targets = {}
            for i, period in enumerate(self.periods):
                service_period = self.periods[i + 1] if i + 1 < len(self.periods) else period
                service = (
                    debt_schedule['Principal Repayment'][service_period]
                    + debt_schedule['Interest Expense'][service_period]
                )
                if (
                    i + 1 == len(self.periods)
                    and debt_schedule['Closing Balance'][period] <= 0
                ):
                    service = Decimal('0')
                dsra_targets[period] = (
                    service * Decimal(str(self.debt.dsra_requirement_months)) / Decimal('12')
                ).quantize(Decimal('0.01'))
            dsra_deposits, dsra_releases, dsra_closing = {}, {}, {}
            prior_dsra_balance = Decimal('0')

            for period in self.periods:
                reserve_target = dsra_targets[period]
                dsra_increase = max(Decimal('0'), reserve_target - prior_dsra_balance)
                dsra_release = max(Decimal('0'), prior_dsra_balance - reserve_target)
                dsra_deposits[period] = dsra_increase
                dsra_releases[period] = dsra_release
                dsra_closing[period] = reserve_target
                # Calculate cash needs BEFORE equity funding and dividends
                cash_needs = (
                    cfo.get(period, Decimal('0')) + 
                    capex_cf.get(period, Decimal('0')) + 
                    debt_schedule['Drawdowns'].get(period, Decimal('0')) + 
                    debt_repayment.get(period, Decimal('0')) -
                    dsra_increase + dsra_release
                )
                
                # Check for dividends (only if net_income > 0)
                net_income = income_statement['Net Income'].get(period, Decimal('0'))
                dividend = Decimal('0')
                if getattr(self, 'dividend_policy', None) and net_income > 0:
                    payout = self.dividend_policy.dividend_payout_ratio_pct / Decimal('100')
                    min_cash_req = self.dividend_policy.minimum_cash_before_dividend
                    potential_dividend = net_income * payout
                    
                    # Available cash before equity = opening cash + net activities
                    available_cash = cash_balance + cash_needs
                    
                    if available_cash > max(min_cash_req, minimum_cash):
                        dividend = min(potential_dividend, available_cash - max(min_cash_req, minimum_cash))
                
                dividends_paid[period] = -dividend.quantize(Decimal('0.01'))
                cash_needs += dividends_paid[period]  # Cash needs becomes more negative (or stays same)
                
                # If opening cash + cash_needs < 0, we need sponsor equity to plug the gap
                cash_deficit = minimum_cash - (cash_balance + cash_needs)
                
                if cash_deficit > 0:
                    equity_drawdown = cash_deficit
                else:
                    equity_drawdown = Decimal('0')
                    
                equity_drawdowns[period] = equity_drawdown
                
                cff[period] = (
                    debt_schedule['Drawdowns'].get(period, Decimal('0')) +
                    debt_repayment.get(period, Decimal('0')) +
                    equity_drawdown + 
                    dividends_paid[period] -
                    dsra_increase + dsra_release
                )
                
                net_cf[period] = cfo.get(period, Decimal('0')) + capex_cf.get(period, Decimal('0')) + cff[period]
                cash_balance += net_cf[period]
                cash_end[period] = cash_balance
                prior_dsra_balance = reserve_target
                
            cfs_data['Dividends Paid'] = dividends_paid
            cfs_data['Equity Drawdowns'] = equity_drawdowns
            cfs_data['Cash Flow from Financing'] = cff
            cfs_data['Net Cash Flow'] = net_cf
            cfs_data['Cash Balance (End)'] = cash_end
            cfs_data['DSRA Target'] = dsra_targets
            cfs_data['DSRA Deposit'] = dsra_deposits
            cfs_data['DSRA Release'] = dsra_releases
            cfs_data['DSRA Closing Balance'] = dsra_closing
            
        except Exception as e:
            logger.error(f"Error building cash flow statement: {str(e)}")
        
        return cfs_data
    
    def _build_balance_sheet(
        self, income_statement, cash_flow_statement, capex_schedule, 
        debt_schedule, depreciation_schedule
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Build balance sheet
        """
        bs_data = {}
        
        try:
            # ASSETS
            # Cash
            bs_data['Cash'] = cash_flow_statement['Cash Balance (End)']
            bs_data['Debt Service Reserve Account'] = cash_flow_statement['DSRA Closing Balance']
            
            # Fixed Assets (Net)
            net_fixed_assets = {}
            accumulated_capex = Decimal('0')
            accumulated_depreciation = Decimal('0')
            
            for period in self.periods:
                accumulated_capex += capex_schedule.get(period, Decimal('0'))
                accumulated_depreciation += income_statement['Depreciation'][period]
                net_fixed_assets[period] = accumulated_capex - accumulated_depreciation
            
            bs_data['Net Fixed Assets'] = net_fixed_assets
            
            # Working Capital Assets
            bs_data['Working Capital Assets'] = getattr(self, '_wc_assets', {p: Decimal('0') for p in self.periods})
            
            # Total Assets
            total_assets = {}
            for period in self.periods:
                total_assets[period] = (
                    bs_data['Cash'][period] +
                    bs_data['Debt Service Reserve Account'][period] +
                    bs_data['Working Capital Assets'][period] +
                    net_fixed_assets[period]
                )
            
            bs_data['Total Assets'] = total_assets
            
            # LIABILITIES
            # Debt
            bs_data['Debt'] = debt_schedule['Closing Balance']
            
            # Working Capital Liabilities
            bs_data['Working Capital Liabilities'] = getattr(self, '_wc_liabilities', {p: Decimal('0') for p in self.periods})
            
            # Total Liabilities
            total_liabilities = {}
            for period in self.periods:
                total_liabilities[period] = (
                    debt_schedule['Closing Balance'][period] +
                    bs_data['Working Capital Liabilities'][period]
                )
            bs_data['Total Liabilities'] = total_liabilities
            
            # EQUITY
            # Retained Earnings (cumulative net income - dividends)
            retained_earnings = {}
            cumulative_ni = Decimal('0')
            
            for period in self.periods:
                cumulative_ni += income_statement['Net Income'][period]
                cumulative_ni += cash_flow_statement.get('Dividends Paid', {}).get(period, Decimal('0'))
                retained_earnings[period] = cumulative_ni
            
            bs_data['Retained Earnings'] = retained_earnings
            
            # Paid-In Capital (Cumulative Equity Drawdowns)
            cumulative_equity = Decimal('0')
            paid_in_capital = {}
            
            for period in self.periods:
                cumulative_equity += cash_flow_statement.get('Equity Drawdowns', {}).get(period, Decimal('0'))
                paid_in_capital[period] = cumulative_equity
                
            bs_data['Paid-In Capital'] = paid_in_capital
            
            # Total Equity
            total_equity = {}
            for period in self.periods:
                total_equity[period] = paid_in_capital[period] + retained_earnings[period]
                
            bs_data['Total Equity'] = total_equity
            
            # Balance Check: Assets = Liabilities + Equity
            balance_check = {}
            for period in self.periods:
                check = total_assets[period] - (
                    bs_data['Total Liabilities'][period] +
                    bs_data['Total Equity'][period]
                )
                balance_check[period] = check
            
            bs_data['Balance Check (should be 0)'] = balance_check
            
        except Exception as e:
            logger.error(f"Error building balance sheet: {str(e)}")
        
        return bs_data
    
    def _calculate_ratios(
        self, income_statement, balance_sheet, cash_flow_statement, debt_schedule
    ) -> Dict[str, Dict[str, Optional[Decimal]]]:
        ratios = {}
        ebitda_margin, net_margin, roe, roa, dscr = {}, {}, {}, {}, {}
        llcr, plcr, debt_to_equity = {}, {}, {}
        cost_of_debt = float(
            (self.debt.base_rate_value + self.debt.interest_margin_spread) / Decimal("100")
        )
        if cost_of_debt <= -1:
            raise CalculationInputError("The debt discount rate must be greater than -100%.")

        for i, period in enumerate(self.periods):
            revenue = income_statement["Total Revenue"][period]
            assets = balance_sheet["Total Assets"][period]
            equity = balance_sheet["Total Equity"][period]
            ebitda_margin[period] = (income_statement["EBITDA"][period] / revenue * 100).quantize(Decimal("0.01")) if revenue else None
            net_margin[period] = (income_statement["Net Income"][period] / revenue * 100).quantize(Decimal("0.01")) if revenue else None
            roe[period] = (income_statement["Net Income"][period] / equity * 100).quantize(Decimal("0.01")) if equity > 0 else None
            roa[period] = (income_statement["Net Income"][period] / assets * 100).quantize(Decimal("0.01")) if assets > 0 else None

            debt_service = debt_schedule["Principal Repayment"][period] + debt_schedule["Interest Expense"][period]
            cfads = cash_flow_statement["Cash Flow from Operations"][period] + debt_schedule["Interest Expense"][period]
            dscr[period] = (cfads / debt_service).quantize(Decimal("0.01")) if debt_service > 0 else None

            outstanding_debt = debt_schedule["Opening Balance"][period]
            if outstanding_debt > 0:
                future_periods = self.periods[i:]
                loan_periods = [
                    p for p in future_periods
                    if debt_schedule["Closing Balance"][p] > 0
                    or debt_schedule["Principal Repayment"][p] > 0
                ]
                llcr_pv = sum(
                    float(cash_flow_statement["Cash Flow from Operations"][p] + debt_schedule["Interest Expense"][p])
                    / ((1 + cost_of_debt) ** (offset + 1))
                    for offset, p in enumerate(loan_periods)
                )
                plcr_pv = sum(
                    float(cash_flow_statement["Cash Flow from Operations"][p] + debt_schedule["Interest Expense"][p])
                    / ((1 + cost_of_debt) ** (offset + 1))
                    for offset, p in enumerate(future_periods)
                )
                llcr[period] = (Decimal(str(llcr_pv)) / outstanding_debt).quantize(Decimal("0.01"))
                plcr[period] = (Decimal(str(plcr_pv)) / outstanding_debt).quantize(Decimal("0.01"))
            else:
                llcr[period] = None
                plcr[period] = None
            debt_to_equity[period] = (
                (debt_schedule["Closing Balance"][period] / equity).quantize(Decimal("0.01"))
                if equity > 0 else None
            )

        ratios["EBITDA Margin (%)"] = ebitda_margin
        ratios["Net Margin (%)"] = net_margin
        ratios["ROE (%)"] = roe
        ratios["ROA (%)"] = roa
        ratios["DSCR"] = dscr
        ratios["LLCR"] = llcr
        ratios["PLCR"] = plcr
        ratios["Debt-to-Equity"] = debt_to_equity
        return ratios
    
    def _calculate_valuation(
        self, income_statement, cash_flow_statement, debt_schedule
    ) -> Dict[str, object]:
        """
        Calculate valuation metrics (NPV, IRR, etc.) using Unlevered Free Cash Flow (FCFF)
        """
        params = self.valuation
        tax_rate = float(
            (self.tax.corporate_income_tax_rate + self.tax.education_tax_pct) / Decimal("100")
        )
        exit_index = params.exit_year - 1
        exit_period = self.periods[exit_index]
        discount_rate = float(params.discount_rate_npv_pct / Decimal("100"))
        if discount_rate <= -1:
            raise CalculationInputError("The valuation discount rate must be greater than -100%.")

        fcf_series = []
        valuation_periods = self.periods[:exit_index + 1]
        for period in valuation_periods:
            interest = income_statement["Interest Expense"][period]
            investing_cash_flow = cash_flow_statement["Cash Flow from Investing"][period]
            # CFO includes levered tax expense; add back interest net of its tax shield.
            fcf = (
                cash_flow_statement["Cash Flow from Operations"][period]
                + interest * Decimal(str(1 - tax_rate))
                + investing_cash_flow
            )
            fcf_series.append(float(fcf))

        ebitda = income_statement["EBITDA"][exit_period]
        exit_multiple_value = ebitda * params.exit_multiple_ev_ebitda
        growth = float(params.terminal_growth_rate_pct / Decimal("100"))
        wacc = float(self.macro.discount_rate_wacc / Decimal("100"))
        method = params.valuation_method.lower()
        dcf_terminal_value = Decimal("0")
        if method.startswith("dcf") or method.startswith("hybrid"):
            if wacc <= growth:
                raise CalculationInputError("WACC must exceed the terminal growth rate for a DCF terminal value.")
            if fcf_series[exit_index] <= 0:
                raise CalculationInputError(
                    "Terminal-year free cash flow must be positive to calculate a DCF terminal value."
                )
            dcf_terminal_value = Decimal(str(fcf_series[exit_index] * (1 + growth) / (wacc - growth)))
        if method.startswith("multiple"):
            if ebitda <= 0:
                raise CalculationInputError("Exit EBITDA must be positive for an EBITDA-multiple valuation.")
            terminal_value = exit_multiple_value
        elif method.startswith("asset"):
            terminal_value = params.asset_sale_value
        elif method.startswith("hybrid"):
            if ebitda <= 0:
                raise CalculationInputError("Exit EBITDA must be positive for a hybrid valuation.")
            terminal_value = (exit_multiple_value + dcf_terminal_value) / Decimal("2")
        else:
            terminal_value = dcf_terminal_value

        transaction_costs = terminal_value * params.transaction_costs_pct / Decimal("100")
        net_terminal_proceeds = terminal_value - transaction_costs
        fcf_with_terminal = list(fcf_series)
        fcf_with_terminal[exit_index] += float(net_terminal_proceeds)
        npv = self._calculate_npv(fcf_with_terminal, discount_rate)
        irr = self._calculate_irr(fcf_with_terminal)

        cumulative = 0.0
        payback = None
        for i, flow in enumerate(fcf_series):
            previous = cumulative
            cumulative += flow
            if cumulative >= 0 and previous < 0:
                payback = i + (-previous / flow if flow > 0 else 0)
                break

        equity_flows = []
        closing_debt = debt_schedule["Closing Balance"][exit_period]
        closing_cash = (
            cash_flow_statement["Cash Balance (End)"][exit_period]
            + cash_flow_statement["DSRA Closing Balance"][exit_period]
        )
        exit_equity_value = max(
            Decimal("0"),
            terminal_value * (Decimal("1") - params.transaction_costs_pct / Decimal("100"))
            - closing_debt + closing_cash,
        )
        for i, period in enumerate(valuation_periods):
            contributed_equity = cash_flow_statement["Equity Drawdowns"][period]
            dividends_paid = cash_flow_statement["Dividends Paid"][period]
            net_dividend = -dividends_paid * (
                Decimal("1") - self.dividend_policy.dividend_wht_pct / Decimal("100")
                if self.dividend_policy else Decimal("1")
            )
            equity_flow = float(net_dividend - contributed_equity)
            if i == exit_index:
                equity_flow += float(exit_equity_value)
            equity_flows.append(equity_flow)

        equity_irr = self._calculate_irr(equity_flows)
        total_contributed = sum(
            float(cash_flow_statement["Equity Drawdowns"][p]) for p in valuation_periods
        )
        total_distributions = sum(
            float(
                -cash_flow_statement["Dividends Paid"][p]
                * (
                    Decimal("1") - self.dividend_policy.dividend_wht_pct / Decimal("100")
                    if self.dividend_policy else Decimal("1")
                )
            ) for p in valuation_periods
        ) + float(exit_equity_value)
        moic = total_distributions / total_contributed if total_contributed > 0 else None

        valuation = {
            "NPV": Decimal(str(npv)).quantize(Decimal("0.01")),
            "IRR (%)": (Decimal(str(irr * 100)).quantize(Decimal("0.01")) if irr is not None else None),
            "Equity IRR (%)": (Decimal(str(equity_irr * 100)).quantize(Decimal("0.01")) if equity_irr is not None else None),
            "Equity MOIC (x)": (Decimal(str(moic)).quantize(Decimal("0.01")) if moic is not None else None),
            "Payback Period (Years)": (Decimal(str(payback)).quantize(Decimal("0.01")) if payback is not None else None),
            "Terminal Value": terminal_value.quantize(Decimal("0.01")),
            "Exit Transaction Costs": transaction_costs.quantize(Decimal("0.01")),
            "Exit Enterprise Value": terminal_value.quantize(Decimal("0.01")),
            "Exit Equity Value": exit_equity_value.quantize(Decimal("0.01")),
            "Exit Year": params.exit_year,
        }
        return valuation
    
    def _calculate_npv(self, cash_flows: List[float], discount_rate: float) -> float:
        """Calculate Net Present Value"""
        if discount_rate <= -1:
            raise CalculationInputError("The discount rate must be greater than -100%.")
        npv = sum(cf / ((1 + discount_rate) ** (i + 1)) for i, cf in enumerate(cash_flows))
        return npv
    
    def _calculate_irr(self, cash_flows: List[float]) -> Optional[float]:
        """Return a unique IRR when a conventional single sign change has a bounded root."""
        nonzero = [flow for flow in cash_flows if flow != 0]
        if len(nonzero) < 2 or (all(flow > 0 for flow in nonzero) or all(flow < 0 for flow in nonzero)):
            return None
        sign_changes = sum(
            (nonzero[i] > 0) != (nonzero[i - 1] > 0)
            for i in range(1, len(nonzero))
        )
        if sign_changes != 1:
            return None

        low, high = -0.99, 10.0
        low_npv = self._calculate_npv(cash_flows, low)
        high_npv = self._calculate_npv(cash_flows, high)
        if low_npv == 0:
            return low
        if high_npv == 0:
            return high
        if (low_npv > 0) == (high_npv > 0):
            return None
        for _ in range(200):
            mid = (low + high) / 2
            mid_npv = self._calculate_npv(cash_flows, mid)
            if abs(mid_npv) < 1e-8 or high - low < 1e-10:
                return mid
            if (mid_npv > 0) == (low_npv > 0):
                low, low_npv = mid, mid_npv
            else:
                high = mid
        return (low + high) / 2
    
    def _save_results(
        self, income_statement, balance_sheet, cash_flow_statement,
        ratios, valuation, debt_schedule,
        revenue_schedule=None, opex_schedule=None, capex_schedule=None, depreciation_schedule=None
    ):
        """
        Save all calculated results to database.
        All Decimal values are converted to float before saving to avoid
        JSON serialization errors in JSONFields.
        """
        # Clear existing results for this scenario
        CalculatedStatement.objects.filter(scenario=self.scenario).delete()

        # Save Income Statement
        for line_item, values in income_statement.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='is',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Save Balance Sheet
        for line_item, values in balance_sheet.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='bs',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Save Cash Flow Statement
        for line_item, values in cash_flow_statement.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='cfs',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Save Ratios
        for line_item, values in ratios.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='ratio',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Save Valuation Metrics
        CalculatedStatement.objects.create(
            scenario=self.scenario,
            statement_type='valuation',
            line_item='Valuation Metrics',
            values_by_period=self._prepare_for_json(valuation)
        )

        # Save Debt Schedule
        for line_item, values in debt_schedule.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='debt',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Save Revenue Schedule
        if revenue_schedule:
            for line_item, values in revenue_schedule.items():
                CalculatedStatement.objects.create(
                    scenario=self.scenario,
                    statement_type='revenue',
                    line_item=line_item,
                    values_by_period=self._prepare_for_json(values)
                )
        
        # Save OpEx Schedule
        if opex_schedule:
            for line_item, values in opex_schedule.items():
                CalculatedStatement.objects.create(
                    scenario=self.scenario,
                    statement_type='opex',
                    line_item=line_item,
                    values_by_period=self._prepare_for_json(values)
                )

        # Save Fixed Assets / Depreciation Schedule
        if depreciation_schedule:
            for line_item, values in depreciation_schedule.items():
                CalculatedStatement.objects.create(
                    scenario=self.scenario,
                    statement_type='fixed_assets',
                    line_item=line_item,
                    values_by_period=self._prepare_for_json(values)
                )

        # Build and Save Tax Schedule from Income Statement values
        tax_lines = ['Corporate Tax', 'Education Tax', 'VAT / Sales Tax', 'Total Taxes']
        tax_schedule = {k: income_statement.get(k, {}) for k in tax_lines if k in income_statement}
        for line_item, values in tax_schedule.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='tax',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # Build and Save Dividend Schedule from Cash Flow Statement values
        dividend_lines = ['Dividends Paid', 'Retained Earnings', 'Minimum Cash Buffer']
        div_schedule = {k: cash_flow_statement.get(k, {}) for k in dividend_lines if k in cash_flow_statement}
        for line_item, values in div_schedule.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='dividend',
                line_item=line_item,
                values_by_period=self._prepare_for_json(values)
            )

        # ── Receivables & Working Capital Schedule (saved under 'revenue') ──
        if getattr(self, 'working_capital', None):
            rec_days = Decimal(str(self.working_capital.receivables_days_dso))
            pay_days = Decimal(str(self.working_capital.payables_days_dpo))
            inv_days = Decimal(str(self.working_capital.inventory_days_dio))
            day_count = Decimal(str(self.project_info.days_in_year or 365))

            ar_schedule = {}
            ap_schedule = {}
            inv_schedule = {}
            nwc_schedule = {}

            for period in self.periods:
                revenue = income_statement.get('Total Revenue', {}).get(period, Decimal('0'))
                opex = income_statement.get('Total Operating Expenses', {}).get(period, Decimal('0'))

                ar = (revenue * rec_days / day_count).quantize(Decimal('0.01'))
                ap = (opex * pay_days / day_count).quantize(Decimal('0.01'))
                inv = (opex * inv_days / day_count).quantize(Decimal('0.01'))

                ar_schedule[period] = ar
                ap_schedule[period] = ap
                inv_schedule[period] = inv
                nwc_schedule[period] = (ar + inv - ap).quantize(Decimal('0.01'))

            for label, vals in [
                ('Accounts Receivable (DSO)', ar_schedule),
                ('Inventory (DIO)', inv_schedule),
                ('Accounts Payable (DPO)', ap_schedule),
                ('Net Working Capital', nwc_schedule),
            ]:
                CalculatedStatement.objects.create(
                    scenario=self.scenario,
                    statement_type='revenue',
                    line_item=label,
                    values_by_period=self._prepare_for_json(vals)
                )

        for label in ('DSRA Target', 'DSRA Deposit', 'DSRA Release', 'DSRA Closing Balance'):
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='dividend',
                line_item=label,
                values_by_period=self._prepare_for_json(cash_flow_statement[label])
            )

        exit_period = str(self.macro.base_year + self.valuation.exit_year - 1)
        exit_values = {
            'Exit Enterprise Value': valuation['Exit Enterprise Value'],
            'Net Debt at Exit': debt_schedule['Closing Balance'][exit_period]
                - cash_flow_statement['Cash Balance (End)'][exit_period]
                - cash_flow_statement['DSRA Closing Balance'][exit_period],
            'Exit Equity Value': valuation['Exit Equity Value'],
        }
        for label, value in exit_values.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='exit',
                line_item=label,
                values_by_period=self._prepare_for_json({exit_period: value})
            )