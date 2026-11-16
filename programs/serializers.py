from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import (
    Program,
    ProgramCountry,
    ProgramUniversity,
    ProgramIntake,
    AssignedProgram,
    AssignedProgramChangeLog,
    AssignedStudentRecord,
    AssignedStudentChangeLog,
)

User = get_user_model()


def _display_user(user):
    if not user:
        return None
    full = user.get_full_name().strip()
    return full or user.username

class ProgramCountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgramCountry
        fields = '__all__'

class ProgramUniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgramUniversity
        fields = '__all__'

class ProgramIntakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgramIntake
        fields = '__all__'

class ProgramSerializer(serializers.ModelSerializer):
    country = serializers.SlugRelatedField(slug_field='name', queryset=ProgramCountry.objects.all(), allow_null=True, required=False)
    university = serializers.SlugRelatedField(slug_field='name', queryset=ProgramUniversity.objects.all(), allow_null=True, required=False)
    intake = serializers.SlugRelatedField(slug_field='name', queryset=ProgramIntake.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Program
        fields = '__all__'


class AssignedProgramChangeLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    def get_changed_by_name(self, obj):
        return _display_user(obj.changed_by) or 'System'

    class Meta:
        model = AssignedProgramChangeLog
        fields = [
            'id', 'action', 'field_name', 'field_label',
            'old_value', 'new_value', 'changed_by', 'changed_by_name', 'created_at',
        ]


class AssignedStudentChangeLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    def get_changed_by_name(self, obj):
        return _display_user(obj.changed_by) or 'System'

    class Meta:
        model = AssignedStudentChangeLog
        fields = [
            'id', 'action', 'field_name', 'field_label',
            'old_value', 'new_value', 'changed_by', 'changed_by_name', 'created_at',
        ]


class AssignedProgramSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    def get_assigned_to_name(self, obj):
        return _display_user(obj.assigned_to)

    def get_created_by_name(self, obj):
        return _display_user(obj.created_by)

    class Meta:
        model = AssignedProgram
        fields = [
            'id', 'sl_no', 'project', 'country', 'assignment',
            'completed', 'presentation', 'training_to_team',
            'assigned_to', 'assigned_to_name', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class AssignedStudentRecordSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    def get_assigned_to_name(self, obj):
        return _display_user(obj.assigned_to)

    def get_created_by_name(self, obj):
        return _display_user(obj.created_by)

    class Meta:
        model = AssignedStudentRecord
        fields = [
            'id', 'sl_no', 'name', 'age', 'phone', 'email_address',
            'place', 'qualification', 'preferred_country', 'preferred_program',
            'intake', 'aps_status', 'ielts_status', 'german_status',
            'assigned_to', 'assigned_to_name', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']
