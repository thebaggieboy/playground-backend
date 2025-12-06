# notifications/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save

User = get_user_model()

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('LIKE', 'Like'),
        ('COMMENT', 'Comment'),
        ('FOLLOW', 'Follow'),
        ('MENTION', 'Mention'),
        ('SYSTEM', 'System'),
        ('ORDER', 'Order'),
        ('PAYMENT', 'Payment'),
        ('REVEIWS', 'Reviews'),
        ('MERCHANDISE', 'Merchandise'),
        ('BANK ACCOUNT', 'Bank Account'),
        ('COMMUNITY', 'Community'),
        ('COMMUNITY MEMBER', 'Community Member'),
        ('BILLING', 'Billing'),
        ('COUPON', 'Coupon')
        
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    target_url = models.URLField(null=True, blank=True)  # URL to redirect when clicked
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()} for {self.user.email}"



