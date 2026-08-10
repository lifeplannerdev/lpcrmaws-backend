from django.db import models

class ProgramCountry(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class ProgramUniversity(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class ProgramIntake(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class Program(models.Model):
    title = models.CharField(max_length=255)
    country = models.ForeignKey(ProgramCountry, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    qualification = models.TextField(blank=True, null=True)
    course_duration = models.CharField(max_length=255, blank=True, null=True)
    university = models.ForeignKey(ProgramUniversity, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    intake = models.ForeignKey(ProgramIntake, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    
    # JSON field to store arbitrary fees structure (e.g. [{"name": "Application Fee", "amount": "25000 + GST"}, ...])
    fees_structure = models.JSONField(default=list, blank=True)
    
    # JSON field to store list of services (e.g. ["Enrollment", "Visa Assistance"])
    services = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.country}"

