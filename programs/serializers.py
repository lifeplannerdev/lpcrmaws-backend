from rest_framework import serializers
from .models import Program, ProgramCountry, ProgramUniversity, ProgramIntake

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
