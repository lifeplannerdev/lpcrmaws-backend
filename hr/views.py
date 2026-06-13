from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from django.db.models import Count, Q
from .models import Penalty, AttendanceDocument, Candidate, Asset, Location, AssetCategory
from .serializers import (
    PenaltySerializer, 
    AttendanceDocumentSerializer, 
    StaffSerializer,
    CandidateSerializer,
    AssetSerializer,
    LocationSerializer,
    AssetCategorySerializer
)
from .permissions import (
    HasPenaltyPermission,
    HasStaffPermission,
    HasAttendancePermission,
    HasCandidatePermission,
    HasAssetPermission
)

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [HasAssetPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        company = self.request.query_params.get('company')
        if company:
            qs = qs.filter(company=company)
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        qs = self.get_queryset()
        summary_data = []
        for loc in qs:
            assets = loc.assets.all()
            category_counts = {}
            for asset in assets:
                cat_name = asset.category.name if asset.category else 'Uncategorized'
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
            
            summary_data.append({
                "id": loc.id,
                "name": loc.name,
                "company": loc.company,
                "asset_counts": category_counts,
                "total_assets": assets.count()
            })
        return Response(summary_data)

class AssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all()
    serializer_class = AssetCategorySerializer
    permission_classes = [HasAssetPermission]

User = get_user_model()


# PENALTY APIs 

class PenaltyListCreateAPI(APIView):
    permission_classes = [HasPenaltyPermission]
    
    def get(self, request):
        penalties = Penalty.objects.all()
        
        # Filter by month
        month = request.GET.get("month")
        if month:
            penalties = penalties.filter(month=month)
        
        # Filter by user
        user_id = request.GET.get("user")
        if user_id:
            penalties = penalties.filter(user_id=user_id)
            
        # Filter by company
        company = request.GET.get("company")
        if company:
            penalties = penalties.filter(user__company=company)
        
        # Serialize with user details
        serializer = PenaltySerializer(
            penalties.order_by("-date"), 
            many=True
        )
        
        return Response({
            "count": penalties.count(),
            "results": serializer.data
        })
    
    def post(self, request):
        serializer = PenaltySerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data.get('user')
            serializer.save(company=user.company if user else 'LP')
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PenaltyDetailAPI(APIView):
    permission_classes = [HasPenaltyPermission]
    
    def get(self, request, pk):
        try:
            penalty = Penalty.objects.get(pk=pk)
        except Penalty.DoesNotExist:
            return Response(
                {"error": "Penalty not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PenaltySerializer(penalty)
        return Response(serializer.data)
    
    def put(self, request, pk):
        try:
            penalty = Penalty.objects.get(pk=pk)
        except Penalty.DoesNotExist:
            return Response(
                {"error": "Penalty not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PenaltySerializer(penalty, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        try:
            penalty = Penalty.objects.get(pk=pk)
        except Penalty.DoesNotExist:
            return Response(
                {"error": "Penalty not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        penalty.delete()
        return Response(
            {"message": "Penalty deleted successfully"}, 
            status=status.HTTP_204_NO_CONTENT
        )


# ATTENDANCE APIs 
class AttendanceDocumentAPI(APIView):

    permission_classes = [HasAttendancePermission]
    
    def get(self, request):
        docs = AttendanceDocument.objects.all()
        month = request.GET.get("month")
        if month:
            docs = docs.filter(month=month)
            
        company = request.GET.get("company")
        if company:
            docs = docs.filter(company=company)
        
        serializer = AttendanceDocumentSerializer(docs.order_by("-date"), many=True)
        return Response({
            "count": docs.count(),
            "results": serializer.data
        })
    
    def post(self, request):
        serializer = AttendanceDocumentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class AttendanceDocumentDeleteAPI(APIView):
    permission_classes = [HasAttendancePermission] 
    def get(self, request, pk):
        try:
            doc = AttendanceDocument.objects.get(pk=pk)
        except AttendanceDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = AttendanceDocumentSerializer(doc)
        return Response(serializer.data)
    
    def delete(self, request, pk):
        try:
            doc = AttendanceDocument.objects.get(pk=pk)
        except AttendanceDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        doc.delete()
        return Response(
            {"message": "Document deleted successfully"}, 
            status=status.HTTP_204_NO_CONTENT
        )


# STAFF/EMPLOYEE APIs
class StaffListAPI(APIView):
    permission_classes = [HasStaffPermission]
    
    def get(self, request):
        users = User.objects.all()
        
        # Filter by role
        role = request.GET.get("role")
        if role:
            users = users.filter(role=role)
        
        # Filter by active status
        is_active = request.GET.get("is_active")
        if is_active is not None:
            users = users.filter(is_active=is_active.lower() == "true")
        
        # Search
        search = request.GET.get("search")
        if search:
            users = users.filter(
                first_name__icontains=search
            ) | users.filter(
                last_name__icontains=search
            ) | users.filter(
                username__icontains=search
            ) | users.filter(
                email__icontains=search
            )
        
        serializer = StaffSerializer(users.order_by("first_name"), many=True)
        return Response({
            "count": users.count(),
            "results": serializer.data
        })


class StaffDetailAPI(APIView):
    permission_classes = [HasStaffPermission]
    
    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"error": "Employee not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = StaffSerializer(user)
        return Response(serializer.data)


class CandidateListCreateAPI(APIView):
    permission_classes = [HasCandidatePermission]

    def get(self, request):
        status_filter = request.GET.get("status")
        candidates = Candidate.objects.all()

        if status_filter:
            candidates = candidates.filter(status=status_filter)

        company = request.GET.get("company")
        if company:
            candidates = candidates.filter(company=company)

        serializer = CandidateSerializer(candidates, many=True)
        return Response({
            "count": candidates.count(),
            "results": serializer.data
        })

    def post(self, request):
        serializer = CandidateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class CandidateDetailAPI(APIView):
    permission_classes = [HasCandidatePermission]

    def get(self, request, pk):
        try:
            candidate = Candidate.objects.get(pk=pk)
        except Candidate.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        return Response(CandidateSerializer(candidate).data)

    def put(self, request, pk):
        candidate = Candidate.objects.get(pk=pk)
        serializer = CandidateSerializer(candidate, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        candidate = Candidate.objects.get(pk=pk)
        candidate.delete()
        return Response(status=204)


# ASSET APIs
class AssetListCreateAPI(APIView):
    permission_classes = [HasAssetPermission]

    def get(self, request):
        assets = Asset.objects.all()

        company = request.GET.get("company")
        if company:
            assets = assets.filter(company=company)
            
        status_filter = request.GET.get("status")
        if status_filter:
            assets = assets.filter(status=status_filter)
            
        assigned_to = request.GET.get("assigned_to")
        if assigned_to:
            assets = assets.filter(assigned_to_id=assigned_to)

        location_id = request.GET.get("location_id")
        if location_id:
            assets = assets.filter(assigned_location_id=location_id)

        category_id = request.GET.get("category_id")
        if category_id:
            assets = assets.filter(category_id=category_id)

        serializer = AssetSerializer(assets, many=True)
        return Response({
            "count": assets.count(),
            "results": serializer.data
        })

    def post(self, request):
        serializer = AssetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AssetDetailAPI(APIView):
    permission_classes = [HasAssetPermission]

    def get(self, request, pk):
        try:
            asset = Asset.objects.get(pk=pk)
        except Asset.DoesNotExist:
            return Response({"error": "Asset not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    def put(self, request, pk):
        try:
            asset = Asset.objects.get(pk=pk)
        except Asset.DoesNotExist:
            return Response({"error": "Asset not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetSerializer(asset, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            asset = Asset.objects.get(pk=pk)
        except Asset.DoesNotExist:
            return Response({"error": "Asset not found"}, status=status.HTTP_404_NOT_FOUND)

        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

