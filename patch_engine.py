import os
import re

file_path = r"model/calculation_engine.py"

with open(file_path, "r") as f:
    content = f.read()

# Replace calculate_scenario definition
target_calc_def = """    def calculate_scenario(self, scenario: Scenario, user=None):
        \"\"\"
        Main entry point for calculating a complete scenario
        Returns: dict with calculation results
        \"\"\"
        self.scenario = scenario
        
        # Create calculation log
        log = CalculationLog.objects.create(
            scenario=scenario,
            triggered_by=user,
            status='running'
        )"""

new_calc_def = """    def calculate_scenario(self, scenario: Scenario, user=None, save_results=True, overrides=None):
        \"\"\"
        Main entry point for calculating a complete scenario
        Returns: dict with calculation results
        \"\"\"
        self.scenario = scenario
        self._prepare_scenario(overrides)
        
        # Create calculation log
        log = None
        if save_results:
            log = CalculationLog.objects.create(
                scenario=scenario,
                triggered_by=user,
                status='running'
            )"""
content = content.replace(target_calc_def, new_calc_def)

# Replace step 12 mapping
target_step_12 = """            # Step 12: Save all results
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
            
            return self._prepare_for_json({
                'status': 'success',
                'periods_calculated': len(self.periods),
                'duration_seconds': duration
            })"""

new_step_12 = """            # Step 12: Save all results
            if save_results:
                self._save_results(
                    income_statement, balance_sheet, cash_flow_statement,
                    ratios, valuation, debt_schedule
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
            })"""
content = content.replace(target_step_12, new_step_12)

# Replace exception handling log.save()
target_except = """            # Update log
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            log.status = 'failed'
            log.completed_at = end_time
            log.duration_seconds = Decimal(str(duration))
            log.error_message = str(e)
            import traceback
            log.error_traceback = traceback.format_exc()
            log.save()"""

new_except = """            # Update log
            if log:
                end_time = timezone.now()
                duration = (end_time - start_time).total_seconds()
                log.status = 'failed'
                log.completed_at = end_time
                log.duration_seconds = Decimal(str(duration))
                log.error_message = str(e)
                import traceback
                log.error_traceback = traceback.format_exc()
                log.save()"""
content = content.replace(target_except, new_except)

# Insert _prepare_scenario
prepare_func = """
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
"""
content = content.replace("def _prepare_for_json(self, data):", prepare_func + "\n    def _prepare_for_json(self, data):")

# Replacements for relations
content = content.replace("macro = self.scenario.macro_assumptions", "macro = self.macro")
content = content.replace("project_info = self.scenario.project_info", "project_info = self.project_info")
content = content.replace("products = self.scenario.revenue_products.all()", "products = self.revenue_products")
content = content.replace("opex = self.scenario.operating_expenses", "opex = self.opex")
content = content.replace("schedules = self.scenario.depreciation_schedules.all()", "schedules = self.dep_schedules")
content = content.replace("capex = self.scenario.capital_expenditure", "capex = self.capex")
content = content.replace("tax = self.scenario.tax_assumptions", "tax = self.tax")
content = content.replace("debt = self.scenario.debt_financing", "debt = self.debt")
content = content.replace("valuation_params = self.scenario.exit_valuation", "valuation_params = self.valuation")

# Save
with open(file_path, "w") as f:
    f.write(content)

print("Patching successful.")
