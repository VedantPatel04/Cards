from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from apps.users.views import is_Authenticated, register
from apps.users.wallet_views import wallet_delete, wallet_list_or_add
from apps.cards.views import catalog_list
from apps.uploads.views import upload_list, upload_reassign, upload_transactions
from apps.transactions.views import review_answer, review_queue, transaction_list

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('api/register/', register, name='register'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    path('api/isAuthenticated/', is_Authenticated, name='ping'),

    # Catalog + wallet
    path('api/cards/', catalog_list, name='catalog_list'),
    path('api/wallet/', wallet_list_or_add, name='wallet'),
    path('api/wallet/<int:wallet_id>/', wallet_delete, name='wallet_delete'),

    # Uploads
    path('api/upload/', upload_transactions, name='upload_transactions'),
    path('api/uploads/', upload_list, name='upload_list'),
    path('api/uploads/<int:upload_id>/reassign/', upload_reassign, name='upload_reassign'),

    # Transactions + merchant review
    path('api/transactions/', transaction_list, name='transaction_list'),
    path('api/review/', review_queue, name='review_queue'),
    path('api/review/answer/', review_answer, name='review_answer'),
]
