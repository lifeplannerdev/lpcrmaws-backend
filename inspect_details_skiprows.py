import pandas as pd

file_path = r'b:\lp alternative\details.xlsx'
df = pd.read_excel(file_path, sheet_name='Sheet1', skiprows=1)
print(df.head(15))
