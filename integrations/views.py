"""Google Calendar OAuth + status API (Sequence 6)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from integrations import google_calendar as gcal
from integrations.models import GoogleCalendarConnection

logger = logging.getLogger(__name__)


class GoogleCalendarStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        conn = GoogleCalendarConnection.objects.filter(user=request.user).first()
        return JsonResponse(
            {
                "configured": gcal.is_configured(),
                "connected": bool(conn),
                "calendar_id": conn.calendar_id if conn else None,
                "connected_at": conn.connected_at.isoformat() if conn else None,
            }
        )


class GoogleCalendarConnectView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not gcal.is_configured():
            return JsonResponse(
                {"error": "Google Calendar is not configured on this server"},
                status=503,
            )
        try:
            url = gcal.build_authorize_url(request.user.id)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        return HttpResponseRedirect(url)


@method_decorator(csrf_exempt, name="dispatch")
class GoogleCalendarCallbackView(View):
    """OAuth redirect target — no JWT; uses signed state cache."""

    def get(self, request):
        frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        profile_url = f"{frontend}/profile?tab=integrations"
        error = request.GET.get("error")
        if error:
            return HttpResponseRedirect(f"{profile_url}&gcal=error")
        code = request.GET.get("code") or ""
        state = request.GET.get("state") or ""
        if not code or not state:
            return HttpResponseRedirect(f"{profile_url}&gcal=missing")
        try:
            gcal.exchange_code(code, state)
        except Exception:
            logger.exception("Google Calendar OAuth callback failed")
            return HttpResponseRedirect(f"{profile_url}&gcal=error")
        return HttpResponseRedirect(f"{profile_url}&gcal=connected")


class GoogleCalendarDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ok = gcal.disconnect_user(request.user.id)
        return JsonResponse({"disconnected": ok})
