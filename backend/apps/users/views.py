from django.db import connection as _db_connection

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView as _BaseTokenView

from .serializers import RegisterSerializer, UserSerializer
from .throttles import AuthRateThrottle


class RegisterView(CreateAPIView):
    """Public signup. serializer_class powers the browsable HTML form fields."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(_BaseTokenView):
    """JWT token endpoint with IP-based rate limiting."""
    throttle_classes = [AuthRateThrottle]


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    try:
        _db_connection.ensure_connection()
        return Response({"status": "ok", "db": "ok"})
    except Exception:
        return Response(
            {"status": "error", "db": "error"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def is_Authenticated(request):
    return Response({"message": "Authenticated."}, status=status.HTTP_200_OK)