from django.db import models

class Program(models.Model):
    title = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    qualification = models.TextField(blank=True, null=True)
    course_duration = models.CharField(max_length=255, blank=True, null=True)
    university = models.CharField(max_length=255, blank=True, null=True)
    intake = models.CharField(max_length=255, blank=True, null=True)
    
    # JSON field to store arbitrary fees structure (e.g. [{"name": "Application Fee", "amount": "25000 + GST"}, ...])
    fees_structure = models.JSONField(default=list, blank=True)
    
    # JSON field to store list of services (e.g. ["Enrollment", "Visa Assistance"])
    services = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.country}"

