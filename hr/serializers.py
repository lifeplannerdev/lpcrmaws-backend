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
    assigned_staff = serializers.SerializerMethodField(read_only=True)
    assigned_assets = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Location
        fields = '__all__'

    def get_assigned_staff(self, obj):
        users = User.objects.filter(location=obj.name, company=obj.company)
        return UserMinimalSerializer(users, many=True).data
        
    def get_assigned_assets(self, obj):
        assets = obj.assets.all()
        return [
            {
                "id": a.id,
                "name": a.name,
                "category": a.category.name if a.category else None,
                "serial_number": a.serial_number,
                "provider": a.provider,
                "assigned_to": a.assigned_to.id if a.assigned_to else None,
            } for a in assets
        ]

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
    primary_sim_details = serializers.SerializerMethodField(read_only=True)
    secondary_sim_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'category', 'category_details', 'serial_number', 'company',
            'primary_sim', 'primary_sim_details', 'secondary_sim', 'secondary_sim_details', 'provider',
            'assigned_to', 'assigned_to_details', 'assigned_location', 'assigned_location_details',
            'branch', 'branch_details', 'attachment', 'attachment_url', 'purchase_date', 'notes', 'created_at', 'updated_at'
        ]

    def get_attachment_url(self, obj):
        if obj.attachment:
            name = obj.attachment.name
            if name and ('raw/upload/' in name or 'image/upload/' in name):
                return f"https://res.cloudinary.com/dzmvrjvfs/{name}"
            return obj.attachment.url
        return None

    def get_primary_sim_details(self, obj):
        if obj.primary_sim:
            return {
                "id": obj.primary_sim.id,
                "name": obj.primary_sim.name,
                "serial_number": obj.primary_sim.serial_number,
                "provider": obj.primary_sim.provider
            }
        return None

    def get_secondary_sim_details(self, obj):
        if obj.secondary_sim:
            return {
                "id": obj.secondary_sim.id,
                "name": obj.secondary_sim.name,
                "serial_number": obj.secondary_sim.serial_number,
                "provider": obj.secondary_sim.provider
            }
        return None

    def update(self, instance, validated_data):
        primary_sim = validated_data.get('primary_sim', instance.primary_sim)
        secondary_sim = validated_data.get('secondary_sim', instance.secondary_sim)

        # SIM swap logic: if this SIM is already primary or secondary on another asset, detach it
        if primary_sim and primary_sim != instance.primary_sim:
            Asset.objects.filter(primary_sim=primary_sim).exclude(id=instance.id).update(primary_sim=None)
            Asset.objects.filter(secondary_sim=primary_sim).exclude(id=instance.id).update(secondary_sim=None)
            
        if secondary_sim and secondary_sim != instance.secondary_sim:
            Asset.objects.filter(primary_sim=secondary_sim).exclude(id=instance.id).update(primary_sim=None)
            Asset.objects.filter(secondary_sim=secondary_sim).exclude(id=instance.id).update(secondary_sim=None)

        return super().update(instance, validated_data)

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
            name = obj.document.name
            if name and ('raw/upload/' in name or 'image/upload/' in name):
                return f"https://res.cloudinary.com/dzmvrjvfs/{name}"
            return obj.document.url
        return None

class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    responsible_locations = serializers.SerializerMethodField()
    
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
            "responsible_locations",
        ]
    
    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        return obj.username

    def get_assets(self, obj):
        assets = obj.assigned_assets.all()
        return AssetSerializer(assets, many=True).data

    def get_responsible_locations(self, obj):
        if obj.location:
            locs = Location.objects.filter(name__icontains=obj.location, company=obj.company)
            return LocationSerializer(locs, many=True).data
        return []


class CandidateSerializer(serializers.ModelSerializer):
    resume_url = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = "__all__"

    def get_resume_url(self, obj):
        if obj.resume:
            name = obj.resume.name
            if name and ('raw/upload/' in name or 'image/upload/' in name):
                return f"https://res.cloudinary.com/dzmvrjvfs/{name}"
            return obj.resume.url
        return None