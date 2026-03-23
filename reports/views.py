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
        Dynamically populates the Sample Model .xlsm directly and streams the file 
        back to the user to guarantee formulas and cell styling remain perfectly intact.
        """
        report = self.get_object()
        
        try:
            # We map assumption values onto the 'Input ' sheet structure based on the schema mapping
            file_path = r'C:\Users\newsh\OneDrive\Documents\Jobs\PLYGROUND\models\PLYGROUND SAMPLE MODEL -Manufacturing Model.xlsm'
            
            if not os.path.exists(file_path):
                return HttpResponse('Template missing', status=500)
                
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=False, keep_vba=True)
            input_sheet = wb['Input ']
            
            # Use the base scenario (or first) from the associated model
            scenario = report.financial_model.scenarios.filter(scenario_type='base').first() or report.financial_model.scenarios.first()
            if scenario:
                # General assumption injections
                try: macro = scenario.macro_assumptions
                except: macro = None
                
                if macro:
                    input_sheet['F36'] = macro.number_of_years
                    input_sheet['F10'] = macro.exchange_rate_local_per_usd
                    input_sheet['F61'] = macro.local_inflation_rate / 100 if macro.local_inflation_rate else 0.28
                    input_sheet['F62'] = macro.usd_inflation_rate / 100 if macro.usd_inflation_rate else 0.041
                    
                # Setup Project Info Injections    
                try: p_info = scenario.project_info
                except: p_info = None
                
                if p_info:
                    input_sheet['F15'] = p_info.days_in_year
                    input_sheet['F17'] = p_info.hours_in_day
                    input_sheet['F34'] = p_info.project_commencement_date
                    input_sheet['F46'] = p_info.construction_start_date
                    input_sheet['F47'] = p_info.construction_duration_months
                    
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            
            # Clean filename
            filename = f"Export_{report.name.replace(' ', '_')}.xlsm"
            
            response = HttpResponse(
                output,
                content_type='application/vnd.ms-excel.sheet.macroEnabled.12'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            return HttpResponse(str(e), status=500)
