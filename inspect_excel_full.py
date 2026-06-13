import pandas as pd

file_path = r'b:\lp alternative\updated assets list kochi.xlsx'

print("Reading Excel file...")
df = pd.read_excel(file_path, sheet_name='Sheet1')

# The "PHONE DETAILS" might be further down in the file, after some blank rows.
# Let's print all rows and columns to see where it is.
# We will drop rows that are completely NaN.

df_cleaned = df.dropna(how='all')

# Print out the first column to see the sections
for i, row in df_cleaned.iterrows():
    print(f"Row {i}: {row.values}")
