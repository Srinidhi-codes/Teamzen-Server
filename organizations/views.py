from rest_framework import viewsets, parsers
from rest_framework.permissions import IsAuthenticated

from .models import Organization, OfficeLocation, Department, Designation
from .serializers import (
    OrganizationSerializer,
    OfficeLocationSerializer,
    DepartmentSerializer,
    DesignationSerializer,
)


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]


class OfficeLocationViewSet(viewsets.ModelViewSet):
    queryset = OfficeLocation.objects.all()
    serializer_class = OfficeLocationSerializer
    permission_classes = [IsAuthenticated]


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]


class DesignationViewSet(viewsets.ModelViewSet):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer
    permission_classes = [IsAuthenticated]

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import EmailMultiAlternatives
import traceback
from temp_email.welcome_email import get_welcome_email_html

class TestEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            html_content = get_welcome_email_html(
                employee_name=request.user.first_name or "Admin User",
                employee_email=email,
                designation="System Admin",
                joining_date="Today"
            )
            msg = EmailMultiAlternatives(
                subject="[Test] Email Settings Validation",
                body="Test email.",
                from_email="no-reply@teamzen.com",
                to=[email]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            return Response({"message": f"Test email successfully sent to {email}"})
        except Exception as e:
            return Response({"error": str(e), "traceback": traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

