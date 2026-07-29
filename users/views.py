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
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import get_user_model
from notifications.email_backends import BrevoHTTPBackend
from temp_email.password_reset_email import get_password_reset_email_html

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

def get_location_from_ip(ip, lat=None, lon=None):
    import requests
    try:
        # If we have precise coordinates, use them for reverse geocoding (Nominatim / OSM)
        if lat and lon:
            try:
                headers = {'User-Agent': 'Teamzen/1.0'}
                response = requests.get(
                    f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10", 
                    headers=headers,
                    timeout=3
                )
                if response.status_code == 200:
                    data = response.json()
                    address = data.get('address', {})
                    city = (
                        address.get('city') or 
                        address.get('town') or 
                        address.get('village') or 
                        address.get('suburb') or 
                        address.get('state_district') or 
                        address.get('neighbourhood') or 
                        address.get('county') or 
                        'Unknown'
                    )
                    country = address.get('country', 'Unknown')
                    return f"{city}, {country}"
            except Exception:
                pass

        # Fallback to IP-based location
        if not ip or ip == '127.0.0.1' or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
            return "Local Network"
            
        response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('error'):
                return "Unknown"
            return f"{data.get('city', 'Unknown')}, {data.get('country_name', 'Unknown')}"
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

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def upload_photo(self, request, pk=None):
        """Upload a photo for a specific user"""
        user_to_update = self.get_object()
        
        # Authorization: only admin, superadmin or the user themselves
        if request.user.role not in ['admin', 'superadmin', 'hr'] and str(request.user.id) != str(user_to_update.id):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
            
        photo = request.FILES.get('profile_picture')
        if not photo:
            return Response({'error': 'No photo provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        user_to_update.profile_picture = photo
        user_to_update.save()
        
        return Response({
            'success': True, 
            'profile_picture_url': user_to_update.profile_picture.url
        })

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
        from users.auth_views import login_user_and_set_cookies
        response = login_user_and_set_cookies(user, request)
        response.status_code = status.HTTP_201_CREATED
        return response


class LoginView(generics.GenericAPIView):
    """User login view"""
    serializer_class = LoginSerializer
    permission_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        
        # Check if 2FA (TOTP) is enabled
        if user.is_totp_enabled:
            import uuid
            from django.core.cache import cache
            temp_token = str(uuid.uuid4())
            cache.set(f"temp_totp_session_{temp_token}", user.id, timeout=300)
            return Response({
                "totp_required": True,
                "temp_token": temp_token
            }, status=status.HTTP_200_OK)
            
        from users.auth_views import login_user_and_set_cookies
        return login_user_and_set_cookies(user, request)



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
        except User.DoesNotExist:
            return Response(
                {"error": "No account found with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = f"{settings.CLIENT_URL}/reset-password?uid={uid}&token={token}"

            plain_text = f"Click the link below to reset your password:\n{reset_url}"
            html_content = get_password_reset_email_html(
                employee_name=f"{user.first_name} {user.last_name}".strip() or "there",
                reset_url=reset_url,
                company_name="Teamzen",
                company_url=settings.CLIENT_URL,
            )
            email_msg = EmailMultiAlternatives(
                subject="Password Reset - Payroll System",
                body=plain_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
                connection=BrevoHTTPBackend(),
            )
            email_msg.attach_alternative(html_content, "text/html")
            email_msg.send(fail_silently=False)
            return Response({"success": "Password reset link sent to your email."}, status=status.HTTP_200_OK)
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
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)


class UserDeviceSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from users.models import UserDeviceSession
        from users.serializers import UserDeviceSessionSerializer
        
        current_jti = request.auth.get('refresh_jti') if request.auth else None
        
        # Get active sessions for the user
        sessions = UserDeviceSession.objects.filter(user=request.user, is_active=True)
        
        serializer = UserDeviceSessionSerializer(
            sessions, 
            many=True, 
            context={'current_jti': current_jti}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from users.models import UserDeviceSession
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        
        jti = request.data.get('jti')
        if not jti:
            return Response({"error": "jti is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Revoke the UserDeviceSession
            session = UserDeviceSession.objects.filter(user=request.user, jti=jti, is_active=True).first()
            if session:
                session.is_active = False
                session.save()
                
            # Blacklist corresponding SimpleJWT token
            outstanding = OutstandingToken.objects.get(jti=jti, user=request.user)
            BlacklistedToken.objects.get_or_create(token=outstanding)
        except OutstandingToken.DoesNotExist:
            # If the token is not in OutstandingToken but session existed, we still mark session inactive
            pass
        except Exception as e:
            return Response({"error": f"Failed to revoke session: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({"success": "Device logged out successfully"}, status=status.HTTP_200_OK)


class LogoutAllOtherDevicesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from users.models import UserDeviceSession
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        
        current_jti = request.auth.get('refresh_jti') if request.auth else None
        if not current_jti:
            return Response({"error": "Current session not identified"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Get all other active sessions for this user
        other_sessions = UserDeviceSession.objects.filter(user=request.user, is_active=True).exclude(jti=current_jti)
        
        revoked_count = 0
        for session in other_sessions:
            session.is_active = False
            session.save()
            
            # Blacklist in SimpleJWT
            try:
                outstanding = OutstandingToken.objects.get(jti=session.jti, user=request.user)
                BlacklistedToken.objects.get_or_create(token=outstanding)
                revoked_count += 1
            except OutstandingToken.DoesNotExist:
                pass
                
        return Response({
            "success": "All other devices logged out successfully",
            "revoked_count": revoked_count
        }, status=status.HTTP_200_OK)