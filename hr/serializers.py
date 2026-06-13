from rest_framework import serializers
from .models import Penalty, AttendanceDocument, Candidate, Asset, Location, AssetCategory, Branch
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "salary", "join_date", "phone", "personal_phone", "office_phone", "location"]

class UserMinimalSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ["id", "username", "name", "first_name", "last_name", "email"]
    
    def get_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        return obj.username

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = '__all__'

class LocationSerializer(serializers.ModelSerializer):
    branch_details = BranchSerializer(source='branch', read_only=True)

    class Meta:
        model = Location
        fields = '__all__'

class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = '__all__'

class AssetSerializer(serializers.ModelSerializer):
    assigned_to_details = UserMinimalSerializer(source='assigned_to', read_only=True)
    assigned_location_details = LocationSerializer(source='assigned_location', read_only=True)
    category_details = AssetCategorySerializer(source='category', read_only=True)
    branch_details = BranchSerializer(source='branch', read_only=True)
    attachment_url = serializers.SerializerMethodField(read_only=True)
    attached_assets = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'category', 'category_details', 'serial_number', 'status', 'company',
            'parent_asset', 'attached_assets', 'primary_phone_number', 'secondary_phone_number',
            'assigned_to', 'assigned_to_details', 'assigned_location', 'assigned_location_details',
            'branch', 'branch_details', 'attachment', 'attachment_url', 'purchase_date', 'notes', 'created_at', 'updated_at'
        ]

    def get_attachment_url(self, obj):
        if obj.attachment:
            return obj.attachment.url
        return None

    def get_attached_assets(self, obj):
        children = obj.attached_assets.all()
        return [
            {
                "id": child.id,
                "name": child.name,
                "category": child.category.name if child.category else None,
                "serial_number": child.serial_number,
                "status": child.status,
                "attachment_url": child.attachment.url if child.attachment else None
            } for child in children
        ]

class PenaltySerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    user_email = serializers.SerializerMethodField(read_only=True)
    user_details = UserMinimalSerializer(source='user', read_only=True)
    
    class Meta:
        model = Penalty
        fields = [
            'id', 
            'user',           
            'user_name',      
            'user_email',    
            'user_details',  
            'act', 
            'amount', 
            'month', 
            'date',
            'company'
        ]
    
    def get_user_name(self, obj):
        if not obj.user:
            return "Unknown"
        if obj.user.first_name and obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        elif obj.user.first_name:
            return obj.user.first_name
        return obj.user.username
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else ""

class AttendanceDocumentSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = AttendanceDocument
        fields = [
            "id",
            "name",
            "date",
            "month",
            "document",
            "document_url",
            "uploaded_at",
            "company"
        ]
    
    def get_document_url(self, obj):
        if obj.document:
            return obj.document.url
        return None

class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "personal_phone",
            "office_phone",
            "team",
            "location",
            "salary",
            "join_date",
            "is_active",
            "company",
            "assets",
        ]
    
    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        return obj.username

    def get_assets(self, obj):
        assets = obj.assigned_assets.filter(parent_asset__isnull=True)
        return AssetSerializer(assets, many=True).data


class CandidateSerializer(serializers.ModelSerializer):
    resume_url = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = "__all__"

    def get_resume_url(self, obj):
        return obj.resume.url if obj.resume else None