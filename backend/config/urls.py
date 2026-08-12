from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from apps.users.views import (
    LoginView,
    RegisterView,
    account_view,
    health_check,
    is_Authenticated,
)
from apps.users.wallet_views import wallet_delete, wallet_list_or_add
from apps.cards.views import catalog_list
from apps.uploads.views import upload_delete, upload_list, upload_reassign, upload_transactions
from apps.transactions.views import review_answer, review_queue, summary_view, transaction_list
from apps.recommendations.views import recommendations_view

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='token_obtain_pair', permanent=False)),
    path('admin/', admin.site.urls),

    # Auth
    path('api/health/', health_check, name='health_check'),
    path('api/register/', RegisterView.as_view(), name='register'),
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    path('api/isAuthenticated/', is_Authenticated, name='ping'),
    path('api/account/', account_view, name='account'),

    # Catalog + wallet
    path('api/cards/', catalog_list, name='catalog_list'),
    path('api/wallet/', wallet_list_or_add, name='wallet'),
    path('api/wallet/<int:wallet_id>/', wallet_delete, name='wallet_delete'),

    # Uploads
    path('api/upload/', upload_transactions, name='upload_transactions'),
    path('api/uploads/', upload_list, name='upload_list'),
    path('api/uploads/<int:upload_id>/', upload_delete, name='upload_delete'),
    path('api/uploads/<int:upload_id>/reassign/', upload_reassign, name='upload_reassign'),

    # Transactions + merchant review
    path('api/transactions/', transaction_list, name='transaction_list'),
    path('api/review/', review_queue, name='review_queue'),
    path('api/review/answer/', review_answer, name='review_answer'),

    # Spend summary + recommendations
    path('api/summary/', summary_view, name='spend_summary'),
    path('api/recommendations/', recommendations_view, name='recommendations'),
]

# Swagger UI — dev/local only
if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerUIView

    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerUIView.as_view(url_name='schema'), name='swagger-ui'),
    ]
