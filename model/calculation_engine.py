"""
Financial Calculation Engine
Implements 3-statement financial model with formulas
Based on standard financial modeling practices
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from django.utils import timezone
import numpy as np
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
        
    def calculate_scenario(self, scenario: Scenario, user=None):
        """
        Main entry point for calculating a complete scenario
        Returns: dict with calculation results
        """
        self.scenario = scenario
        
        # Create calculation log
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
            self._save_results(
                income_statement, balance_sheet, cash_flow_statement,
                ratios, valuation, debt_schedule
            )
            
            # Update log
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            log.status = 'success'
            log.completed_at = end_time
            log.duration_seconds = Decimal(str(duration))
            log.save()
            
            return {
                'status': 'success',
                'periods_calculated': len(self.periods),
                'duration_seconds': duration
            }
            
        except Exception as e:
            logger.error(f"Calculation error for scenario {scenario.id}: {str(e)}")
            
            # Update log
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
    
    def _generate_periods(self) -> List[str]:
        """
        Generate list of periods based on model timeline
        Returns: ['2025', '2026', '2027', ...]
        """
        try:
            macro = self.scenario.macro_assumptions
            project_info = self.scenario.project_info
            
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
            products = self.scenario.revenue_products.all()
            
            for product in products:
                product_revenue = {}
                
                # Get product parameters
                year_1_volume = product.year_1_sales_volume or Decimal('0')
                year_1_price = product.unit_price_year_1 or Decimal('0')
                volume_growth = product.volume_growth_rate or Decimal('0')
                price_escalation = product.price_escalation_rate or Decimal('0')
                
                for i, period in enumerate(self.periods):
                    # Volume growth (compounded)
                    volume = year_1_volume * ((1 + volume_growth / 100) ** i)
                    
                    # Price escalation (compounded)
                    price = year_1_price * ((1 + price_escalation / 100) ** i)
                    
                    # Revenue = Volume × Price
                    revenue = volume * price
                    
                    # Apply ramp-up factor if in ramp-up period
                    if product.revenue_rampup_months and i == 0:
                        rampup_factor = min(Decimal('1.0'), product.revenue_rampup_months / Decimal('12'))
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
            opex = self.scenario.operating_expenses
            macro = self.scenario.macro_assumptions
            
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
            schedules = self.scenario.depreciation_schedules.all()
            project_info = self.scenario.project_info
            
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
            capex = self.scenario.capital_expenditure
            project_info = self.scenario.project_info
            
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
            debt = self.scenario.debt_financing
            capex = self.scenario.capital_expenditure
            project_info = self.scenario.project_info
            
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
                    periods_remaining = debt.loan_tenor_years - (year - repayment_start_year)
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
        is_data = {}
        
        try:
            tax = self.scenario.tax_assumptions
            
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
            tax_expense = {}
            for period in self.periods:
                if ebt[period] > 0:
                    tax_expense[period] = (ebt[period] * tax.corporate_income_tax_rate / 100).quantize(Decimal('0.01'))
                else:
                    tax_expense[period] = Decimal('0')
            
            is_data['Tax Expense'] = tax_expense
            
            # Net Income
            net_income = {}
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
        cfs_data = {}
        
        try:
            # Operating Cash Flow
            # Start with Net Income
            cfs_data['Net Income'] = income_statement['Net Income']
            
            # Add back Depreciation (non-cash)
            cfs_data['Depreciation'] = income_statement['Depreciation']
            
            # Changes in Working Capital (simplified - would need more detail)
            changes_in_wc = {p: Decimal('0') for p in self.periods}
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
            
            # Cash Flow from Financing
            cff = {}
            for period in self.periods:
                cff[period] = (
                    debt_schedule['Drawdowns'][period] +
                    debt_repayment[period] +
                    interest_cf[period]
                )
            
            cfs_data['Cash Flow from Financing'] = cff
            
            # Net Cash Flow
            net_cf = {}
            cash_balance = Decimal('0')
            cash_end = {}
            
            for period in self.periods:
                net_cf[period] = cfo[period] + capex_cf[period] + cff[period]
                cash_balance += net_cf[period]
                cash_end[period] = cash_balance
            
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
            
            # Total Assets
            total_assets = {}
            for period in self.periods:
                total_assets[period] = (
                    bs_data['Cash'][period] +
                    net_fixed_assets[period]
                )
            
            bs_data['Total Assets'] = total_assets
            
            # LIABILITIES
            # Debt
            bs_data['Debt'] = debt_schedule['Closing Balance']
            
            # Total Liabilities
            bs_data['Total Liabilities'] = debt_schedule['Closing Balance']
            
            # EQUITY
            # Retained Earnings (cumulative net income)
            retained_earnings = {}
            cumulative_ni = Decimal('0')
            
            for period in self.periods:
                cumulative_ni += income_statement['Net Income'][period]
                retained_earnings[period] = cumulative_ni
            
            bs_data['Retained Earnings'] = retained_earnings
            
            # Total Equity
            bs_data['Total Equity'] = retained_earnings
            
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
        Calculate valuation metrics (NPV, IRR, etc.)
        """
        valuation = {}
        
        try:
            valuation_params = self.scenario.exit_valuation
            macro = self.scenario.macro_assumptions
            
            # Get Free Cash Flow
            fcf_series = []
            for period in self.periods:
                fcf = cash_flow_statement['Cash Flow from Operations'][period]
                fcf_series.append(float(fcf))
            
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
        """Calculate Internal Rate of Return"""
        try:
            return float(np.irr(cash_flows))
        except:
            return 0.0
    
    def _save_results(
        self, income_statement, balance_sheet, cash_flow_statement,
        ratios, valuation, debt_schedule
    ):
        """
        Save all calculated results to database
        """
        # Clear existing results for this scenario
        CalculatedStatement.objects.filter(scenario=self.scenario).delete()
        
        # Save Income Statement
        for line_item, values in income_statement.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='is',
                line_item=line_item,
                values_by_period=values
            )
        
        # Save Balance Sheet
        for line_item, values in balance_sheet.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='bs',
                line_item=line_item,
                values_by_period=values
            )
        
        # Save Cash Flow Statement
        for line_item, values in cash_flow_statement.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='cfs',
                line_item=line_item,
                values_by_period=values
            )
        
        # Save Ratios
        for line_item, values in ratios.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='ratio',
                line_item=line_item,
                values_by_period=values
            )
        
        # Save Valuation Metrics
        CalculatedStatement.objects.create(
            scenario=self.scenario,
            statement_type='valuation',
            line_item='Valuation Metrics',
            values_by_period=valuation
        )
        
        # Save Debt Schedule
        for line_item, values in debt_schedule.items():
            CalculatedStatement.objects.create(
                scenario=self.scenario,
                statement_type='debt',
                line_item=line_item,
                values_by_period=values
            )