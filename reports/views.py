from django.shortcuts import render
from .models import  Reports
from django.conf import settings
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import viewsets
from .serializers import ReportSerializer

class ReportViewSet(viewsets.ModelViewSet):
    queryset = Reports.objects.all()
    serializer_class = ReportSerializer
    
