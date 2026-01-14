from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from users.models import CustomUser
from rest_framework_simplejwt.views import TokenRefreshView
from users.serializers import UserSerializer, UserDetailSerializer, RegisterSerializer, LoginSerializer
from django.conf import settings

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

    @action(detail=False, methods=['put'])
    def update_profile(self, request):
        """Update user profile"""
        user = request.user
        serializer = UserDetailSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
        refresh = RefreshToken.for_user(user)
        response = Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

        # Set cookies
        response.set_cookie(
            key="access_token",
            value=str(refresh.access_token),
            httponly=True,
            secure=settings.DEBUG is False,
            samesite="Lax",
            max_age=30 * 60,  # 30 minutes
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=settings.DEBUG is False,
            samesite="Lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
        )

        return response


class LoginView(generics.GenericAPIView):
    """User login view"""
    serializer_class = LoginSerializer
    permission_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        response = Response({
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)
    
        # 🔐 Set cookies
        response.set_cookie(
            key="access_token",
            value=str(refresh.access_token),
            httponly=True,
            secure=settings.DEBUG is False,
            samesite="Lax",
            max_age=30 * 60,
        )

        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=settings.DEBUG is False,
            samesite="Lax",
            max_age=60 * 60 * 24 * 7,
        )

        return response


class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = []
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Prepare data for serializer (handle cookie if body is empty of refresh)
        data = request.data.copy() if hasattr(request.data, 'copy') else request.data
        if 'refresh' not in data and 'refresh_token' in request.COOKIES:
            data['refresh'] = request.COOKIES['refresh_token']
        
        serializer = self.get_serializer(data=data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response({'error': 'Invalid or missing refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            
        token_data = serializer.validated_data
        
        response = Response(token_data, status=status.HTTP_200_OK)
        
        if 'access' in token_data:
            response.set_cookie(
                key="access_token",
                value=token_data['access'],
                httponly=True,
                secure=settings.DEBUG is False,
                samesite="Lax",
                max_age=30 * 60,
            )
            
        if 'refresh' in token_data:
            response.set_cookie(
                key="refresh_token",
                value=token_data['refresh'],
                httponly=True,
                secure=settings.DEBUG is False,
                samesite="Lax",
                max_age=7 * 24 * 60 * 60,
            )
            
        return response

class LogoutView(APIView):
    def post(self, request):
        response = Response({"detail": "Logged out"}, status=200)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response
