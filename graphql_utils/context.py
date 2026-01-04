from strawberry.django.context import StrawberryDjangoContext
from users.authentication import CookieJWTAuthentication

class CustomContext(StrawberryDjangoContext):
    def __init__(self, request, response):
        super().__init__(request=request, response=response)
        
        # Always try JWT authentication first. 
        # This ensures that if an access_token is present (e.g. from cookie), 
        # it takes precedence over any session-based auth (e.g. from Django Admin).
        auth = CookieJWTAuthentication()
        try:
            user_auth_tuple = auth.authenticate(request)
            if user_auth_tuple is not None:
                self.request.user, _ = user_auth_tuple
        except Exception:
            # If JWT auth fails (e.g. invalid token), we generally want to leave request.user as is 
            # (which might be AnonymousUser or a valid Session user), 
            # OR we might want to force it to AnonymousUser if we want strictly API behavior.
            # For now, let's allow fallback but priority is given to JWT.
            pass
