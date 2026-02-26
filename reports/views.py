from rest_framework import viewsets, permissions
from .models import Report
from .serializers import ReportSerializer

class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Report.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
