# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('api/notifications/', views.NotificationListAPI.as_view(), name='notification-list'),
    path('api/notifications/unread_count/', views.UnreadNotificationCountAPI.as_view(), name='unread-count'),
    path('api/notifications/mark_as_read/', views.MarkAsReadAPI.as_view(), name='mark-as-read'),
]