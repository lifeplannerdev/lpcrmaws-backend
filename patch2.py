import re

file_path = "b:/lp alternative/lpcrmbackend-main/fees/serializers.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the create method start
old_create = """    def create(self, validated_data):
        request = self.context['request']
        student = validated_data['student']"""

new_create = """    def create(self, validated_data):
        first_installment_date = validated_data.pop('first_installment_date', None)
        request = self.context['request']
        student = validated_data['student']"""

content = content.replace(old_create, new_create)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched create method")
