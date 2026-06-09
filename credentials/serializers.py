from rest_framework import serializers
from .models import Credential, CredentialHistory, CredentialUpdateRequest, CredentialCategory
from accounts.serializers import StaffListSerializer, RoleSerializer

class CredentialCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CredentialCategory
        fields = ['id', 'name', 'color', 'icon_name', 'created_at']

class CredentialSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    shared_users_list = StaffListSerializer(source='shared_users', many=True, read_only=True)
    shared_roles_list = RoleSerializer(source='shared_roles', many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True) # Used for writing only
    category_detail = CredentialCategorySerializer(source='category', read_only=True)

    class Meta:
        model = Credential
        fields = [
            'id', 'title', 'username', 'url', 'notes', 'category', 'category_detail',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
            'shared_users', 'shared_roles', 'shared_users_list', 'shared_roles_list',
            'password'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate(self, data):
        # Enforce password on creation
        if not self.instance:
            if not data.get('password'):
                raise serializers.ValidationError({"password": "A password is required when creating a new credential."})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        shared_users = validated_data.pop('shared_users', [])
        shared_roles = validated_data.pop('shared_roles', [])
        
        credential = Credential.objects.create(**validated_data)
        if password:
            credential.set_password(password)
            credential.save()
            
        credential.shared_users.set(shared_users)
        credential.shared_roles.set(shared_roles)
        return credential

    def update(self, instance, validated_data):
        # We don't update password here for shared users, only for the creator or admins directly
        # Shared users will use the UpdateRequest workflow
        password = validated_data.pop('password', None)
        shared_users = validated_data.pop('shared_users', None)
        shared_roles = validated_data.pop('shared_roles', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if password:
            instance.set_password(password)
            
        instance.save()
        
        if shared_users is not None:
            instance.shared_users.set(shared_users)
        if shared_roles is not None:
            instance.shared_roles.set(shared_roles)
            
        return instance

class CredentialDetailSerializer(CredentialSerializer):
    # Includes decrypted password (only use this when explicitly requesting a detail view)
    decrypted_password = serializers.SerializerMethodField()

    class Meta(CredentialSerializer.Meta):
        fields = CredentialSerializer.Meta.fields + ['decrypted_password']

    def get_decrypted_password(self, obj):
        try:
            return obj.get_password()
        except Exception:
            return None

class CredentialHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    decrypted_password = serializers.SerializerMethodField()

    class Meta:
        model = CredentialHistory
        fields = ['id', 'credential', 'changed_by', 'changed_by_name', 'changed_at', 'decrypted_password']

    def get_decrypted_password(self, obj):
        try:
            return obj.get_password()
        except Exception:
            return None

class CredentialUpdateRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    proposed_password = serializers.CharField(write_only=True)
    credential_title = serializers.CharField(source='credential.title', read_only=True)

    class Meta:
        model = CredentialUpdateRequest
        fields = [
            'id', 'credential', 'credential_title', 'requested_by', 'requested_by_name',
            'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at',
            'proposed_password'
        ]
        read_only_fields = ['id', 'requested_by', 'status', 'reviewed_by', 'reviewed_at', 'created_at']

    def create(self, validated_data):
        proposed_password = validated_data.pop('proposed_password', None)
        request = CredentialUpdateRequest.objects.create(**validated_data)
        if proposed_password:
            request.set_proposed_password(proposed_password)
            request.save()
        return request
