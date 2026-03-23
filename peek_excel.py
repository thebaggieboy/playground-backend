import openpyxl
import sys

def peek_excel(file_path):
    print(f"Loading {file_path}")
    try:
        # data_only=False means formulas are preserved.
        wb = openpyxl.load_workbook(file_path, data_only=False, read_only=True)
        print("Sheets in workbook:")
        for sheet in wb.sheetnames:
            print(f"- {sheet}")
            
    except Exception as e:
        print(f"Error loading: {e}")

if __name__ == "__main__":
    peek_excel(r'C:\Users\newsh\OneDrive\Documents\Jobs\PLYGROUND\models\PLYGROUND SAMPLE MODEL -Manufacturing Model.xlsm')
