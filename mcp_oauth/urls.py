from django.urls import path

from mcp_oauth.api import DeviceCodeView, TokenView
from mcp_oauth.views import (
    AuthorizeRedirectView,
    ConnectHomeView,
    ConsentOAuthView,
    ConsentView,
    DeviceEntryView,
    LoginView,
    OTPView,
    TOTPView,
)

app_name = "mcp_oauth"

urlpatterns = [
    # Browser connect
    path("connect/", ConnectHomeView.as_view(), name="connect"),
    path("connect/login/", LoginView.as_view(), name="login"),
    path("connect/otp/", OTPView.as_view(), name="otp"),
    path("connect/totp/", TOTPView.as_view(), name="totp"),
    path("connect/device/", DeviceEntryView.as_view(), name="device"),
    path("connect/consent/", ConsentView.as_view(), name="consent"),
    path("connect/consent/oauth/", ConsentOAuthView.as_view(), name="consent_oauth"),
    # OAuth API
    path("oauth/device/code", DeviceCodeView.as_view(), name="device_code"),
    path("oauth/token", TokenView.as_view(), name="token"),
    path("oauth/authorize", AuthorizeRedirectView.as_view(), name="authorize"),
]
