import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"

with open(file_path, "a", encoding="utf-8") as f:
    f.write("\n\n")
    f.write("from .models import FeePolicy\n")
    f.write("from .serializers import FeePolicySerializer\n")
    f.write("\n")
    f.write("class FeePolicyAPIView(APIView):\n")
    f.write("    permission_classes = [IsAuthenticated, CanManageFees]\n")
    f.write("\n")
    f.write("    def get(self, request):\n")
    f.write("        company = request.user.company or 'LP'\n")
    f.write("        policy, created = FeePolicy.objects.get_or_create(company=company)\n")
    f.write("        return Response(FeePolicySerializer(policy).data)\n")
    f.write("\n")
    f.write("    def patch(self, request):\n")
    f.write("        company = request.user.company or 'LP'\n")
    f.write("        policy, created = FeePolicy.objects.get_or_create(company=company)\n")
    f.write("        serializer = FeePolicySerializer(policy, data=request.data, partial=True)\n")
    f.write("        serializer.is_valid(raise_exception=True)\n")
    f.write("        serializer.save()\n")
    f.write("        return Response(serializer.data)\n")

print("Appended FeePolicyAPIView to fees/views.py")
