from rest_framework import serializers
from .models import Report
from django.contrib.auth import get_user_model

User = get_user_model()

class ReportSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source='financial_model.name', read_only=True)
    scenario_name = serializers.CharField(source='scenario.name', read_only=True)
    
    class Meta:
        model = Report
        fields = [
            'id', 'name', 'description', 'user', 'financial_model', 'scenario',
            'report_type', 'status', 'report_data', 'report', 'slug', 'date_created',
            'model_name', 'scenario_name'
        ]
        read_only_fields = ['id', 'user', 'slug', 'date_created', 'status', 'report_data']
