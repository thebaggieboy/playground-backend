class IncomeStatementCalculator:
    def __init__(self, df):
        self.df = df
        
    def calculate(self):
        # ------------------- 1. Revenue & COGS -------------------
        # Example: Simple Year-over-Year Growth
        self.df['Revenue'] = self.df.apply(
            lambda row: row['Historical Revenue'] * (1 + row['Input:RevenueGrowthRate']) if pd.notna(row['Historical Revenue']) else 0,
            axis=1
        ).fillna(method='ffill')
        
        # Example: COGS based on Manufacturing Model complexity
        self.df['COGS'] = (self.df['Revenue'] * self.df['Input:GrossMargin'] * -1).fillna(0)
        self.df['Gross Profit'] = self.df['Revenue'] + self.df['COGS']

        # ------------------- 2. Operating Expenses -------------------
        self.df['S&M'] = (self.df['Revenue'] * self.df['Input:SM_percent_rev'] * -1).fillna(0)
        self.df['Operating Income (EBIT)'] = self.df['Gross Profit'] + self.df['S&M'] + self.df['G&A'] #... and other expenses

        # ------------------- 3. Tax and NI -------------------
        self.df['Interest Expense'] = 0  # Placeholder, calculated later based on Debt from BS
        self.df['PBT'] = self.df['Operating Income (EBIT)'] - self.df['Interest Expense']
        self.df['Tax'] = (self.df['PBT'] * self.df['Input:CorporateTaxRate'] * -1).clip(upper=0).fillna(0)
        
        # FINAL OUTPUT: Net Income flows to Retained Earnings on the BS
        self.df['Net Income'] = self.df['PBT'] + self.df['Tax']
        return self.df