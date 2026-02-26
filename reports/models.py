from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=250, null=True, blank=True)
    description = models.CharField(max_length=250, null=True, blank=True)
    
    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports', null=True)
    financial_model = models.ForeignKey('model.FinancialModel', on_delete=models.CASCADE, related_name='reports', null=True)
    scenario = models.ForeignKey('model.Scenario', on_delete=models.CASCADE, related_name='reports', null=True)
    
    # Metadata
    report_type = models.CharField(max_length=100, default='Summary')
    status = models.CharField(max_length=50, default='completed')
    
    # Data storage
    report_data = models.JSONField(null=True, blank=True)
    report = models.FileField(upload_to='reports/', max_length=250, null=True, blank=True)
 
    slug = models.SlugField(null=True, blank=True, default='')
    date_created = models.DateTimeField(default=timezone.now)
    
    class Meta:
        verbose_name_plural = "Reports"
        ordering = ['-date_created']

    def __str__(self):
        return f'Report: {self.name or "Unknown"}'

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)