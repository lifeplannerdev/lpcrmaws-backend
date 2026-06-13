import pandas as pd

file_path = r'b:\lp alternative\details.xlsx'

print("Reading details.xlsx...")
try:
    xls = pd.ExcelFile(file_path)
    print("Sheet Names:", xls.sheet_names)

    for sheet_name in xls.sheet_names:
        print(f"\n--- Sheet: {sheet_name} ---")
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        df_cleaned = df.dropna(how='all')
        print("Columns:", df_cleaned.columns.tolist())
        for i, row in df_cleaned.head(20).iterrows():
            print(f"Row {i}: {row.values}")
except Exception as e:
    print("Error:", e)
