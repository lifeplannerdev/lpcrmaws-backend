import pandas as pd

file_path = r'b:\lp alternative\updated assets list kochi.xlsx'

print("Reading Excel file...")
xls = pd.ExcelFile(file_path)
print("Sheet Names:", xls.sheet_names)

for sheet_name in xls.sheet_names:
    print(f"\n--- Sheet: {sheet_name} ---")
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    print("Columns:", df.columns.tolist())
    print(df.head())
