import pandas as pd
from decimal import Decimal
from django.db.models import F
from .models import Scenario, Assumption, HistoricalData, FinancialStatementLineItem

# The primary time index for the model run
FORECAST_PERIODS = ['2025-Q1', '2025-Q2', '2025-Q3', '2025-Q4', '2026-Q1', '2026-Q2', ...] # Define your full period list

class DataLoader:
    """Loads all input data for a scenario into a unified Pandas DataFrame."""
    
    def __init__(self, scenario_id):
        self.scenario = Scenario.objects.get(id=scenario_id)
        self.model = self.scenario.model
        self.df = self._initialize_dataframe()

    def _initialize_dataframe(self):
        # 1. Load all relevant periods (Historical + Forecast)
        historical_periods = HistoricalData.objects.filter(model=self.model).values_list('period', flat=True).distinct()
        all_periods = sorted(list(set(historical_periods) | set(FORECAST_PERIODS)))
        df = pd.DataFrame(index=all_periods)
        df.index.name = 'Period'
        return df

    def load_historical_data(self):
        """Pulls historical data and maps it to the DataFrame."""
        hist_data = HistoricalData.objects.filter(model=self.model)
        for item in hist_data:
            df.loc[item.period, item.line_item] = item.value

    def load_assumptions(self):
        """Pulls user assumptions and maps them to the DataFrame."""
        assumptions = Assumption.objects.filter(scenario=self.scenario)
        for item in assumptions:
            # Prefix assumption variables to prevent naming clashes with calculated variables
            self.df.loc[item.period, f'Input:{item.variable_name}'] = item.value

# ... (Additional utility methods for saving results, logging, etc.) ...