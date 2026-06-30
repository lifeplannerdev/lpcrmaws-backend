import re

file_path = "b:/lp alternative/lpcrmbackend-main/fees/serializers.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update fields list in Meta and add first_installment_date
content = content.replace(
    "'plan_snapshot', 'source_label'\n    ]",
    "'plan_snapshot', 'source_label', 'first_installment_date'\n    ]\n\n    first_installment_date = serializers.DateField(required=False, allow_null=True, write_only=True)"
)

# 2. Update _generate_installments signature
content = content.replace(
    "def _generate_installments(self, account, template):",
    "def _generate_installments(self, account, template, first_installment_date=None):"
)

# 3. Update _generate_installments logic
old_logic = """            if count > 0 and amount > 0:
                for i in range(count):
                    month_offset = i
                    month = start_date.month - 1 + month_offset
                    year = start_date.year + month // 12
                    month = month % 12 + 1
                    
                    days_in_month = monthrange(year, month)[1]
                    day = min(due_day, days_in_month)
                    
                    due_date = datetime.date(year, month, day)"""

new_logic = """            if count > 0 and amount > 0:
                base_date = first_installment_date or start_date
                installment_due_day = base_date.day if first_installment_date else due_day
                
                # If no first_installment_date provided, start next month
                base_month_offset = 0 if first_installment_date else 1

                for i in range(count):
                    month_offset = base_month_offset + i
                    month = base_date.month - 1 + month_offset
                    year = base_date.year + month // 12
                    month = month % 12 + 1
                    
                    days_in_month = monthrange(year, month)[1]
                    day = min(installment_due_day, days_in_month)
                    
                    due_date = datetime.date(year, month, day)"""

content = content.replace(old_logic, new_logic)

# 4. Update create method signature and generate_installments call
old_create = """    def create(self, validated_data):
        template = validated_data.get('template')
        student = validated_data.get('student')
        request = self.context.get('request')"""

new_create = """    def create(self, validated_data):
        first_installment_date = validated_data.pop('first_installment_date', None)
        template = validated_data.get('template')
        student = validated_data.get('student')
        request = self.context.get('request')"""

content = content.replace(old_create, new_create)

old_call = """            if template:
                self._generate_installments(account, template)"""

new_call = """            if template:
                self._generate_installments(account, template, first_installment_date)"""

content = content.replace(old_call, new_call)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated serializers.py")
