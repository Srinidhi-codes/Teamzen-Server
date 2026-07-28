import uuid
import secrets
import pyotp
import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from users.serializers import UserSerializer
from users.models import UserLoginHistory
from users.views import get_client_ip, get_location_from_ip, get_cookie_settings
from notifications.email_backends import BrevoHTTPBackend
from temp_email.otp_email import get_otp_email_html

User = get_user_model()

def login_user_and_set_cookies(user, request):
    """Generates simple JWT tokens and sets access/refresh cookies on response"""
    from users.utils import create_user_session
    
    refresh = RefreshToken.for_user(user)
    access_token = refresh.access_token
    # Set the refresh token's JTI on the access token so we can map requests to the device session
    access_token['refresh_jti'] = refresh['jti']
    
    response = Response({
        'user': UserSerializer(user).data,
        'success': True,
        'access': str(access_token),
        'refresh': str(refresh),
    }, status=status.HTTP_200_OK)
    
    cookie_settings = get_cookie_settings()
    
    response.set_cookie(
        key="access_token",
        value=str(access_token),
        max_age=30 * 60,  # 30 minutes
        **cookie_settings
    )
    response.set_cookie(
        key="refresh_token",
        value=str(refresh),
        max_age=7 * 24 * 60 * 60,  # 7 days
        **cookie_settings
    )
    response.set_cookie(
        key="session_can_refresh",
        value="true",
        max_age=7 * 24 * 60 * 60,
        **get_cookie_settings(httponly=False)
    )
    
    # Log Login History and Create Active Device Session
    try:
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        ip = get_client_ip(request)
        
        # Log History
        UserLoginHistory.objects.create(
            user=user,
            ip_address=ip,
            location=get_location_from_ip(ip, lat=latitude, lon=longitude),
            latitude=latitude,
            longitude=longitude,
            user_agent=request.META.get('HTTP_USER_AGENT'),
            status='success'
        )
        
        # Create Active Device Session
        create_user_session(user, refresh, request)
    except Exception as e:
        print(f"Error logging login history or creating session: {e}")
        
    return response


class RequestOTPView(APIView):
    permission_classes = []
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = User.objects.get(email=email)
            if not user.is_active:
                return Response({"error": "This account is inactive"}, status=status.HTTP_400_BAD_REQUEST)
                
            # Generate 6-digit OTP
            otp = "".join(secrets.choice("0123456789") for _ in range(6))
            
            # Store OTP in cache (5 minutes TTL)
            cache.set(f"otp_{email}", otp, timeout=300)
            
            # Generate HTML email content using base design templates
            employee_name = f"{user.first_name} {user.last_name}".strip() or "Employee"
            html_content = get_otp_email_html(
                employee_name=employee_name,
                otp_code=otp,
                expiry_minutes=5,
                logo_url=""
            )
            
            # Send via custom Brevo HTTP backend to bypass outbound port restrictions
            email_msg = EmailMultiAlternatives(
                subject="Your Single Sign-On OTP 🔑",
                body=f"Hi {employee_name},\n\nYour security code is {otp}. It is valid for 5 minutes.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
                connection=BrevoHTTPBackend()
            )
            email_msg.attach_alternative(html_content, "text/html")
            email_msg.send(fail_silently=False)
            
            return Response({"success": True, "message": "OTP sent to your email"}, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            # Secure: don't leak account existence, return success message but do nothing
            return Response({"success": True, "message": "OTP sent to your email"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyOTPView(APIView):
    permission_classes = []
    
    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')
        
        if not email or not otp:
            return Response({"error": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        cached_otp = cache.get(f"otp_{email}")
        if not cached_otp or cached_otp != otp:
            return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Delete OTP from cache on verify attempt
        cache.delete(f"otp_{email}")
        
        try:
            user = User.objects.get(email=email)
            if not user.is_active:
                return Response({"error": "This account is inactive"}, status=status.HTTP_400_BAD_REQUEST)
                
            # If 2FA (TOTP) is enabled, return temp session token for step-2 validation
            if user.is_totp_enabled:
                temp_token = str(uuid.uuid4())
                cache.set(f"temp_totp_session_{temp_token}", user.id, timeout=300)
                return Response({
                    "totp_required": True,
                    "temp_token": temp_token
                }, status=status.HTTP_200_OK)
                
            return login_user_and_set_cookies(user, request)
            
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


class SetupTOTPView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        if user.is_totp_enabled:
            return Response({"error": "TOTP is already enabled"}, status=status.HTTP_400_BAD_REQUEST)
            
        # If secret does not exist, initialize it
        if not user.totp_secret:
            user.totp_secret = pyotp.random_base32()
            user.save()
            
        totp = pyotp.TOTP(user.totp_secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="Teamzen"
        )
        
        return Response({
            "secret": user.totp_secret,
            "provisioning_uri": provisioning_uri
        }, status=status.HTTP_200_OK)


class EnableTOTPView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        code = request.data.get('code')
        
        if not code:
            return Response({"error": "Verification code is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        if not user.totp_secret:
            return Response({"error": "Setup TOTP first before enabling"}, status=status.HTTP_400_BAD_REQUEST)
            
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code):
            user.is_totp_enabled = True
            user.save()
            return Response({
                "success": True,
                "message": "Two-factor authentication enabled successfully"
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid verification code"}, status=status.HTTP_400_BAD_REQUEST)


class DisableTOTPView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        code = request.data.get('code')
        
        if not code:
            return Response({"error": "Verification code is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code):
            user.is_totp_enabled = False
            user.totp_secret = None
            user.save()
            return Response({
                "success": True,
                "message": "Two-factor authentication disabled successfully"
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid verification code"}, status=status.HTTP_400_BAD_REQUEST)


class VerifyTOTPView(APIView):
    permission_classes = []
    
    def post(self, request):
        temp_token = request.data.get('temp_token')
        code = request.data.get('code')
        
        if not temp_token or not code:
            return Response({"error": "Session token and verification code are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        user_id = cache.get(f"temp_totp_session_{temp_token}")
        if not user_id:
            return Response({"error": "Session expired or invalid. Please log in again."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = User.objects.get(id=user_id)
            if not user.is_active:
                return Response({"error": "This account is inactive"}, status=status.HTTP_400_BAD_REQUEST)
                
            totp = pyotp.TOTP(user.totp_secret)
            if totp.verify(code):
                cache.delete(f"temp_totp_session_{temp_token}")
                return login_user_and_set_cookies(user, request)
            else:
                return Response({"error": "Invalid verification code"}, status=status.HTTP_400_BAD_REQUEST)
                
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


class GoogleLoginView(APIView):
    permission_classes = []
    
    def post(self, request):
        id_token = request.data.get('id_token')
        if not id_token:
            return Response({"error": "ID token is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            google_response = requests.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}",
                timeout=5
            )
            
            if google_response.status_code != 200:
                return Response({"error": "Invalid Google token"}, status=status.HTTP_400_BAD_REQUEST)
                
            token_info = google_response.json()
            email = token_info.get('email')
            email_verified = token_info.get('email_verified')
            
            if not email:
                return Response({"error": "Google account email is missing"}, status=status.HTTP_400_BAD_REQUEST)
                
            if str(email_verified).lower() != 'true':
                return Response({"error": "Your Google account email is not verified"}, status=status.HTTP_400_BAD_REQUEST)
                
            try:
                user = User.objects.get(email=email)
                if not user.is_active:
                    return Response({"error": "This account is inactive"}, status=status.HTTP_400_BAD_REQUEST)
                    
                # Check if 2FA is enabled
                if user.is_totp_enabled:
                    temp_token = str(uuid.uuid4())
                    cache.set(f"temp_totp_session_{temp_token}", user.id, timeout=300)
                    return Response({
                        "totp_required": True,
                        "temp_token": temp_token
                    }, status=status.HTTP_200_OK)
                    
                return login_user_and_set_cookies(user, request)
                
            except User.DoesNotExist:
                return Response({
                    "error": "Google Sign-In is only allowed for registered employees. Please contact your HR department to register your email first."
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Failed to reach Google verification server: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)
