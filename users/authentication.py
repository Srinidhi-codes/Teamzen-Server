from rest_framework_simplejwt.authentication import JWTAuthentication

class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            raw_token = request.COOKIES.get("access_token")
        else:
            raw_token = self.get_raw_token(header)

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        
        # Check if the device session has been revoked
        refresh_jti = validated_token.get("refresh_jti")
        if refresh_jti:
            from users.models import UserDeviceSession
            from rest_framework.exceptions import AuthenticationFailed
            from django.utils import timezone
            
            session = UserDeviceSession.objects.filter(jti=refresh_jti).first()
            if session:
                if not session.is_active:
                    raise AuthenticationFailed("Session has been revoked.")
                
                # Throttle last_active updates to once every 60 seconds to optimize DB writes
                now = timezone.now()
                if not session.last_active or (now - session.last_active).total_seconds() > 60:
                    UserDeviceSession.objects.filter(id=session.id).update(last_active=now)
        
        return user, validated_token
