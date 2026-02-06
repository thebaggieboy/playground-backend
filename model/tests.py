# tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import FinancialModel, Scenario
from .calculation_engine import CalculationEngine

User = get_user_model()

class CalculationEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
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