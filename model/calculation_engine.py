"""
Financial Calculation Engine
Implements 3-statement financial model with formulas
Based on standard financial modeling practices
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from django.utils import timezone
from typing import Dict, List
import logging

from .models import (
    Scenario, CalculatedStatement, CalculationLog,
    ProjectInformation, MacroAssumptions, RevenueProduct,
    OperatingExpenses, CapitalExpenditure, DebtFinancing,
    TaxAssumptions, WorkingCapital, DepreciationSchedule,
    DividendPolicy, ExitValuation
)

logger = logging.getLogger(__name__)


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
            opex_schedule = self._calculate_opex()
            
            # Step 4: Calculate Depreciation
            depreciation_schedule = self._calculate_depreciation()
            
            # Step 5: Calculate CAPEX Schedule
            capex_schedule = self._calculate_capex()
            
            # Step 6: Calculate Debt Schedule
            debt_schedule = self._calculate_debt()
            
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
            
            # Step 10: Calculate Financial Ratios
            ratios = self._calculate_ratios(
                income_statement, balance_sheet, cash_flow_statement, debt_schedule
            )
            
            # Step 11: Calculate Valuation Metrics
            valuation = self._calculate_valuation(
                income_statement, cash_flow_statement
            )
            
            # Step 12: Save all results
            if save_results:
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
                    'irr': float(valuation.get('IRR (%)', 0)),
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

    
    def _prepare_scenario(self, overrides):
        try: self.macro = self.scenario.macro_assumptions
        except: self.macro = None
        try: self.project_info = self.scenario.project_info
        except: self.project_info = None
        try: self.opex = self.scenario.operating_expenses
        except: self.opex = None
        try: self.capex = self.scenario.capital_expenditure
        except: self.capex = None
        try: self.tax = self.scenario.tax_assumptions
        except: self.tax = None
        try: self.debt = self.scenario.debt_financing
        except: self.debt = None
        try: self.valuation = self.scenario.exit_valuation
        except: self.valuation = None
        try: self.working_capital = getattr(self.scenario, 'working_capital', None)
        except: self.working_capital = None
        try: self.dividend_policy = getattr(self.scenario, 'dividend_policy', None)
        except: self.dividend_policy = None
        try: self.revenue_products = list(self.scenario.revenue_products.all())
        except: self.revenue_products = []
        try: self.dep_schedules = list(self.scenario.depreciation_schedules.all())
        except: self.dep_schedules = []

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
        Generate list of periods based on model timeline
        Returns: ['2025', '2026', '2027', ...]
        """
        try:
            macro = self.macro
            project_info = self.project_info
            
            base_year = macro.base_year
            num_years = macro.number_of_years
            
            return [str(base_year + i) for i in range(num_years)]
            
        except Exception as e:
            logger.error(f"Error generating periods: {str(e)}")
            # Default fallback
            return [str(2025 + i) for i in range(10)]
    
    def _calculate_revenue(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate revenue for all products across all periods
        Returns: {'ProductName': {'2025': 1000000, '2026': 1150000, ...}}
        """
        revenue_schedule = {}
        
        try:
            products = self.revenue_products
            
            for product in products:
                product_revenue = {}
                
                # Get product parameters
                year_1_volume = Decimal(str(product.year_1_sales_volume or '0'))
                year_1_price = Decimal(str(product.unit_price_year_1 or '0'))
                volume_growth = Decimal(str(product.volume_growth_rate or '0'))
                price_escalation = Decimal(str(product.price_escalation_rate or '0'))
                
                for i, period in enumerate(self.periods):
                    # Real Estate specialized revenue logic
                    if product.number_of_units and product.sale_price_per_unit:
                        # Revenue = Units × Price (one-time sale model for now)
                        price_factor = (Decimal('1') + price_escalation / Decimal('100')) ** Decimal(str(i))
                        price = Decimal(str(product.sale_price_per_unit)) * price_factor
                        # Sales absorption - distributes sales over time
                        absorption_months = product.sales_absorption_period_months or 24
                        annual_absorption_factor = min(Decimal('1.0'), Decimal('12') / Decimal(str(absorption_months)))
                        revenue = Decimal(str(product.number_of_units)) * price * annual_absorption_factor
                    else:
                        # Standard Volume × Price model
                        # Volume growth (compounded)
                        volume_factor = (Decimal('1') + volume_growth / Decimal('100')) ** Decimal(str(i))
                        volume = year_1_volume * volume_factor
                        
                        # Price escalation (compounded)
                        price_factor = (Decimal('1') + price_escalation / Decimal('100')) ** Decimal(str(i))
                        price = year_1_price * price_factor
                        
                        # Revenue = Volume × Price
                        revenue = volume * price
                    
                    # Apply ramp-up factor if in ramp-up period
                    if product.revenue_rampup_months and i == 0 and not (product.number_of_units and product.sale_price_per_unit):
                        rampup_factor = min(Decimal('1.0'), Decimal(str(product.revenue_rampup_months)) / Decimal('12'))
                        revenue = revenue * rampup_factor
                    
                    # Apply seasonal adjustment
                    if product.seasonal_adjustment_factor:
                        revenue = revenue * product.seasonal_adjustment_factor
                    
                    product_revenue[period] = revenue.quantize(Decimal('0.01'))
                
                revenue_schedule[product.product_name] = product_revenue
                
        except Exception as e:
            logger.error(f"Error calculating revenue: {str(e)}")
            # Return empty schedule
            revenue_schedule = {'Total Revenue': {p: Decimal('0') for p in self.periods}}
        
        return revenue_schedule
    
    def _calculate_opex(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate operating expenses across all periods
        Returns: {'Staff Costs': {'2025': 500000, ...}, ...}
        """
        opex_schedule = {}
        
        try:
            opex = self.opex
            macro = self.macro
            
            # Staff Costs
            staff_costs = {}
            base_staff_cost = (
                Decimal(opex.total_headcount) * 
                opex.average_annual_salary * 
                (1 + opex.benefits_payroll_tax_pct / 100)
            )
            
            for i, period in enumerate(self.periods):
                # Apply salary escalation
                escalated_cost = base_staff_cost * ((1 + opex.salary_escalation_rate / 100) ** i)
                staff_costs[period] = escalated_cost.quantize(Decimal('0.01'))
            
            opex_schedule['Staff Costs'] = staff_costs
            
            # Utilities
            utilities = {}
            base_utilities = opex.power_electricity_cost_annual + opex.water_gas_utilities_annual
            
            for i, period in enumerate(self.periods):
                escalated = base_utilities * ((1 + opex.utilities_escalation_rate / 100) ** i)
                utilities[period] = escalated.quantize(Decimal('0.01'))
            
            opex_schedule['Utilities'] = utilities
            
            # Other OpEx (Admin, Marketing, Professional Fees, etc.)
            other_opex = {}
            base_other = (
                opex.administrative_expenses_annual +
                opex.rent_facilities_annual +
                opex.technology_software_annual +
                opex.professional_fees_annual
            )
            
            for i, period in enumerate(self.periods):
                # Use general inflation for other expenses
                escalated = base_other * ((1 + macro.local_inflation_rate / 100) ** i)
                other_opex[period] = escalated.quantize(Decimal('0.01'))
            
            opex_schedule['Other Operating Expenses'] = other_opex
            
            # Insurance
            insurance = {}
            for i, period in enumerate(self.periods):
                escalated = opex.insurance_annual * ((1 + macro.local_inflation_rate / 100) ** i)
                insurance[period] = escalated.quantize(Decimal('0.01'))
            
            opex_schedule['Insurance'] = insurance

            # Property Management (Real Estate)
            if opex.property_management_pct:
                prop_mgmt = {}
                # Calculate total revenue for each period
                for period in self.periods:
                    total_rev = Decimal('0')
                    for prod_rev in revenue_schedule.values():
                        total_rev += prod_rev.get(period, Decimal('0'))
                    
                    mgmt_fee = total_rev * (opex.property_management_pct / 100)
                    prop_mgmt[period] = mgmt_fee.quantize(Decimal('0.01'))
                
                opex_schedule['Property Management'] = prop_mgmt
            
            # TAM Costs (Turn Around Maintenance)
            if opex.tam_cost and opex.tam_frequency_years:
                tam_schedule = {}
                for i, period in enumerate(self.periods):
                    if i > 0 and i % opex.tam_frequency_years == 0:
                        tam_schedule[period] = opex.tam_cost.quantize(Decimal('0.01'))
                    else:
                        tam_schedule[period] = Decimal('0')
                opex_schedule['TAM Expenses'] = tam_schedule
            
        except Exception as e:
            logger.error(f"Error calculating opex: {str(e)}")
        
        return opex_schedule
    
    def _calculate_depreciation(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate depreciation for all asset categories
        Returns: {'Buildings': {'2025': 50000, ...}, ...}
        """
        depreciation_schedule = {}
        
        try:
            schedules = self.dep_schedules
            project_info = self.project_info
            
            # Determine when operations start (depreciation begins)
            ops_start_year = project_info.operations_start_date.year
            
            for schedule in schedules:
                if schedule.useful_life_years == 0:
                    # Land is not depreciated
                    depreciation_schedule[schedule.get_asset_category_display()] = {
                        p: Decimal('0') for p in self.periods
                    }
                    continue
                
                category_dep = {}
                
                # Calculate annual depreciation using straight-line method
                depreciable_base = schedule.asset_value * (
                    1 - schedule.residual_value_pct / 100
                )
                annual_depreciation = depreciable_base / Decimal(schedule.useful_life_years)
                
                for period in self.periods:
                    year = int(period)
                    
                    # Only depreciate after operations start
                    if year >= ops_start_year:
                        years_from_start = year - ops_start_year
                        
                        # Check if still within useful life
                        if years_from_start < schedule.useful_life_years:
                            category_dep[period] = annual_depreciation.quantize(Decimal('0.01'))
                        else:
                            category_dep[period] = Decimal('0')
                    else:
                        category_dep[period] = Decimal('0')
                
                depreciation_schedule[schedule.get_asset_category_display()] = category_dep
                
        except Exception as e:
            logger.error(f"Error calculating depreciation: {str(e)}")
        
        return depreciation_schedule
    
    def _calculate_capex(self) -> Dict[str, Decimal]:
        """
        Calculate CAPEX by period
        Returns: {'2025': 50000000, '2026': 30000000, ...}
        """
        capex_schedule = {}
        
        try:
            capex = self.capex
            project_info = self.project_info
            
            # Calculate total initial CAPEX
            total_hard_costs = (
                capex.land_cost +
                capex.construction_building_cost +
                capex.equipment_machinery_cost +
                capex.ffe_cost
            )
            
            # Add real estate specific if present
            if capex.carpark_cost:
                total_hard_costs += capex.carpark_cost
            if capex.amenities_cost:
                total_hard_costs += capex.amenities_cost
            if capex.apartment_construction_cost:
                total_hard_costs += capex.apartment_construction_cost
            if capex.hotel_commercial_cost:
                total_hard_costs += capex.hotel_commercial_cost
            
            # Add soft costs
            contingency = total_hard_costs * capex.contingency_pct / 100
            prof_fees = total_hard_costs * capex.professional_fees_pct / 100
            permits = total_hard_costs * capex.permits_approvals_pct / 100
            vat = total_hard_costs * capex.vat_on_construction_pct / 100
            
            total_capex = total_hard_costs + contingency + prof_fees + permits + vat
            
            # Apply phasing
            construction_start_year = project_info.construction_start_date.year
            
            for period in self.periods:
                year = int(period)
                years_from_construction = year - construction_start_year
                
                if years_from_construction == 0:
                    capex_schedule[period] = (total_capex * capex.year_1_drawdown_pct / 100).quantize(Decimal('0.01'))
                elif years_from_construction == 1:
                    capex_schedule[period] = (total_capex * capex.year_2_drawdown_pct / 100).quantize(Decimal('0.01'))
                elif years_from_construction == 2:
                    capex_schedule[period] = (total_capex * capex.year_3_drawdown_pct / 100).quantize(Decimal('0.01'))
                else:
                    # Replacement CAPEX after construction
                    if year > construction_start_year + 3:
                        # Calculate as % of revenue
                        # This requires revenue data - simplified for now
                        capex_schedule[period] = Decimal('0')  # Placeholder
                    else:
                        capex_schedule[period] = Decimal('0')
                        
        except Exception as e:
            logger.error(f"Error calculating capex: {str(e)}")
            capex_schedule = {p: Decimal('0') for p in self.periods}
        
        return capex_schedule
    
    def _calculate_debt(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate debt schedule with principal, interest, payments
        Returns: {'Principal': {...}, 'Interest': {...}, 'Payment': {...}}
        """
        debt_schedule = {
            'Opening Balance': {},
            'Drawdowns': {},
            'Principal Repayment': {},
            'Interest Expense': {},
            'Closing Balance': {},
        }
        
        try:
            debt = self.debt
            capex = self.capex
            project_info = self.project_info
            
            # Calculate total debt amount
            # Get total project cost from CAPEX
            total_hard_costs = (
                capex.land_cost + capex.construction_building_cost +
                capex.equipment_machinery_cost + capex.ffe_cost
            )
            total_capex = total_hard_costs * (1 + (capex.contingency_pct + capex.professional_fees_pct + 
                                                     capex.permits_approvals_pct + capex.vat_on_construction_pct) / 100)
            
            total_debt = total_capex * debt.debt_percentage / 100
            
            # Interest rate
            all_in_rate = (debt.base_rate_value + debt.interest_margin_spread) / 100
            
            # Construction period
            construction_start_year = project_info.construction_start_date.year
            ops_start_year = project_info.operations_start_date.year
            grace_period_years = debt.grace_period_months / 12
            repayment_start_year = ops_start_year + int(grace_period_years)
            
            # Calculate debt schedule
            closing_balance = Decimal('0')
            
            for i, period in enumerate(self.periods):
                year = int(period)
                
                # Opening balance = previous closing
                debt_schedule['Opening Balance'][period] = closing_balance
                
                # Drawdowns during construction
                if year == construction_start_year:
                    drawdown = total_debt * capex.year_1_drawdown_pct / 100
                elif year == construction_start_year + 1:
                    drawdown = total_debt * capex.year_2_drawdown_pct / 100
                elif year == construction_start_year + 2:
                    drawdown = total_debt * capex.year_3_drawdown_pct / 100
                else:
                    drawdown = Decimal('0')
                
                debt_schedule['Drawdowns'][period] = drawdown
                
                # Calculate interest on average balance
                avg_balance = closing_balance + drawdown / 2
                interest = avg_balance * Decimal(str(all_in_rate))
                debt_schedule['Interest Expense'][period] = interest.quantize(Decimal('0.01'))
                
                # Principal repayment (after grace period)
                if year >= repayment_start_year and debt.repayment_type == 'Amortizing':
                    # Calculate amortizing payment
                    periods_remaining = int(debt.loan_tenor_years) - (year - int(repayment_start_year))
                    if periods_remaining > 0:
                        # PMT formula
                        principal_payment = self._calculate_pmt(
                            closing_balance + drawdown,
                            all_in_rate,
                            periods_remaining
                        ) - interest
                        principal_payment = max(Decimal('0'), principal_payment)
                    else:
                        principal_payment = closing_balance + drawdown
                else:
                    principal_payment = Decimal('0')
                
                debt_schedule['Principal Repayment'][period] = principal_payment.quantize(Decimal('0.01'))
                
                # Closing balance
                closing_balance = closing_balance + drawdown - principal_payment
                debt_schedule['Closing Balance'][period] = closing_balance.quantize(Decimal('0.01'))
                
        except Exception as e:
            logger.error(f"Error calculating debt: {str(e)}")
            for key in debt_schedule:
                debt_schedule[key] = {p: Decimal('0') for p in self.periods}
        
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
        """
        Build complete income statement
        """
        is_data: Dict[str, Dict[str, Decimal]] = {}
        
        try:
            tax = self.tax
            
            # Total Revenue
            total_revenue = {}
            for period in self.periods:
                period_revenue = sum(
                    product_rev.get(period, Decimal('0'))
                    for product_rev in revenue_schedule.values()
                )
                total_revenue[period] = period_revenue
            
            is_data['Total Revenue'] = total_revenue
            
            # Total Operating Expenses
            total_opex = {}
            for period in self.periods:
                period_opex = sum(
                    opex_item.get(period, Decimal('0'))
                    for opex_item in opex_schedule.values()
                )
                total_opex[period] = period_opex
            
            is_data['Total Operating Expenses'] = total_opex
            
            # EBITDA
            ebitda = {}
            for period in self.periods:
                ebitda[period] = total_revenue[period] - total_opex[period]
            
            is_data['EBITDA'] = ebitda
            
            # Total Depreciation
            total_depreciation = {}
            for period in self.periods:
                period_dep = sum(
                    dep_item.get(period, Decimal('0'))
                    for dep_item in depreciation_schedule.values()
                )
                total_depreciation[period] = period_dep
            
            is_data['Depreciation'] = total_depreciation
            
            # EBIT
            ebit = {}
            for period in self.periods:
                ebit[period] = ebitda[period] - total_depreciation[period]
            
            is_data['EBIT'] = ebit
            
            # Interest Expense
            is_data['Interest Expense'] = debt_schedule['Interest Expense']
            
            # EBT (Earnings Before Tax)
            ebt = {}
            for period in self.periods:
                ebt[period] = ebit[period] - debt_schedule['Interest Expense'].get(period, Decimal('0'))
            
            is_data['EBT'] = ebt
            
            # Tax Expense
            tax_expense: Dict[str, Decimal] = {}
            for period in self.periods:
                if ebt[period] > 0:
                    tax_expense[period] = (ebt[period] * tax.corporate_income_tax_rate / 100).quantize(Decimal('0.01'))
                else:
                    tax_expense[period] = Decimal('0')
            
            is_data['Tax Expense'] = tax_expense
            
            # Net Income
            net_income: Dict[str, Decimal] = {}
            for period in self.periods:
                net_income[period] = ebt[period] - tax_expense[period]
            
            is_data['Net Income'] = net_income
            
        except Exception as e:
            logger.error(f"Error building income statement: {str(e)}")
        
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
                
                prev_nwc = Decimal('0')
                for period in self.periods:
                    revenue = income_statement['Total Revenue'].get(period, Decimal('0'))
                    opex = income_statement['Total Operating Expenses'].get(period, Decimal('0'))
                    
                    ar = revenue * rec_days / Decimal('365')
                    inv = opex * inv_days / Decimal('365')
                    ap = opex * pay_days / Decimal('365')
                    
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
            
            for period in self.periods:
                # Calculate cash needs BEFORE equity funding and dividends
                cash_needs = (
                    cfo.get(period, Decimal('0')) + 
                    capex_cf.get(period, Decimal('0')) + 
                    debt_schedule['Drawdowns'].get(period, Decimal('0')) + 
                    debt_repayment.get(period, Decimal('0'))
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
                    
                    if available_cash > min_cash_req:
                        dividend = min(potential_dividend, available_cash - min_cash_req)
                
                dividends_paid[period] = -dividend.quantize(Decimal('0.01'))
                cash_needs += dividends_paid[period]  # Cash needs becomes more negative (or stays same)
                
                # If opening cash + cash_needs < 0, we need sponsor equity to plug the gap
                cash_deficit = -(cash_balance + cash_needs)
                
                if cash_deficit > 0:
                    equity_drawdown = cash_deficit
                else:
                    equity_drawdown = Decimal('0')
                    
                equity_drawdowns[period] = equity_drawdown
                
                cff[period] = (
                    debt_schedule['Drawdowns'].get(period, Decimal('0')) +
                    debt_repayment.get(period, Decimal('0')) +
                    equity_drawdown + 
                    dividends_paid[period]
                )
                
                net_cf[period] = cfo.get(period, Decimal('0')) + capex_cf.get(period, Decimal('0')) + cff[period]
                cash_balance += net_cf[period]
                cash_end[period] = cash_balance
                
            cfs_data['Dividends Paid'] = dividends_paid
            cfs_data['Equity Drawdowns'] = equity_drawdowns
            cfs_data['Cash Flow from Financing'] = cff
            cfs_data['Net Cash Flow'] = net_cf
            cfs_data['Cash Balance (End)'] = cash_end
            
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
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Calculate financial ratios and metrics
        """
        ratios = {}
        
        try:
            # Profitability Ratios
            # EBITDA Margin
            ebitda_margin = {}
            for period in self.periods:
                revenue = income_statement['Total Revenue'][period]
                if revenue > 0:
                    ebitda_margin[period] = (
                        income_statement['EBITDA'][period] / revenue * 100
                    ).quantize(Decimal('0.01'))
                else:
                    ebitda_margin[period] = Decimal('0')
            
            ratios['EBITDA Margin (%)'] = ebitda_margin
            
            # Net Margin
            net_margin = {}
            for period in self.periods:
                revenue = income_statement['Total Revenue'][period]
                if revenue > 0:
                    net_margin[period] = (
                        income_statement['Net Income'][period] / revenue * 100
                    ).quantize(Decimal('0.01'))
                else:
                    net_margin[period] = Decimal('0')
            
            ratios['Net Margin (%)'] = net_margin
            
            # ROE (Return on Equity)
            roe = {}
            for period in self.periods:
                equity = balance_sheet['Total Equity'][period]
                if equity > 0:
                    roe[period] = (
                        income_statement['Net Income'][period] / equity * 100
                    ).quantize(Decimal('0.01'))
                else:
                    roe[period] = Decimal('0')
            
            ratios['ROE (%)'] = roe
            
            # ROA (Return on Assets)
            roa = {}
            for period in self.periods:
                assets = balance_sheet['Total Assets'][period]
                if assets > 0:
                    roa[period] = (
                        income_statement['Net Income'][period] / assets * 100
                    ).quantize(Decimal('0.01'))
                else:
                    roa[period] = Decimal('0')
            
            ratios['ROA (%)'] = roa
            
            # Debt Ratios
            # DSCR (Debt Service Coverage Ratio)
            dscr = {}
            for period in self.periods:
                debt_service = (
                    debt_schedule['Principal Repayment'][period] +
                    debt_schedule['Interest Expense'][period]
                )
                if debt_service > 0:
                    # DSCR = (EBITDA - Capex) / Debt Service
                    available_cash = income_statement['EBITDA'][period]
                    dscr[period] = (available_cash / debt_service).quantize(Decimal('0.01'))
                else:
                    dscr[period] = Decimal('0')
            
            ratios['DSCR'] = dscr
            
            # LLCR (Loan Life Coverage Ratio) & PLCR (Project Life Coverage Ratio)
            llcr = {}
            plcr = {}
            try:
                cost_of_debt = float(self.debt.base_rate_value + self.debt.interest_margin_spread) / 100.0
            except Exception:
                cost_of_debt = 0.10  # Fallback

            for i, period in enumerate(self.periods):
                outstanding_debt = float(debt_schedule['Opening Balance'].get(period, 0))
                if outstanding_debt > 0:
                    future_periods = self.periods[i:]
                    
                    # LLCR looks only at periods where the loan is active (balance or repayment exists)
                    loan_periods = [p for p in future_periods if float(debt_schedule['Closing Balance'].get(p, 0)) > 0 or float(debt_schedule['Principal Repayment'].get(p, 0)) > 0]
                    if not loan_periods:
                        loan_periods = [period]
                        
                    npv_cfads_llcr = 0.0
                    for t, p in enumerate(loan_periods):
                        cfads = float(cash_flow_statement.get('Cash Flow from Operations', {}).get(p, 0))
                        npv_cfads_llcr += cfads / ((1 + cost_of_debt) ** t)
                    
                    npv_cfads_plcr = 0.0
                    for t, p in enumerate(future_periods):
                        cfads = float(cash_flow_statement.get('Cash Flow from Operations', {}).get(p, 0))
                        npv_cfads_plcr += cfads / ((1 + cost_of_debt) ** t)
                    
                    llcr[period] = Decimal(str(npv_cfads_llcr / outstanding_debt)).quantize(Decimal('0.01'))
                    plcr[period] = Decimal(str(npv_cfads_plcr / outstanding_debt)).quantize(Decimal('0.01'))
                else:
                    llcr[period] = Decimal('0')
                    plcr[period] = Decimal('0')
            
            ratios['LLCR'] = llcr
            ratios['PLCR'] = plcr
            
            # Debt-to-Equity
            debt_to_equity = {}
            for period in self.periods:
                equity = balance_sheet['Total Equity'][period]
                if equity > 0:
                    debt_to_equity[period] = (
                        debt_schedule['Closing Balance'][period] / equity
                    ).quantize(Decimal('0.01'))
                else:
                    debt_to_equity[period] = Decimal('0')
            
            ratios['Debt-to-Equity'] = debt_to_equity
            
        except Exception as e:
            logger.error(f"Error calculating ratios: {str(e)}")
        
        return ratios
    
    def _calculate_valuation(
        self, income_statement, cash_flow_statement
    ) -> Dict[str, Decimal]:
        """
        Calculate valuation metrics (NPV, IRR, etc.) using Unlevered Free Cash Flow (FCFF)
        """
        valuation = {}
        
        try:
            valuation_params = self.valuation
            tax_rate = float(self.tax.corporate_income_tax_rate / 100) if self.tax else 0.0
            
            # Generate accurate Unlevered Free Cash Flow (FCFF)
            # FCFF = EBIT*(1-T) + D&A - CAPEX - Changes in WC
            fcf_series = []
            for period in self.periods:
                ebit = float(income_statement.get('EBIT', {}).get(period, 0))
                nopat = ebit * (1 - tax_rate)
                
                depreciation = float(income_statement.get('Depreciation', {}).get(period, 0))
                
                # CFI is CAPEX (negative cash stream)
                cfi = float(cash_flow_statement.get('Cash Flow from Investing', {}).get(period, 0))
                
                # Working capital change
                dwc = float(cash_flow_statement.get('Changes in Working Capital', {}).get(period, 0))
                
                fcf = nopat + depreciation + cfi - dwc
                fcf_series.append(fcf)
            
            # NPV Calculation
            discount_rate = float(valuation_params.discount_rate_npv_pct / 100)
            npv = self._calculate_npv(fcf_series, discount_rate)
            valuation['NPV'] = Decimal(str(npv)).quantize(Decimal('0.01'))
            
            # IRR Calculation
            irr = self._calculate_irr(fcf_series)
            if irr:
                valuation['IRR (%)'] = Decimal(str(irr * 100)).quantize(Decimal('0.01'))
            else:
                valuation['IRR (%)'] = Decimal('0')
            
            # Payback Period Calculation
            cumulative_cash = 0.0
            payback_years = 0.0
            payback_found = False
            
            for i, fcf in enumerate(fcf_series):
                prev_cumulative = cumulative_cash
                cumulative_cash += fcf
                
                # Check if it flipped from negative to positive
                if cumulative_cash >= 0 and prev_cumulative < 0 and not payback_found:
                    fraction = abs(prev_cumulative) / fcf if fcf > 0 else 0
                    payback_years = i + fraction
                    payback_found = True
                    
            if payback_found:
                valuation['Payback Period (Years)'] = Decimal(str(payback_years)).quantize(Decimal('0.01'))
            else:
                valuation['Payback Period (Years)'] = Decimal('0')
            
            
            # Terminal Value (using Exit Multiple)
            final_year_ebitda = income_statement['EBITDA'][self.periods[-1]]
            terminal_value = final_year_ebitda * valuation_params.exit_multiple_ev_ebitda
            valuation['Terminal Value'] = terminal_value.quantize(Decimal('0.01'))
            
        except Exception as e:
            logger.error(f"Error calculating valuation: {str(e)}")
        
        return valuation
    
    def _calculate_npv(self, cash_flows: List[float], discount_rate: float) -> float:
        """Calculate Net Present Value"""
        npv = sum(cf / ((1 + discount_rate) ** i) for i, cf in enumerate(cash_flows))
        return npv
    
    def _calculate_irr(self, cash_flows: List[float]) -> float:
        """
        Calculate Internal Rate of Return using Newton-Raphson iteration.
        np.irr was removed in NumPy 2.0, so we implement it manually.
        """
        try:
            if not cash_flows or len(cash_flows) < 2:
                return 0.0

            # Newton-Raphson iteration to find IRR
            rate = 0.1  # Initial guess: 10%
            for _ in range(1000):
                npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
                # Derivative of NPV with respect to rate
                dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cash_flows))
                if dnpv == 0:
                    break
                new_rate = rate - npv / dnpv
                if abs(new_rate - rate) < 1e-7:
                    return float(new_rate)
                rate = new_rate

            return float(rate)
        except Exception:
            return 0.0
    
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
        if not 'Dividends Paid' in div_schedule and 'Cash Flow from Financing' in cash_flow_statement:
            div_schedule['Dividends Paid'] = cash_flow_statement.get('Cash Flow from Financing', {}) # Fallback approximation
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

            ar_schedule = {}
            ap_schedule = {}
            inv_schedule = {}
            nwc_schedule = {}

            for period in self.periods:
                revenue = income_statement.get('Total Revenue', {}).get(period, Decimal('0'))
                opex = income_statement.get('Total Operating Expenses', {}).get(period, Decimal('0'))

                ar = (revenue * rec_days / Decimal('365')).quantize(Decimal('0.01'))
                ap = (opex * pay_days / Decimal('365')).quantize(Decimal('0.01'))
                inv = (opex * inv_days / Decimal('365')).quantize(Decimal('0.01'))

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

        # ── Reserve Accounts / DSRA (saved under 'dividend') ──
        try:
            dsra_target = {}
            dsra_balance = {}
            dsra_deposit = {}
            dsra_release = {}

            # DSRA target = 6 months of upcoming debt service (principal + interest)
            months_cover = 6
            for i, period in enumerate(self.periods):
                principal = debt_schedule.get('Principal Repayment', {}).get(period, Decimal('0'))
                interest = debt_schedule.get('Interest Expense', {}).get(period, Decimal('0'))
                annual_ds = principal + interest
                target = (annual_ds * Decimal(str(months_cover)) / Decimal('12')).quantize(Decimal('0.01'))
                dsra_target[period] = target

            prev_balance = Decimal('0')
            for period in self.periods:
                target = dsra_target[period]
                if target > prev_balance:
                    deposit = (target - prev_balance).quantize(Decimal('0.01'))
                    release = Decimal('0')
                else:
                    deposit = Decimal('0')
                    release = (prev_balance - target).quantize(Decimal('0.01'))

                dsra_deposit[period] = deposit
                dsra_release[period] = release
                dsra_balance[period] = target
                prev_balance = target

            for label, vals in [
                ('DSRA Target (6-mo DS)', dsra_target),
                ('DSRA Deposit', dsra_deposit),
                ('DSRA Release', dsra_release),
                ('DSRA Closing Balance', dsra_balance),
            ]:
                CalculatedStatement.objects.create(
                    scenario=self.scenario,
                    statement_type='dividend',
                    line_item=label,
                    values_by_period=self._prepare_for_json(vals)
                )
        except Exception as e:
            logger.error(f"Error calculating DSRA: {str(e)}")

        # ── Exit & Terminal Value Schedule (saved under 'exit') ──
        try:
            exit_schedule = {}
            if getattr(self, 'valuation', None):
                exit_year = getattr(self.valuation, 'exit_year', len(self.periods))
                exit_multiple = getattr(self.valuation, 'exit_multiple_ev_ebitda', Decimal('0'))

                exit_ebitda = {}
                enterprise_value = {}
                net_debt_at_exit = {}
                equity_value_at_exit = {}

                for period in self.periods:
                    ebitda = income_statement.get('EBITDA', {}).get(period, Decimal('0'))
                    exit_ebitda[period] = ebitda
                    ev = (ebitda * exit_multiple).quantize(Decimal('0.01'))
                    enterprise_value[period] = ev

                    outstanding_debt = debt_schedule.get('Outstanding Balance', {}).get(period, Decimal('0'))
                    cash = cash_flow_statement.get('Cash Balance (End)', {}).get(period, Decimal('0'))
                    nd = (outstanding_debt - cash).quantize(Decimal('0.01'))
                    net_debt_at_exit[period] = nd
                    equity_value_at_exit[period] = (ev - nd).quantize(Decimal('0.01'))

                for label, vals in [
                    ('EBITDA at Exit', exit_ebitda),
                    (f'Enterprise Value ({exit_multiple}x EBITDA)', enterprise_value),
                    ('Net Debt at Exit', net_debt_at_exit),
                    ('Equity Value at Exit', equity_value_at_exit),
                ]:
                    CalculatedStatement.objects.create(
                        scenario=self.scenario,
                        statement_type='exit',
                        line_item=label,
                        values_by_period=self._prepare_for_json(vals)
                    )
        except Exception as e:
            logger.error(f"Error calculating exit schedule: {str(e)}")