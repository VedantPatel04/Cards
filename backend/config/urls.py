from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from apps.users.views import is_Authenticated, register
from apps.uploads.views import upload_transactions

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('api/register/', register, name='register'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    path('api/isAuthenticated/', is_Authenticated, name='ping'),

    # Uploads
    path('api/upload/', upload_transactions, name='upload_transactions'),
]
