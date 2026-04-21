from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from django.http import HttpResponse
from .models import Report
from .serializers import ReportSerializer
import os
import io


class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Report.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None):
        """
        Export report data to Excel using the shared ExcelExporter.
        Uses the report's linked scenario to generate a professional Excel workbook
        with all calculated financial statements, assumptions, and schedules.
        GET /api/reports/{id}/export_excel/
        """
        report = self.get_object()
        
        try:
            # Get the scenario linked to this report
            scenario = report.scenario
            if not scenario and report.financial_model:
                # Fallback: use base case scenario from the linked model
                scenario = (
                    report.financial_model.scenarios.filter(scenario_type='base').first() or
                    report.financial_model.scenarios.first()
                )
            
            if not scenario:
                return HttpResponse('No scenario found for this report.', status=400)
            
            from model.excel_export import ExcelExporter
            exporter = ExcelExporter()
            
            # Generate Excel file for the scenario
            excel_buffer = exporter.export_scenario(scenario)
            
            # Clean filename
            filename = f"Export_{report.name.replace(' ', '_')}.xlsx"
            
            response = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            return HttpResponse(str(e), status=500)
