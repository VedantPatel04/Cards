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


@extend_schema_view(
    get=extend_schema(responses={200: UserSerializer}),
    delete=extend_schema(
        request=AccountDeleteSerializer,
        responses={204: None, 400: dict},
    ),
)
@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def account_view(request):
    """
    GET /api/account/ — profile for the signed-in user.
    DELETE /api/account/ — hard-delete the account and all owned data.

    DELETE body: {"password": "<current>", "confirm": "DELETE"}
    Cascades: wallet cards, uploads, transactions, merchant resolutions,
    and owned custom Card_Products. Also clears this user's Redis merchant cache.
    """
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