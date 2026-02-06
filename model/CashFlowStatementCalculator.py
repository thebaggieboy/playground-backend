class CashFlowStatementCalculator:
    def __init__(self, df):
        self.df = df

    def calculate(self):
        # ------------------- 1. Cash from Operations (CFO) -------------------
        self.df['CFO:Start'] = self.df['Net Income'] + self.df['IS:Depreciation'] # Net Income + Non-Cash Items
        
        # Adjust for Changes in Working Capital (Change in BS item = change in cash)
        self.df['CFO:d_AR'] = (self.df['Accounts Receivable'].shift(1) - self.df['Accounts Receivable']).fillna(0)
        # self.df['CFO:d_Inventory'] = ...
        
        self.df['Cash from Operations'] = self.df['CFO:Start'] + self.df['CFO:d_AR'] #... + all other changes

        # ------------------- 2. Cash from Investing (CFI) -------------------
        self.df['Cash from Investing'] = self.df['Input:CAPEX'] * -1 # CAPEX is an outflow

        # ------------------- 3. Cash from Financing (CFF) -------------------
        self.df['Cash from Financing'] = self.df['Input:NewDebt'] + self.df['Input:EquityInjection'] - self.df['Input:Repayments']
        
        # ------------------- 4. Final Cash Balance -------------------
        self.df['Change in Cash'] = self.df['Cash from Operations'] + self.df['Cash from Investing'] + self.df['Cash from Financing']
        
        # FINAL OUTPUT: Closing Cash for the Balance Sheet
        self.df['Cash'] = self.df['Historical Cash'].fillna(0).cumsum() + self.df['Change in Cash'].cumsum()
        
        # CRITICAL CHECK: Ensure the Balance Sheet now balances (Total Assets = Total L&E)
        # Add Cash to Assets, then check balance.
        self.df['Total Assets'] = self.df['Cash'] + self.df['Total Assets'] # The Cash value closes the loop
        
        # The relationship between the three statements is fundamental. 
        # 
        
        self.df['BS Check'] = self.df['Total Assets'] - self.df['Total Liabilities & Equity']
        if not all(self.df['BS Check'].apply(lambda x: abs(x) < 0.01)): # Check for tiny rounding errors
             raise ValueError("Balance Sheet Check Failed! The model does not balance.")

        return self.df