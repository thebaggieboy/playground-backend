from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import uuid 


# Create your models here.
class ModelTemplates(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_name = models.CharField(max_length=250, null=True, blank=True)
    model_type = models.CharField(max_length=250, null=True, blank=True)
    model_category = models.CharField(max_length=250, null=True, blank=True)
    description = models.CharField(max_length=250, null=True, blank=True)
    slug = models.SlugField(null=True, blank=True, default='')
    # FIXED: Added date_created field
    date_created = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f'Lead: {self.model_name or "Unknown"}'

    def save(self, *args, **kwargs):
        if not self.slug:
            slug_source = self.model_name
            self.slug = slugify(slug_source)
        return super().save(*args, **kwargs)
