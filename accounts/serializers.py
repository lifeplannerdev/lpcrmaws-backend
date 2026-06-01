from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User,ActivityLog


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
            'permissions'
        ]
        read_only_fields = fields


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
            'assets'
        ]
        read_only_fields = ['date_joined', 'last_login']

    assets = serializers.SerializerMethodField()

    def get_assets(self, obj):
        from hr.serializers import AssetSerializer
        assets = obj.assigned_assets.all()
        return AssetSerializer(assets, many=True).data


#  Staff Create/Update Serializer 
class StaffCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    
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
            'join_date'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


#  Staff Update Serializer
class StaffUpdateSerializer(serializers.ModelSerializer):
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
            'permissions'
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