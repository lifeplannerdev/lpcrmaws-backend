import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/models.py"

with open(file_path, "a", encoding="utf-8") as f:
    f.write("\n\n")
    f.write("class FeePolicy(models.Model):\n")
    f.write("    company = models.CharField(max_length=10, unique=True, default='LP')\n")
    f.write("    block_without_fee_account = models.BooleanField(default=False)\n")
    f.write("    pending_if_overdue = models.BooleanField(default=False)\n")
    f.write("\n")
    f.write("    class Meta:\n")
    f.write("        verbose_name_plural = 'Fee Policies'\n")
    f.write("\n")
    f.write("    def __str__(self):\n")
    f.write("        return f\"{self.company} Fee Policy\"\n")

print("Appended FeePolicy to fees/models.py")
