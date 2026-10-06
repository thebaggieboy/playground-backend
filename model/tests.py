# tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date
from types import SimpleNamespace
from rest_framework.exceptions import ValidationError
from .models import (
    CapitalExpenditure,
    CalculatedStatement,
    DebtFinancing,
    DepreciationSchedule,
    ExitValuation,
    FinancialModel,
    MacroAssumptions,
    OperatingExpenses,
    ProjectInformation,
    RevenueProduct,
    Scenario,
    TaxAssumptions,
    WorkingCapital,
)
from .calculation_engine import (
    CalculationEngine,
    CalculationInputError,
    InvalidIndustryLibraryInputError,
)
from .serializers import ProjectInformationSerializer

User = get_user_model()

class CalculationEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@test.com', password='password')
        self.model = FinancialModel.objects.create(
            name='Test Model',
            owner=self.user,
            project_type='manufacturing'
        )
        self.scenario = Scenario.objects.create(
            model=self.model,
            name='Base Case',
            scenario_type='base'
        )
    
    def test_calculation_engine(self):
        engine = CalculationEngine()
        with self.assertRaisesRegex(CalculationInputError, "Complete the required model sections"):
            engine.calculate_scenario(self.scenario, user=self.user)

    def test_populated_annual_project_calculates_balanced_statements(self):
        ProjectInformation.objects.create(
            scenario=self.scenario,
            project_name="Test Plant",
            industry_sector="Manufacturing",
            industry_sub_type="General",
            project_type="Greenfield",
            project_commencement_date=date(2025, 1, 1),
            construction_start_date=date(2025, 1, 1),
            construction_duration_months=12,
            construction_end_date=date(2025, 12, 31),
            operations_start_date=date(2026, 1, 1),
            operations_duration_years=20,
            total_capacity=100,
            capacity_unit="tonnes/year",
        )
        MacroAssumptions.objects.create(
            scenario=self.scenario,
            exchange_rate_local_per_usd=1,
            base_year=2025,
            periodicity="Annually",
            number_of_years=5,
            local_inflation_rate=2,
            foreign_inflation_rate=2,
            longterm_target_inflation=2,
            revenue_opex_escalation_usd=2,
            discount_rate_wacc=10,
            risk_free_rate=4,
            benchmark_rate_value=5,
            terminal_growth_rate=2,
            contingency_buffer=5,
        )
        RevenueProduct.objects.create(
            scenario=self.scenario,
            product_name="Finished goods",
            unit_of_measure="tonnes",
            year_1_sales_volume=10000,
            unit_price_year_1=200,
            volume_growth_rate=2,
            price_escalation_rate=2,
        )
        OperatingExpenses.objects.create(
            scenario=self.scenario,
            total_headcount=10,
            average_annual_salary=30000,
            salary_escalation_rate=2,
            benefits_payroll_tax_pct=20,
            power_electricity_cost_annual=50000,
            water_gas_utilities_annual=10000,
            utilities_escalation_rate=2,
            regular_maintenance_pct_revenue=2,
            insurance_annual=10000,
            marketing_sales_pct_revenue=1,
            administrative_expenses_annual=20000,
            rent_facilities_annual=0,
            technology_software_annual=5000,
            professional_fees_annual=5000,
            payables_days_dpo=30,
        )
        CapitalExpenditure.objects.create(
            scenario=self.scenario,
            land_cost=100000,
            construction_building_cost=500000,
            equipment_machinery_cost=300000,
            ffe_cost=100000,
            contingency_pct=5,
            professional_fees_pct=2,
            permits_approvals_pct=1,
            vat_on_construction_pct=0,
            year_1_drawdown_pct=60,
            year_2_drawdown_pct=40,
            year_3_drawdown_pct=0,
            replacement_capex_pct_revenue=1,
        )
        DebtFinancing.objects.create(
            scenario=self.scenario,
            equity_percentage=50,
            debt_percentage=50,
            base_rate_value=5,
            interest_margin_spread=3,
            loan_tenor_years=5,
            upfront_fees_pct=1,
            commitment_fee_pct=0.5,
        )
        TaxAssumptions.objects.create(
            scenario=self.scenario,
            corporate_income_tax_rate=25,
            vat_sales_tax_rate=0,
            wht_dividends=0,
            wht_interest=0,
            initial_allowance_pct=0,
            annual_allowance_pct=0,
        )
        WorkingCapital.objects.create(
            scenario=self.scenario,
            initial_wc_pct_year1_opex=0,
            receivables_days_dso=30,
            inventory_days_dio=15,
            payables_days_dpo=30,
            wc_pct_revenue=0,
            minimum_cash_balance=10000,
        )
        DepreciationSchedule.objects.create(
            scenario=self.scenario,
            asset_category="equipment",
            asset_value=1000000,
            useful_life_years=20,
            residual_value_pct=0,
        )
        ExitValuation.objects.create(
            scenario=self.scenario,
            exit_year=5,
            exit_multiple_ev_ebitda=6,
            terminal_growth_rate_pct=2,
            discount_rate_npv_pct=10,
            target_irr_pct=15,
            target_equity_irr_pct=15,
            target_project_irr_pct=15,
            payback_period_target_years=5,
            minimum_moic=1.5,
            transaction_costs_pct=3,
            valuation_method="Multiple-based",
        )

        result = CalculationEngine().calculate_scenario(
            self.scenario,
            user=self.user,
            save_results=True,
        )
        self.assertEqual(result["status"], "success")
        balance_checks = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="bs",
            line_item="Balance Check (should be 0)",
        ).values_by_period
        self.assertTrue(
            all(abs(value) <= 0.01 for value in balance_checks.values()),
            balance_checks,
        )
        valuation = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="valuation",
        ).values_by_period
        self.assertGreater(valuation["Terminal Value"], 0)
        self.assertIsNotNone(valuation["Equity MOIC (x)"])
        self.assertIsNotNone(valuation["Equity IRR (%)"])
        capitalized_interest = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="debt",
            line_item="Capitalized Interest",
        ).values_by_period
        self.assertGreater(capitalized_interest["2025"], 0)
        upfront_fees = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="debt",
            line_item="Upfront Fees",
        ).values_by_period
        self.assertGreater(upfront_fees["2025"], 0)
        commitment_fees = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="debt",
            line_item="Commitment Fees",
        ).values_by_period
        self.assertGreater(commitment_fees["2025"], 0)
        dsra = CalculatedStatement.objects.get(
            scenario=self.scenario,
            statement_type="dividend",
            line_item="DSRA Closing Balance",
        ).values_by_period
        self.assertGreater(dsra["2029"], 0)

    def test_industry_library_values_round_trip_through_project_information(self):
        library_inputs = {
            "Energy & Power:Solar:project": {
                "p50Yield": "1250",
                "sourceTier": "Tier 4: Market and user data",
                "sourceReference": "Project energy-yield assessment",
            }
        }
        serializer = ProjectInformationSerializer(data={
            "project_name": "Solar Test",
            "project_location": "Test",
            "industry_sector": "Energy & Power",
            "industry_sub_type": "Solar",
            "industry_library_inputs": library_inputs,
            "industry_library_metadata": {"itemCode": "SOL"},
            "industry_library_schema": {
                "project": [{"id": "p50Yield", "type": "number"}]
            },
            "project_type": "Greenfield",
            "project_commencement_date": "2026-01-01",
            "construction_start_date": "2026-02-01",
            "construction_duration_months": 12,
            "construction_end_date": "2027-01-31",
            "operations_start_date": "2027-02-01",
            "operations_duration_years": 20,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        project_info = serializer.save(scenario=self.scenario)
        project_info.refresh_from_db()
        serialized = ProjectInformationSerializer(project_info).data
        self.assertEqual(serialized["industry_library_inputs"], library_inputs)
        self.assertEqual(serialized["industry_library_metadata"]["itemCode"], "SOL")
        self.assertEqual(serialized["industry_library_schema"]["project"][0]["id"], "p50Yield")

    def test_library_numeric_values_require_a_source_record(self):
        serializer = ProjectInformationSerializer()
        serializer = ProjectInformationSerializer(data={
            "industry_sector": "Energy & Power",
            "industry_sub_type": "Solar",
            "industry_library_inputs": {
                "Energy & Power:Solar:project": {"p50Yield": "1250"}
            },
            "industry_library_schema": {
                "project": [{"id": "p50Yield", "type": "number"}]
            },
        })
        with self.assertRaises(ValidationError):
            serializer.validate({})

    def test_solar_p50_yield_supplies_missing_mwh_revenue_volume(self):
        engine = CalculationEngine()
        engine.periods = ["2026"]
        engine.project_info = SimpleNamespace(
            industry_sector="Energy & Power",
            industry_sub_type="Solar",
            operations_start_date=date(2026, 1, 1),
            operations_duration_years=20,
            industry_library_inputs={
                "Energy & Power:Solar:project": {"p50Yield": 1250}
            },
        )
        engine.revenue_products = [
            SimpleNamespace(
                year_1_sales_volume=0,
                unit_price_year_1=50,
                volume_growth_rate=0,
                price_escalation_rate=0,
                unit_of_measure="MWh",
                product_name="Solar generation",
                number_of_units=None,
                sale_price_per_unit=None,
                revenue_rampup_months=None,
                seasonal_adjustment_factor=1,
                sales_absorption_period_months=None,
            )
        ]
        revenue = engine._calculate_revenue()
        self.assertEqual(revenue["Solar generation"]["2026"], 62500)

    def test_core_revenue_volume_remains_authoritative_over_p50(self):
        engine = CalculationEngine()
        engine.periods = ["2026"]
        engine.project_info = SimpleNamespace(
            industry_sector="Energy & Power",
            industry_sub_type="Solar",
            operations_start_date=date(2026, 1, 1),
            operations_duration_years=20,
            industry_library_inputs={
                "Energy & Power:Solar:project": {"p50Yield": 1250}
            },
        )
        engine.revenue_products = [
            SimpleNamespace(
                year_1_sales_volume=1000,
                unit_price_year_1=50,
                volume_growth_rate=0,
                price_escalation_rate=0,
                unit_of_measure="MWh",
                product_name="Solar generation",
                number_of_units=None,
                sale_price_per_unit=None,
                revenue_rampup_months=None,
                seasonal_adjustment_factor=1,
                sales_absorption_period_months=None,
            )
        ]
        revenue = engine._calculate_revenue()
        self.assertEqual(revenue["Solar generation"]["2026"], 50000)

    def test_invalid_solar_p50_value_is_not_converted_to_zero_revenue(self):
        engine = CalculationEngine()
        engine.periods = ["2026"]
        engine.project_info = SimpleNamespace(
            industry_sector="Energy & Power",
            industry_sub_type="Solar",
            operations_start_date=date(2026, 1, 1),
            operations_duration_years=20,
            industry_library_inputs={
                "Energy & Power:Solar:project": {"p50Yield": "not-a-number"}
            },
        )
        engine.revenue_products = [
            SimpleNamespace(
                year_1_sales_volume=0,
                unit_price_year_1=50,
                volume_growth_rate=0,
                price_escalation_rate=0,
                unit_of_measure="MWh",
                product_name="Solar generation",
                number_of_units=None,
                sale_price_per_unit=None,
                revenue_rampup_months=None,
                seasonal_adjustment_factor=1,
                sales_absorption_period_months=None,
            )
        ]
        with self.assertRaises(InvalidIndustryLibraryInputError):
            engine._calculate_revenue()

    def test_irr_uses_bounded_root_for_conventional_cash_flows(self):
        engine = CalculationEngine()
        irr = engine._calculate_irr([-100.0, 60.0, 60.0])
        self.assertIsNotNone(irr)
        self.assertAlmostEqual(irr, 0.130662386, places=6)

    def test_irr_is_not_reported_without_a_unique_root(self):
        engine = CalculationEngine()
        self.assertIsNone(engine._calculate_irr([100.0, 50.0, 25.0]))
        self.assertIsNone(engine._calculate_irr([-100.0, 230.0, -132.0]))

    def test_npv_discounts_first_forecast_period_by_one_year(self):
        engine = CalculationEngine()
        self.assertAlmostEqual(
            engine._calculate_npv([110.0], 0.1),
            100.0,
            places=6,
        )

    def test_property_sales_follow_absorption_period_and_stop_at_inventory_limit(self):
        engine = CalculationEngine()
        engine.periods = ["2026", "2027", "2028"]
        engine.project_info = SimpleNamespace(
            industry_sector="Real Estate",
            industry_sub_type="Residential",
            operations_start_date=date(2026, 1, 1),
            operations_duration_years=20,
            industry_library_inputs={},
        )
        engine.revenue_products = [
            SimpleNamespace(
                year_1_sales_volume=0,
                unit_price_year_1=0,
                volume_growth_rate=0,
                price_escalation_rate=0,
                unit_of_measure="unit",
                product_name="Apartments",
                number_of_units=12,
                sale_price_per_unit=100000,
                revenue_rampup_months=None,
                seasonal_adjustment_factor=1,
                sales_absorption_period_months=24,
            )
        ]

        revenue = engine._calculate_revenue()["Apartments"]
        self.assertEqual(revenue, {"2026": 600000, "2027": 600000, "2028": 0})

    def test_partial_first_operating_year_applies_ramp_up(self):
        engine = CalculationEngine()
        engine.periods = ["2026", "2027"]
        engine.project_info = SimpleNamespace(
            industry_sector="Manufacturing",
            industry_sub_type="General",
            operations_start_date=date(2026, 7, 1),
            operations_duration_years=20,
            industry_library_inputs={},
        )
        engine.revenue_products = [
            SimpleNamespace(
                year_1_sales_volume=1200,
                unit_price_year_1=1,
                volume_growth_rate=0,
                price_escalation_rate=0,
                unit_of_measure="units",
                product_name="Production",
                number_of_units=None,
                sale_price_per_unit=None,
                revenue_rampup_months=6,
                seasonal_adjustment_factor=1,
                sales_absorption_period_months=None,
            )
        ]

        revenue = engine._calculate_revenue()["Production"]
        self.assertGreater(revenue["2026"], 300)
        self.assertLess(revenue["2026"], 310)
        self.assertEqual(revenue["2027"], 1200)