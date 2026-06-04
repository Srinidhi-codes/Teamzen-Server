from django.urls import path, include
from rest_framework.routers import DefaultRouter
from users.views import (
    UserViewSet, RegisterView, LoginView, LogoutView,
    PasswordResetRequestView, PasswordResetConfirmView,
    UserDeviceSessionListView, LogoutDeviceView, LogoutAllOtherDevicesView
)
from users.auth_views import (
    RequestOTPView, VerifyOTPView, SetupTOTPView, 
    EnableTOTPView, DisableTOTPView, VerifyTOTPView, GoogleLoginView
)

router = DefaultRouter()
router.register(r'', UserViewSet, basename='users')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path("logout/", LogoutView.as_view(), name="logout"),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    
    # New Auth Routes
    path('auth/otp/send/', RequestOTPView.as_view(), name='request_otp'),
    path('auth/otp/verify/', VerifyOTPView.as_view(), name='verify_otp'),
    path('auth/totp/setup/', SetupTOTPView.as_view(), name='setup_totp'),
    path('auth/totp/enable/', EnableTOTPView.as_view(), name='enable_totp'),
    path('auth/totp/disable/', DisableTOTPView.as_view(), name='disable_totp'),
    path('auth/totp/verify/', VerifyTOTPView.as_view(), name='verify_totp'),
    path('auth/google/', GoogleLoginView.as_view(), name='google_login'),
    
    # Session Management Routes
    path('auth/sessions/', UserDeviceSessionListView.as_view(), name='active_sessions'),
    path('auth/sessions/logout-device/', LogoutDeviceView.as_view(), name='logout_device'),
    path('auth/sessions/logout-all-others/', LogoutAllOtherDevicesView.as_view(), name='logout_all_others'),
    
    path('', include(router.urls)),
]
