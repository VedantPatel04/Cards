from django.db import connection as _db_connection
from django.db import transaction as db_transaction

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView as _BaseTokenView

from config.api_schema import AccountDeleteSerializer
from services.merchant_cache import cache_delete_user

from .models import CustomUser
from .serializers import RegisterSerializer, UserSerializer
from .throttles import AuthRateThrottle

ACCOUNT_DELETE_CONFIRM = "DELETE"


class RegisterView(CreateAPIView):
    """Create a new user account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(_BaseTokenView):
    """Issue JWT access and refresh tokens for a valid username and password."""
    throttle_classes = [AuthRateThrottle]


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Report API and database availability."""
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
    """Confirm the request carries a valid JWT."""
    return Response({"message": "Authenticated."}, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        responses={200: UserSerializer},
        description="Return the signed-in user's profile.",
    ),
    delete=extend_schema(
        request=AccountDeleteSerializer,
        responses={204: None, 400: dict},
        description=(
            "Permanently delete the signed-in account and owned data "
            "after password confirmation."
        ),
    ),
)
@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def account_view(request):
    if request.method == "GET":
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)
    return _account_delete(request)


def _account_delete(request):
    password = request.data.get("password")
    confirm = str(request.data.get("confirm") or "").strip()

    if confirm != ACCOUNT_DELETE_CONFIRM:
        return Response(
            {"detail": f'confirm must be exactly "{ACCOUNT_DELETE_CONFIRM}".'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not password or not request.user.check_password(password):
        return Response(
            {"detail": "Password is incorrect."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    # Refuse to wipe the last remaining superuser via the API.
    if user.is_superuser and not CustomUser.objects.filter(
        is_superuser=True
    ).exclude(pk=user.pk).exists():
        return Response(
            {
                "detail": (
                    "Cannot delete the last superuser account. "
                    "Create another superuser first."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_id = user.pk
    with db_transaction.atomic():
        user.delete()

    cache_delete_user(user_id)
    return Response(status=status.HTTP_204_NO_CONTENT)