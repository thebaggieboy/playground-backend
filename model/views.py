from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from accounts.models import  AccountUser
from django.conf import settings
# Create your views here.
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import viewsets
from .serializers import ModelSerializer

class ModelViewSet(viewsets.ModelViewSet):
    queryset = AccountUser.objects.all()
    serializer_class = ModelSerializer
    
