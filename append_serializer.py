import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/serializers.py"

with open(file_path, "a", encoding="utf-8") as f:
    f.write("\n\n")
    f.write("from .models import FeePolicy\n")
    f.write("class FeePolicySerializer(serializers.ModelSerializer):\n")
    f.write("    class Meta:\n")
    f.write("        model = FeePolicy\n")
    f.write("        fields = '__all__'\n")

print("Appended FeePolicySerializer to fees/serializers.py")
