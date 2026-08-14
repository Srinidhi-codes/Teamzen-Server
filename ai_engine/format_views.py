from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status


FORMAT_PROMPTS = {
    "format": (
        "Improve clarity, grammar, and formatting of the text. "
        "Keep the original meaning and language. Return ONLY the revised text."
    ),
    "improve": (
        "Rewrite the text to be clearer, more polished, and professional while keeping the meaning. "
        "Return ONLY the revised text."
    ),
    "shorten": (
        "Shorten the text while preserving key points. Return ONLY the revised text."
    ),
    "professional": (
        "Rewrite the text in a professional workplace tone. Return ONLY the revised text."
    ),
    "friendly": (
        "Rewrite the text in a friendly, approachable tone. Return ONLY the revised text."
    ),
}


class FormatTextView(APIView):
    """Lightweight AI rewrite for textarea suggestions (no chat history / tools)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = (request.data.get("text") or "").strip()
        mode = (request.data.get("mode") or "improve").strip().lower()
        if not text:
            return Response({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)
        if len(text) > 8000:
            return Response({"error": "text is too long (max 8000 chars)"}, status=status.HTTP_400_BAD_REQUEST)
        if mode not in FORMAT_PROMPTS:
            return Response(
                {"error": f"Invalid mode. Use one of: {', '.join(FORMAT_PROMPTS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        org = getattr(user, "organization", None)
        if getattr(user, "role", None) != "superadmin":
            from organizations.plan_entitlements import org_has_feature

            if not org_has_feature(org, "ai_assistant"):
                return Response(
                    {
                        "error": "AI write requires the Pro plan. Ask your admin to upgrade in Settings → Plan & billing.",
                        "code": "plan_required",
                        "required_plan": "pro",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        org_id = getattr(user, "organization_id", None)
        if not org_id:
            return Response({"error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from ai_engine.graph import get_llm
            from ai_engine.views import _normalize_llm_content
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(org_id)
            result = llm.invoke(
                [
                    SystemMessage(content=FORMAT_PROMPTS[mode]),
                    HumanMessage(content=text),
                ]
            )
            rewritten = _normalize_llm_content(getattr(result, "content", result)).strip()
            if not rewritten:
                return Response({"error": "AI returned empty text"}, status=status.HTTP_502_BAD_GATEWAY)
            return Response({"success": True, "text": rewritten, "mode": mode})
        except Exception as e:
            return Response(
                {"error": str(e) or "AI formatting failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
