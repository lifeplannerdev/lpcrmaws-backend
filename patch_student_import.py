import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("from students.models import Student", "from trainers.models import Student")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Backend views patched for correct Student import!")
