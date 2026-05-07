# users/views.py
from rest_framework import viewsets, status, generics, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from users.models import CustomUser, UserLoginHistory
from rest_framework_simplejwt.views import TokenRefreshView
from users.serializers import UserSerializer, UserDetailSerializer, RegisterSerializer, LoginSerializer
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

User = get_user_model()

def get_cookie_settings(httponly=True):
    """Get cookie settings based on environment"""
    return {
        'httponly': httponly,
        'secure': not settings.DEBUG,
        'samesite': 'None' if not settings.DEBUG else 'Lax',
        'path': '/',
    }

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_location_from_ip(ip):
    import requests
    try:
        # Normalize IPv6-mapped IPv4 addresses
        if ip and ip.startswith('::ffff:'):
            ip = ip.replace('::ffff:', '')

        # Internal / Private IP ranges
        if not ip or ip == '127.0.0.1' or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.') or ip == '::1':
            return "Local Network"
        
        # Try Provider 1: ipapi.co
        try:
            response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
            if response.status_code == 200:
                data = response.json()
                if not data.get('error'):
                    city = data.get('city', 'Unknown')
                    region = data.get('region', '')
                    country = data.get('country_name', 'Unknown')
                    if region:
                        return f"{city}, {region}, {country}"
                    return f"{city}, {country}"
        except Exception:
            pass

        # Try Provider 2: ip-api.com (Fallback)
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    city = data.get('city', 'Unknown')
                    region = data.get('regionName', '')
                    country = data.get('country', 'Unknown')
                    if region:
                        return f"{city}, {region}, {country}"
                    return f"{city}, {country}"
        except Exception:
            pass
            
    except Exception:
        pass
    return "Unknown"

class UserViewSet(viewsets.ModelViewSet):
    """User management viewset"""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UserDetailSerializer
        return super().get_serializer_class()

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user info"""
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['put', 'patch'], parser_classes=[parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser])
    def update_profile(self, request):
        """Update user profile"""
        print(f"Update profile request data: {request.data.keys()}")
        print(f"Update profile files: {request.FILES.keys()}")
        user = request.user
        serializer = UserDetailSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        print(f"Update profile errors: {serializer.errors}") # Debugging
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user password"""
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not user.check_password(old_password):
            return Response({'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'success': 'Password changed successfully'})


class RegisterView(generics.CreateAPIView):
    """User registration view"""
    serializer_class = RegisterSerializer
    permission_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        
        response = Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

        cookie_settings = get_cookie_settings()
        
        response.set_cookie(
            key="access_token",
            value=str(refresh.access_token),
            max_age=30 * 60,  # 30 minutes
            **cookie_settings
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            max_age=7 * 24 * 60 * 60,  # 7 days
            **cookie_settings
        )

        # Set a non-httponly cookie so JS can check if it should attempt a refresh
        response.set_cookie(
            key="session_can_refresh",
            value="true",
            max_age=7 * 24 * 60 * 60,
            **get_cookie_settings(httponly=False)
        )

        return response


class LoginView(generics.GenericAPIView):
    """User login view"""
    serializer_class = LoginSerializer
    permission_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        
        response = Response({
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)
    
        cookie_settings = get_cookie_settings()

        response.set_cookie(
            key="access_token",
            value=str(refresh.access_token),
            max_age=30 * 60,
            **cookie_settings
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            max_age=7 * 24 * 60 * 60,
            **cookie_settings
        )

        # Set a non-httponly cookie so JS can check if it should attempt a refresh
        response.set_cookie(
            key="session_can_refresh",
            value="true",
            max_age=7 * 24 * 60 * 60,
            **get_cookie_settings(httponly=False)
        )

        # Log Login History
        try:
            ip = get_client_ip(request)
            UserLoginHistory.objects.create(
                user=user,
                ip_address=ip,
                location=get_location_from_ip(ip),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                status='success'
            )
        except Exception as e:
            print(f"Error logging login history: {e}")

        return response



class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = []
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Get refresh token from cookie or body
        data = {}
        if 'refresh' in request.data:
            data['refresh'] = request.data['refresh']
        elif 'refresh_token' in request.COOKIES:
            data['refresh'] = request.COOKIES['refresh_token']
        else:
            return Response(
                {'error': 'Refresh token not found'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = self.get_serializer(data=data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            response = Response(
                {'error': 'Invalid or expired refresh token'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
            # Clear invalid cookies
            response.delete_cookie('access_token', path='/')
            response.delete_cookie('refresh_token', path='/')
            return response
            
        token_data = serializer.validated_data
        
        response = Response({
            'access': token_data.get('access'),
            'refresh': token_data.get('refresh'),
        }, status=status.HTTP_200_OK)
        
        cookie_settings = get_cookie_settings()  # ← Use centralized settings
        
        # Always set new access token
        if 'access' in token_data:
            response.set_cookie(
                key="access_token",
                value=token_data['access'],
                max_age=30 * 60,
                **cookie_settings
            )
        
        # Set new refresh token if rotation is enabled
        if 'refresh' in token_data:
            response.set_cookie(
                key="refresh_token",
                value=token_data['refresh'],
                max_age=7 * 24 * 60 * 60,
                **cookie_settings
            )
            
        # Ensure session flag is present
        response.set_cookie(
            key="session_can_refresh",
            value="true",
            max_age=7 * 24 * 60 * 60,
            **get_cookie_settings(httponly=False)
        )
            
        return response


class LogoutView(APIView):
    permission_classes = []  # ← Allow logout even without valid token
    
    def post(self, request):
        try:
            # Blacklist the refresh token
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass  # Token already blacklisted or invalid
        
        response = Response({"detail": "Logged out successfully"}, status=200)
        response.delete_cookie("access_token", path='/')
        response.delete_cookie("refresh_token", path='/')
        response.delete_cookie("session_can_refresh", path='/')
        return response

class PasswordResetRequestView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # frontend_url = f"{settings.CLIENT_URL}/reset-password?uid={uid}&token={token}"
            # For robustness, handle both User and Admin clients or just one central reset page
            reset_url = f"{settings.CLIENT_URL}/reset-password?uid={uid}&token={token}"
            
            message = f"Click the link below to reset your password:\n{reset_url}"
            send_mail(
                "Password Reset - Payroll System",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            return Response({"success": "Password reset link sent to your email."}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            # Don't reveal if user exists or not for security, but return same success msg
            return Response({"success": "If an account exists with this email, a reset link has been sent."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PasswordResetConfirmView(APIView):
    permission_classes = []

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('password')

        if not all([uidb64, token, new_password]):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
            
            if default_token_generator.check_token(user, token):
                user.set_password(new_password)
                user.save()
                return Response({"success": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)