from rest_framework import viewsets
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
