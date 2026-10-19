from django.urls import path

from .grid_views import FeeGridListAPIView, FeeGridExportAPIView
from .receipt_views import (
    ReceiptSettingsAPIView,
    FeeReceiptListCreateAPIView,
    FeeReceiptDetailAPIView,
    FeeReceiptFromPaymentAPIView,
    FeeReceiptVoidAPIView,
    FeeReceiptCalculatePreviewAPIView,
    FeeReceiptSendEmailAPIView,
    PublicReceiptVerifyAPIView,
)
from .views import (
    FeeAnalyticsOverviewAPIView,
    FeeStudent360APIView,
    FeePlanTemplateListCreateAPIView,
    FeePlanTemplateDetailAPIView,
    FeeAccountListCreateAPIView,
    FeeAccountDetailAPIView,
    FeeInstallmentListCreateAPIView,
    FeeInstallmentDetailAPIView,
    FeePaymentListCreateAPIView,
    FeePaymentDetailAPIView,
    FeeAdjustmentListCreateAPIView,
    FeeRestructureAPIView,
    FeeSummaryAPIView,
    FeeCatalogSeedAPIView,
    FeeStudentsAPIView,
    ExportAdmissionsReportAPIView,
    FeePolicyAPIView,
)

urlpatterns = [
    path('fees/policy/', FeePolicyAPIView.as_view(), name='fee-policy'),
    path('fees/catalog/', FeePlanTemplateListCreateAPIView.as_view(), name='fee-catalog-list-create'),
    path('fees/catalog/<int:pk>/', FeePlanTemplateDetailAPIView.as_view(), name='fee-catalog-detail'),
    path('fees/catalog/seed/', FeeCatalogSeedAPIView.as_view(), name='fee-catalog-seed'),
    path('fees/accounts/', FeeAccountListCreateAPIView.as_view(), name='fee-account-list-create'),
    path('fees/accounts/<int:pk>/', FeeAccountDetailAPIView.as_view(), name='fee-account-detail'),
    path('fees/accounts/<int:account_pk>/installments/', FeeInstallmentListCreateAPIView.as_view(), name='fee-installment-list-create'),
    path('fees/accounts/<int:account_pk>/installments/<int:pk>/', FeeInstallmentDetailAPIView.as_view(), name='fee-installment-detail'),
    path('fees/accounts/<int:account_pk>/payments/', FeePaymentListCreateAPIView.as_view(), name='fee-payment-list-create'),
    path('fees/accounts/<int:account_pk>/payments/<int:pk>/', FeePaymentDetailAPIView.as_view(), name='fee-payment-detail'),
    path('fees/accounts/<int:account_pk>/adjustments/', FeeAdjustmentListCreateAPIView.as_view(), name='fee-adjustment-list-create'),
    path('fees/accounts/<int:pk>/restructure/', FeeRestructureAPIView.as_view(), name='fee-restructure'),
    path('fees/summary/', FeeSummaryAPIView.as_view(), name='fee-summary'),
    path('fees/students/', FeeStudentsAPIView.as_view(), name='fee-students'),
    path('fees/export/admissions/', ExportAdmissionsReportAPIView.as_view(), name='export-admissions-report'),

    path('fees/analytics/overview/', FeeAnalyticsOverviewAPIView.as_view(), name='fee-analytics-overview'),
    path('fees/analytics/student/<int:student_id>/', FeeStudent360APIView.as_view(), name='fee-student-360'),

    path('fees/grid/', FeeGridListAPIView.as_view(), name='fee-grid-list'),
    path('fees/grid/export/', FeeGridExportAPIView.as_view(), name='fee-grid-export'),

    # Digital Receipt & Invoice Studio Endpoints
    path('fees/receipt-settings/', ReceiptSettingsAPIView.as_view(), name='fee-receipt-settings'),
    path('fees/receipts/', FeeReceiptListCreateAPIView.as_view(), name='fee-receipt-list-create'),
    path('fees/receipts/calculate-preview/', FeeReceiptCalculatePreviewAPIView.as_view(), name='fee-receipt-calculate-preview'),
    path('fees/receipts/from-payment/<int:payment_id>/', FeeReceiptFromPaymentAPIView.as_view(), name='fee-receipt-from-payment'),
    path('fees/receipts/verify/<str:verification_token>/', PublicReceiptVerifyAPIView.as_view(), name='fee-receipt-verify'),
    path('fees/receipts/<int:pk>/', FeeReceiptDetailAPIView.as_view(), name='fee-receipt-detail'),
    path('fees/receipts/<int:pk>/void/', FeeReceiptVoidAPIView.as_view(), name='fee-receipt-void'),
    path('fees/receipts/<int:pk>/send-email/', FeeReceiptSendEmailAPIView.as_view(), name='fee-receipt-send-email'),
]

