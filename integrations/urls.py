from django.urls import path

from integrations.views import (
    GoogleCalendarCallbackView,
    GoogleCalendarConnectView,
    GoogleCalendarDisconnectView,
    GoogleCalendarStatusView,
)

urlpatterns = [
    path(
        "google/calendar/status/",
        GoogleCalendarStatusView.as_view(),
        name="gcal_status",
    ),
    path(
        "google/calendar/connect/",
        GoogleCalendarConnectView.as_view(),
        name="gcal_connect",
    ),
    path(
        "google/calendar/callback/",
        GoogleCalendarCallbackView.as_view(),
        name="gcal_callback",
    ),
    path(
        "google/calendar/disconnect/",
        GoogleCalendarDisconnectView.as_view(),
        name="gcal_disconnect",
    ),
]
