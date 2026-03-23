import openpyxl

def scan_sheet(file_path, sheet_name):
    print(f"\n--- Scanning {sheet_name} ---")
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        sheet = wb[sheet_name]
        
        for row in range(1, 100):
            row_data = []
            for col in range(1, 10):
                cell = sheet.cell(row=row, column=col)
                val = cell.value
                if val:
                    row_data.append(f"{cell.coordinate}: {str(val)[:30]}")
            if row_data:
                print(" | ".join(row_data))
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    path = r'C:\Users\newsh\OneDrive\Documents\Jobs\PLYGROUND\models\PLYGROUND SAMPLE MODEL -Manufacturing Model.xlsm'
    scan_sheet(path, 'Assumption ')
    scan_sheet(path, 'Input ')
