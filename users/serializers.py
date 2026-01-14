from rest_framework import serializers
from django.contrib.auth import authenticate
from users.models import CustomUser

class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'employee_id', 'role', 'department', 'designation',
            'date_of_joining', 'employment_type', 'is_active',
            'organization', 'organization_name'
        ]
        read_only_fields = ['id']


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer"""
    department_name = serializers.CharField(source='department.name', read_only=True)
    designation_name = serializers.CharField(source='designation.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'date_of_birth', 'gender', 'employee_id',
            'department', 'department_name', 'designation', 'designation_name',
            'manager', 'office_location', 'role', 'employment_type',
            'date_of_joining', 'date_of_leaving', 'bank_account_number',
            'bank_ifsc_code', 'aadhar_number', 'pan_number', 'uan_number',
            'profile_picture', 'is_verified', 'is_active', 'created_at',
            'organization', 'organization_name'
        ]
        read_only_fields = ['id', 'created_at']


class RegisterSerializer(serializers.ModelSerializer):
    """User registration serializer"""
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ['email', 'username', 'password', 'password2', 'first_name', 'last_name', 'organization']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        user = CustomUser.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """Login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        data['user'] = user
        return data