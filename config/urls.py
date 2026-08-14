from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from strawberry.django.views import GraphQLView
from graphql_api.schema import schema
from graphql_utils.context import CustomContext

class CustomGraphQLView(GraphQLView):
    def get_context(self, request, response):
        return CustomContext(request, response)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from users.views import LoginView, CookieTokenRefreshView, RegisterView

from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("graphql/", csrf_exempt(CustomGraphQLView.as_view(schema=schema))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")), 
    path("api/auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/auth/register/", RegisterView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),  
    path("api/users/", include("users.urls")),
    path("api/ai/", include("ai_engine.urls")),
    path("api/bot/", include("bot_gateway.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("api/", include("organizations.urls")),
    path("api/", include("payroll.urls")),
    path("api/", include("attendance.urls")),
    path("api/", include("feedback.urls")),
    path("api/", include("onboarding.urls")),
    path("api/", include("documents.urls")),
    path("api/", include("offboarding.urls")),
    path("mcp/", include("mcp_oauth.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
