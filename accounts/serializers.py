from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User, ActivityLog, Role, AppPermission


# Login Serializer
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data.get("username")
        password = data.get("password")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid username or password")
        if not user.is_active:
            raise serializers.ValidationError(
                "Your account is inactive or pending admin approval."
            )

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid username or password")

        data["user"] = user
        return data



#  Staff List Serializer 
class StaffListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'company',
            'date_joined',
            'phone',             
            'personal_phone',
            'office_phone',
            'location', 
            'is_active',
            'team',
            'salary',
            'join_date',
            'permissions',
            'db_roles',
            'role_names'
        ]
        read_only_fields = fields

    permissions = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()

    def get_permissions(self, obj):
        from .services import PermissionService
        return PermissionService.get_user_permissions(obj)

    def get_role_names(self, obj):
        return list(obj.db_roles.values_list('name', flat=True))


#  Staff Detail Serializer 
class StaffDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'company',
            'team',
            'date_joined',
            'last_login',
            'is_active',
            'phone',              
            'personal_phone',
            'office_phone',
            'location', 
            'salary',
            'join_date',
            'permissions',
            'assets',
            'db_roles',
            'role_names'
        ]
        read_only_fields = ['date_joined', 'last_login']

    assets = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()

    def get_assets(self, obj):
        from hr.serializers import AssetSerializer
        assets = obj.assigned_assets.all()
        return AssetSerializer(assets, many=True).data

    def get_permissions(self, obj):
        from .services import PermissionService
        return PermissionService.get_user_permissions(obj)

    def get_role_names(self, obj):
        return list(obj.db_roles.values_list('name', flat=True))


#  Staff Create/Update Serializer 
class StaffCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    db_roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.all(), required=False)
    
    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'company',
            'team',
            'is_active',
            'password',
            'phone',              
            'personal_phone',
            'office_phone',
            'location',
            'salary',
            'join_date',
            'db_roles'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        db_roles = validated_data.pop('db_roles', [])
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if db_roles:
            user.db_roles.set(db_roles)
        return user


#  Staff Update Serializer
class StaffUpdateSerializer(serializers.ModelSerializer):
    db_roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.all(), required=False)

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'company',
            'team',
            'is_active',
            'phone',
            'personal_phone',
            'office_phone',
            'location',
            'salary',
            'join_date',
            'permissions',
            'db_roles'
        ]


 
class ActivityLogSerializer(serializers.ModelSerializer):
    user_name    = serializers.SerializerMethodField()
    action_label = serializers.CharField(source='get_action_display', read_only=True)
 
    class Meta:
        model  = ActivityLog
        fields = [
            'id',
            'user', 'user_name',
            'action', 'action_label',
            'entity_type', 'entity_id', 'entity_name',
            'description',
            'metadata',
            'created_at',
        ]
 
    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return 'System'



class AppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppPermission
        fields = ['id', 'name', 'description']

class RoleSerializer(serializers.ModelSerializer):
    permissions = AppPermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'permissions', 'permission_ids']

    def create(self, validated_data):
        permission_ids = validated_data.pop('permission_ids', [])
        role = Role.objects.create(**validated_data)
        if permission_ids:
            role.permissions.set(permission_ids)
        return role

    def update(self, instance, validated_data):
        permission_ids = validated_data.pop('permission_ids', None)
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.save()
        if permission_ids is not None:
            instance.permissions.set(permission_ids)
        return instance