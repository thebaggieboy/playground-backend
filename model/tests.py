# tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from types import SimpleNamespace
from rest_framework.exceptions import ValidationError
from .models import FinancialModel, Scenario
from .calculation_engine import CalculationEngine, InvalidIndustryLibraryInputError
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
        result = engine.calculate_scenario(self.scenario, user=self.user)
        self.assertEqual(result['status'], 'success')

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
            )
        ]
        with self.assertRaises(InvalidIndustryLibraryInputError):
            engine._calculate_revenue()