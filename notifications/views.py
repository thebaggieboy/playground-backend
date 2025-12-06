# notifications/views.py
from rest_framework import generics, permissions
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer
from django.db.models import Q

class NotificationListAPI(generics.ListAPIView):
    serializer_class = NotificationSerializer
    #permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

class UnreadNotificationCountAPI(generics.GenericAPIView):
    #permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'count': count})

class MarkAsReadAPI(generics.GenericAPIView):
    #permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'success'})