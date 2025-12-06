from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import viewsets
from .serializers import UserSerializer, ProfileSerializer
 
from .models import Profile, AccountUser
from django.conf import settings

# Create your views here.
class UserViewSet(viewsets.ModelViewSet):
    queryset = AccountUser.objects.all()
    serializer_class = UserSerializer
    

class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
