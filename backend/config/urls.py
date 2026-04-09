from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from apps.users.views import is_Authenticated

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(),name = 'token_obtain_pair'), # This endpoint is used to obtain an access token
    path('api/token/refresh/', TokenRefreshView.as_view(), name = 'token_refresh'),# This endpoint is used to refresh an access token
                                                                                   # Use "interceptors" to refresh automatically     
    
    # Token verification endpoint - returns status code
    path('api/token/verify/', TokenVerifyView.as_view(), name = 'token_verify'), # 'name' allows for quick url reference  in future code
    path('api/isAuthenticated/', is_Authenticated,name = "ping"),
]
