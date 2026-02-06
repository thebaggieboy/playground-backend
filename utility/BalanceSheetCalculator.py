class BalanceSheetCalculator:
    def __init__(self, df):
        self.df = df
        
    def calculate(self):
        # ------------------- 1. Working Capital Items -------------------
        # A/R: Change in A/R = (Current Period Sales / 365 * DSO) - Prior Period A/R
        self.df['Accounts Receivable'] = (
            self.df['Revenue'].shift(0) / Decimal(365) * self.df['Input:DSO']
        ).fillna(0).cumsum() 
        
        # Inventory (Crucial for Manufacturing): Uses Input:DaysInventoryHeld
        # self.df['Inventory'] = ... 

        # ------------------- 2. Non-Current Assets & Liabilities -------------------
        # PP&E (Cumulative calculation based on CAPEX Input and Depreciation from IS)
        self.df['PP&E, Net'] = self.df['Historical PP&E'].fillna(0).cumsum() + self.df['Input:CAPEX'] - self.df['IS:Depreciation']
        
        # Debt (Assumes an opening balance + inputs)
        self.df['Long-Term Debt'] = self.df['Historical Debt'].fillna(0).cumsum() + self.df['Input:NewDebt'] - self.df['Input:Repayments']

        # ------------------- 3. Equity & Retained Earnings -------------------
        # Retained Earnings: Cumulative Sum
        self.df['Retained Earnings'] = (
            self.df['Historical Retained Earnings'].fillna(0) + self.df['Net Income']
        ).cumsum() 
        
        self.df['Total Assets'] = self.df['Accounts Receivable'] + self.df['PP&E, Net'] #... + all other assets
        self.df['Total Liabilities & Equity'] = self.df['Long-Term Debt'] + self.df['Retained Earnings'] #... + all other L&E
        
        # NOTE: Cash is still missing. It's calculated by the CFS.
        return self.df