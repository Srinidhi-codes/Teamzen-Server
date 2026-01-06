from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from math import radians, sin, cos, sqrt, atan2
from django.utils import timezone
from attendance.models import AttendanceRecord, AttendanceCorrection
from attendance.serializers import AttendanceRecordSerializer, AttendanceCorrectionSerializer
from organizations.models import OfficeLocation

class AttendanceRecordViewSet(viewsets.ModelViewSet):
    """Attendance management"""
    serializer_class = AttendanceRecordSerializer
    permission_classes = []

    def get_queryset(self):
        return AttendanceRecord.objects.filter(user=self.request.user)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two coordinates"""
        R = 6371000  # Earth radius in meters
        phi1 = radians(float(lat1))
        phi2 = radians(float(lat2))
        delta_phi = radians(float(lat2) - float(lat1))
        delta_lambda = radians(float(lon2) - float(lon1))

        a = sin(delta_phi/2)**2 + cos(phi1)*cos(phi2)*sin(delta_lambda/2)**2
        c = 2*atan2(sqrt(a), sqrt(1-a))
        return R*c

    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """Check in to office"""
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        office_id = request.data.get('office_id')

        if not all([latitude, longitude, office_id]):
            return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return Response({'error': 'Latitude and longitude must be valid numbers'},status=status.HTTP_400_BAD_REQUEST)

        office = get_object_or_404(OfficeLocation, id=office_id)

        distance = self.calculate_distance(latitude, longitude, office.latitude, office.longitude)
        is_within_geofence = distance <= office.geo_radius_meters

        if distance > office.geo_radius_meters:
            return Response(
                {
                    'message': 'Not within geofence',
                    'is_within_geofence': False,
                    'distance': round(distance, 2),
                    'allowed_radius': office.geo_radius_meters
                },
                status=status.HTTP_403_FORBIDDEN
            )

        attendance, created = AttendanceRecord.objects.get_or_create(
            user=request.user,
            attendance_date=timezone.now().date(),
            office_location=office
        )

        attendance.login_time = timezone.now()
        attendance.login_latitude = latitude
        attendance.login_longitude = longitude
        attendance.is_within_geofence = is_within_geofence
        attendance.status = 'present'
        attendance.save()

        return Response({
            'message': 'Check-in successful',
            'is_within_geofence': is_within_geofence,
            'distance': distance
        },status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def check_out(self, request):
        """Check out from office"""

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        # 1. Validate input
        if not all([latitude, longitude]):
            return Response(
                {'error': 'Missing latitude or longitude'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Latitude and longitude must be valid numbers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Fetch today's attendance
        attendance = get_object_or_404(
            AttendanceRecord,
            user=request.user,
            attendance_date=timezone.now().date()
        )

        office = attendance.office_location

        # 3. Calculate logout distance
        logout_distance = self.calculate_distance(
            latitude,
            longitude,
            office.latitude,
            office.longitude
        )

        is_within_geofence = logout_distance <= office.geo_radius_meters

        # 4. Update attendance
        attendance.logout_time = timezone.now()
        attendance.logout_latitude = latitude
        attendance.logout_longitude = longitude
        attendance.logout_distance = logout_distance  # optional field
        attendance.is_within_geofence_logout = is_within_geofence  # optional field

        # 5. Calculate worked hours
        if attendance.login_time:
            attendance.worked_hours = round(
                (attendance.logout_time - attendance.login_time).total_seconds() / 3600,
                2
            )

        attendance.save()

        return Response(
            {
                'message': 'Check-out successful',
                'is_within_geofence': is_within_geofence,
                'distance': round(logout_distance, 2),
                'allowed_radius': office.geo_radius_meters,
                'worked_hours': attendance.worked_hours or 0
            },
            status=status.HTTP_200_OK
        )

    class AttendanceCorrectionViewSet(viewsets.ModelViewSet):
        """Attendance correction requests"""
        serializer_class = AttendanceCorrectionSerializer

        def get_queryset(self):
            user = self.request.user
            if user.role == 'employee':
                return AttendanceCorrection.objects.filter(requested_by=user)
            elif user.role == 'hr':
                return AttendanceCorrection.objects.filter(attendance_record__user__organization=user.organization)
            return AttendanceCorrection.objects.none()

        def perform_create(self, serializer):
            serializer.save(requested_by=self.request.user)

        @action(detail=True, methods=['post'])
        def approve(self, request, pk=None):
            """Approve correction"""
            correction = self.get_object()
            attendance = correction.attendance_record

            if correction.corrected_login_time:
                attendance.login_time = correction.corrected_login_time
            if correction.corrected_logout_time:
                attendance.logout_time = correction.corrected_logout_time

            attendance.save()
            correction.status = 'approved'
            correction.approved_by = request.user
            correction.save()

            return Response(AttendanceCorrectionSerializer(correction).data)
