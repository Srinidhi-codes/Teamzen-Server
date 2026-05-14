from rest_framework import serializers
from django.contrib.auth import authenticate
from users.models import CustomUser
from organizations.serializers import OfficeLocationSerializer

class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'employee_id', 'role', 'department', 'designation', 'office_location',
            'date_of_joining', 'employment_type', 'is_active',
            'organization', 'organization_name', 'has_seen_onboarding', 'has_seen_ai_onboarding'
        ]
        read_only_fields = ['id']


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer"""
    department_name = serializers.CharField(source='department.name', read_only=True)
    designation_name = serializers.CharField(source='designation.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    office_location_details = OfficeLocationSerializer(source='office_location', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'date_of_birth', 'gender', 'employee_id',
            'department', 'department_name', 'designation', 'designation_name',
            'manager', 'office_location', 'office_location_details', 'role', 'employment_type',
            'date_of_joining', 'date_of_exit', 'bank_account_number',
            'bank_ifsc_code', 'aadhar_number', 'pan_number', 'uan_number',
            'profile_picture', 'is_verified', 'is_active', 'created_at',
            'organization', 'organization_name', 'has_seen_onboarding', 'has_seen_ai_onboarding'
        ]
        read_only_fields = [
            'id', 'created_at', 'role', 'is_verified', 'is_active', 
            'organization', 'department', 'designation', 'manager', 
            'office_location', 'employee_id', 'date_of_joining', 'date_of_exit',
            'email', 'username'
        ]


from organizations.models import Organization

class RegisterSerializer(serializers.ModelSerializer):
    """User registration serializer"""
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)
    organization_name = serializers.CharField(write_only=True, required=False)
    plan = serializers.CharField(write_only=True, required=False, default='free')

    class Meta:
        model = CustomUser
        fields = ['email', 'username', 'password', 'password2', 'first_name', 'last_name', 'organization', 'organization_name', 'plan']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        organization_name = validated_data.pop('organization_name', None)
        plan = validated_data.pop('plan', 'free')
        
        # If organization_name is provided, create a new org and set user as admin
        if organization_name:
            org = Organization.objects.create(name=organization_name, plan=plan)
            validated_data['organization'] = org
            validated_data['role'] = 'admin'
        
        user = CustomUser.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """Login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    latitude = serializers.DecimalField(max_digits=25, decimal_places=10, required=False)
    longitude = serializers.DecimalField(max_digits=25, decimal_places=10, required=False)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        data['user'] = user
        return data