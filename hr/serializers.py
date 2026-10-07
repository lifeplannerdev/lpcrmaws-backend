from django.db.models import Q
from rest_framework import serializers
from .models import Penalty, PenaltyType, AttendanceDocument, Candidate, Asset, Location, AssetCategory, Branch, DocumentDetail
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

def _get_attachment_url(attachment_field, request=None):
    if not attachment_field:
        return None
    try:
        url = attachment_field.url
        if request and url:
            return request.build_absolute_uri(url)
        return url
    except Exception:
        return None

class LocationSerializer(serializers.ModelSerializer):
    branch_details = BranchSerializer(source='branch', read_only=True)
    assigned_to_details = UserMinimalSerializer(source='assigned_to', read_only=True)
    assigned_staff = serializers.SerializerMethodField(read_only=True)
    assigned_assets = serializers.SerializerMethodField(read_only=True)
    members = serializers.SerializerMethodField(read_only=True)
    general_assets = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Location
        fields = '__all__'

    def get_assigned_staff(self, obj):
        obj_name_clean = (obj.name or '').strip()
        if not obj_name_clean:
            return []
        loc_filter = Q(location__icontains=obj_name_clean) | Q(location=str(obj.id))
        candidates = User.objects.filter(loc_filter)
        if obj.company:
            candidates = candidates.filter(Q(company=obj.company) | Q(company__isnull=True))
        matched = [
            u for u in candidates
            if u.location and (
                u.location.strip().lower() == obj_name_clean.lower() or
                u.location.strip() == str(obj.id)
            )
        ]
        return UserMinimalSerializer(matched, many=True).data
        
    def get_assigned_assets(self, obj):
        assets = obj.assets.all()
        return [
            {
                "id": a.id,
                "name": a.name,
                "category": a.category.name if a.category else None,
                "classification": a.classification,
                "serial_number": a.serial_number,
                "provider": a.provider,
                "assigned_to": a.assigned_to.id if a.assigned_to else None,
            } for a in assets
        ]

    def get_members(self, obj):
        user_ids = set()
        if obj.assigned_to_id:
            user_ids.add(obj.assigned_to_id)

        obj_name_clean = (obj.name or '').strip()
        if obj_name_clean:
            loc_filter = Q(location__icontains=obj_name_clean) | Q(location=str(obj.id))
        else:
            loc_filter = Q(location=str(obj.id))

        loc_candidates = User.objects.filter(loc_filter)
        if obj.company:
            loc_candidates = loc_candidates.filter(Q(company=obj.company) | Q(company__isnull=True))
        for u in loc_candidates:
            if u.location and (
                (obj_name_clean and u.location.strip().lower() == obj_name_clean.lower()) or
                u.location.strip() == str(obj.id)
            ):
                user_ids.add(u.id)

        asset_user_ids = obj.assets.filter(assigned_to__isnull=False).values_list('assigned_to_id', flat=True)
        for uid in asset_user_ids:
            if uid:
                user_ids.add(uid)

        if not user_ids:
            return []

        # Bulk fetch all members and sort: manager first, then alphabetical by display name
        users = list(User.objects.filter(id__in=user_ids))
        users.sort(key=lambda u: (
            0 if u.id == obj.assigned_to_id else 1,
            (f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username).lower()
        ))

        # Bulk fetch all candidate assets for these users
        all_user_assets = Asset.objects.filter(
            assigned_to_id__in=user_ids
        ).filter(
            Q(assigned_location=obj) | Q(assigned_location__isnull=True)
        ).select_related('category')

        from collections import defaultdict
        assets_by_user = defaultdict(list)
        for a in all_user_assets:
            assets_by_user[a.assigned_to_id].append(a)

        request = self.context.get('request')
        members_data = []
        for user in users:
            is_cabin_occupant = (
                obj.assigned_to_id == user.id or
                bool(user.location and (user.location.strip().lower() == obj_name_clean.lower() or user.location == str(obj.id)))
            )
            raw_assets = assets_by_user.get(user.id, [])
            if is_cabin_occupant:
                user_assets = raw_assets
            else:
                user_assets = [a for a in raw_assets if a.assigned_location_id == obj.id]

            members_data.append({
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                "email": user.email,
                "phone": user.phone or user.office_phone,
                "is_manager": obj.assigned_to_id == user.id,
                "assets": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "category": a.category.name if a.category else None,
                        "classification": a.classification,
                        "serial_number": a.serial_number,
                        "provider": a.provider,
                        "attachment_url": _get_attachment_url(a.attachment, request),
                    } for a in user_assets
                ]
            })
        return members_data

    def get_general_assets(self, obj):
        general = obj.assets.filter(assigned_to__isnull=True).select_related('category')
        request = self.context.get('request')
        return [
            {
                "id": a.id,
                "name": a.name,
                "category": a.category.name if a.category else None,
                "classification": a.classification,
                "serial_number": a.serial_number,
                "provider": a.provider,
                "purchase_date": str(a.purchase_date) if a.purchase_date else None,
                "notes": a.notes,
                "attachment_url": _get_attachment_url(a.attachment, request),
            } for a in general
        ]

class LocationMinimalSerializer(serializers.ModelSerializer):
    branch_details = BranchSerializer(source='branch', read_only=True)
    assigned_to_details = UserMinimalSerializer(source='assigned_to', read_only=True)

    class Meta:
        model = Location
        fields = ['id', 'name', 'company', 'branch', 'branch_details', 'assigned_to', 'assigned_to_details', 'created_at']

class LocationSummarySerializer(serializers.ModelSerializer):
    branch_details = BranchSerializer(source='branch', read_only=True)
    assigned_to_details = UserMinimalSerializer(source='assigned_to', read_only=True)
    assigned_assets = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Location
        fields = ['id', 'name', 'company', 'branch', 'branch_details', 'assigned_to', 'assigned_to_details', 'assigned_assets', 'created_at']

    def get_assigned_assets(self, obj):
        assets = obj.assets.select_related('category').all()
        return [
            {
                "id": a.id,
                "name": a.name,
                "category": a.category.name if a.category else None,
                "classification": a.classification,
                "serial_number": a.serial_number,
                "provider": a.provider,
                "assigned_to": a.assigned_to_id,
            } for a in assets
        ]

class AssetCategorySerializer(serializers.ModelSerializer):
    classification = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = AssetCategory
        fields = ['id', 'name', 'classification', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['classification'] = instance.get_classification()
        return data

class AssetSerializer(serializers.ModelSerializer):
    assigned_to_details = UserMinimalSerializer(source='assigned_to', read_only=True)
    assigned_location_details = LocationMinimalSerializer(source='assigned_location', read_only=True)
    category_details = AssetCategorySerializer(source='category', read_only=True)
    branch_details = BranchSerializer(source='branch', read_only=True)
    classification = serializers.CharField(read_only=True)
    attachment_url = serializers.SerializerMethodField(read_only=True)
    primary_sim_details = serializers.SerializerMethodField(read_only=True)
    secondary_sim_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'category', 'category_details', 'classification', 'serial_number', 'company',
            'primary_sim', 'primary_sim_details', 'secondary_sim', 'secondary_sim_details', 'provider',
            'assigned_to', 'assigned_to_details', 'assigned_location', 'assigned_location_details',
            'branch', 'branch_details', 'attachment', 'attachment_url', 'purchase_date', 'notes', 'created_at', 'updated_at'
        ]

    def get_attachment_url(self, obj):
        return _get_attachment_url(obj.attachment, self.context.get('request'))

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

class PenaltyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PenaltyType
        fields = ['id', 'name', 'description', 'default_amount']

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
            'company',
            'source_report_id'
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
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document.url)
            return obj.document.url
        return None

class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    responsible_locations = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()
    
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
            "role_names",
            "assets",
            "responsible_locations",
        ]
    
    def get_role_names(self, obj):
        if hasattr(obj, 'db_roles'):
            return list(obj.db_roles.values_list('name', flat=True))
        return []

    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        return obj.username

    def get_assets(self, obj):
        assets = obj.assigned_assets.all()
        return AssetSerializer(assets, many=True, context=self.context).data

    def get_responsible_locations(self, obj):
        filters = Q(assigned_to=obj)
        if obj.location and obj.location.strip():
            filters |= Q(name__icontains=obj.location.strip())
        if obj.company:
            filters &= (Q(company=obj.company) | Q(company__isnull=True))
        locs = Location.objects.filter(filters).distinct().select_related('branch', 'assigned_to').prefetch_related('assets__category')
        return LocationSummarySerializer(locs, many=True, context=self.context).data


class CandidateSerializer(serializers.ModelSerializer):
    resume_url = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = "__all__"

    def get_resume_url(self, obj):
        if obj.resume:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.resume.url)
            return obj.resume.url
        return None

class DocumentDetailSerializer(serializers.ModelSerializer):
    days_remaining = serializers.SerializerMethodField(read_only=True)
    days_remaining_next = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DocumentDetail
        fields = '__all__'
        read_only_fields = ['next_renewal_date', 'created_at', 'updated_at']

    def get_days_remaining(self, obj):
        """Days until expiry. Negative = already expired."""
        from django.utils import timezone
        today = timezone.now().date()
        if not obj.expiry_date:
            return None
        return (obj.expiry_date - today).days

    def get_days_remaining_next(self, obj):
        """Days until next renewal date (post-expiry). Null if no renewal interval."""
        from django.utils import timezone
        today = timezone.now().date()
        if not obj.next_renewal_date:
            return None
        return (obj.next_renewal_date - today).days