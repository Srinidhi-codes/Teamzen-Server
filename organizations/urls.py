from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet,
    OfficeLocationViewSet,
    DepartmentViewSet,
    DesignationViewSet,
)

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet)
router.register(r'office-locations', OfficeLocationViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'designations', DesignationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
