from rest_framework import serializers
from django.conf import settings
from .models import Profile, AccountUser
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer


# Custom Serializer for Djoser Library 
class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = ['id',  'email', 'password' ]
       
 
class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AccountUser
        fields = ['id', 'slug',  'email', 'brand_name', 'brand_logo',  'brand_bio', 'followers', 'brand_type', 'mobile_number', 'is_active', 'staff', 'admin']


class ProfileSerializer(serializers.HyperlinkedModelSerializer):
    user = serializers.HyperlinkedRelatedField(view_name='profile-detail',queryset=Profile.objects.all())
    class Meta:
        model = Profile
        fields = ['id', 'user', 'date_created']


