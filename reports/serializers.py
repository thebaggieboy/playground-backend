from rest_framework import serializers
from .models import Report
from django.contrib.auth import get_user_model

User = get_user_model()


class ReportSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source='financial_model.name', read_only=True)
    scenario_name = serializers.CharField(source='scenario.name', read_only=True)
    calculated_data = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            'id', 'name', 'description', 'user', 'financial_model', 'scenario',
            'report_type', 'status', 'report_data', 'report', 'slug', 'date_created',
            'model_name', 'scenario_name', 'calculated_data'
        ]
        read_only_fields = ['id', 'user', 'slug', 'date_created', 'status', 'report_data']

    def get_calculated_data(self, obj):
        """
        Pull calculated statements from the linked scenario grouped by type.
        Returns a dict: { 'is': [...], 'bs': [...], 'cfs': [...], 'ratio': [...], 'debt': [...] }
        Each item: { line_item, values_by_period }
        """
        if not obj.scenario:
            return None

        try:
            statements = obj.scenario.calculated_statements.all()
            if not statements.exists():
                return None

            grouped = {}
            for stmt in statements:
                stype = stmt.statement_type
                if stype not in grouped:
                    grouped[stype] = []
                grouped[stype].append({
                    'line_item': stmt.line_item,
                    'values_by_period': stmt.values_by_period,
                })
            return grouped
        except Exception:
            return None
