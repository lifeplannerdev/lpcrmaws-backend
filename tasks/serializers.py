from rest_framework import serializers
from django.utils import timezone
from .models import Task, TaskUpdate
from django.contrib.auth import get_user_model

User = get_user_model()

#  Employee Serializer
class EmployeeSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'is_active', 'role', 'role_names']
        
    def get_role(self, obj):
        return ", ".join(obj.db_roles.values_list('name', flat=True))

    def get_role_names(self, obj):
        return list(obj.db_roles.values_list('name', flat=True))


#  Task Serializer 
class TaskSerializer(serializers.ModelSerializer):
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.username', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    
    # Add these computed fields that your frontend expects
    is_overdue = serializers.BooleanField(read_only=True)
    overdue_days = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    requires_attention_from = serializers.PrimaryKeyRelatedField(read_only=True)
    requires_attention_from_name = serializers.CharField(source='requires_attention_from.username', read_only=True)
    
    class Meta:
        model = Task
        fields = "__all__"
    
    def get_overdue_days(self, obj):
        if obj.status in ['COMPLETED', 'CANCELLED']:
            return 0
        if obj.is_overdue:
            delta = timezone.now().date() - obj.deadline
            return delta.days
        return 0
    
    def get_days_until_deadline(self, obj):
        if obj.status in ['COMPLETED', 'CANCELLED']:
            return 0
        delta = obj.deadline - timezone.now().date()
        return delta.days if delta.days > 0 else 0
    
    def validate(self, attrs):
        request = self.context.get("request")
        assigned_to = attrs.get("assigned_to")
        if request and assigned_to and request.user == assigned_to:
            raise serializers.ValidationError(
                "You cannot assign a task to yourself."
            )
        return attrs


#  Task Update Serializer 
class TaskUpdateSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(source='updated_by.username', read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    task = serializers.PrimaryKeyRelatedField(read_only=True)  # Set in view context
    new_status = serializers.CharField(required=False)
    previous_status = serializers.CharField(required=False)

    class Meta:
        model = TaskUpdate
        fields = [
            'id', 'task', 'updated_by', 'updated_by_name',
            'previous_status', 'new_status', 'notes', 'created_at'
        ]

    #  Validation 
    def validate(self, attrs):
        task = self.context.get('task')  
        if not task:
            raise serializers.ValidationError("Task context is required for validation.")

        new_status = attrs.get('new_status')
        notes = attrs.get('notes', '')

        # new_status is optional — assignees may post a note without changing status
        if new_status is not None:
            # If a status is provided, it must actually differ from current
            if new_status == task.status:
                raise serializers.ValidationError("New status must be different from the current status.")

            # Require notes when completing or cancelling
            if new_status in ['COMPLETED', 'CANCELLED'] and not notes.strip():
                raise serializers.ValidationError("Notes are required when completing or cancelling a task.")
        else:
            # Notes-only update: require non-empty notes
            if not notes.strip():
                raise serializers.ValidationError("Please provide a note.")

        return attrs


#  Upcoming Task Serializer
class UpcomingTaskSerializer(serializers.ModelSerializer):
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    days_left = serializers.IntegerField(source="days_until_deadline", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "priority",
            "priority_label",
            "status",
            "status_label",
            "deadline",
            "days_left",
            "is_overdue",
        ]