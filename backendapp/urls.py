from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomerViewSet, ProductViewSet, SaleViewSet,
    InvoiceViewSet, PaymentViewSet, receivables, csrf, login_view, logout_view, me,
    transactions_list, reports_dashboard, landing_summary, profile, change_password
)
router = DefaultRouter()
router.register(r"customers", CustomerViewSet)
router.register(r"products", ProductViewSet)
router.register(r"sales", SaleViewSet)
router.register(r"invoices", InvoiceViewSet)
router.register(r"payments", PaymentViewSet)
urlpatterns = [
    path("", include(router.urls)),
    path("receivables/", receivables, name="receivables"),
    path("transactions/", transactions_list, name="transactions"),
    path("reports/dashboard/", reports_dashboard, name="reports_dashboard"),
    path("landing-summary/", landing_summary, name="landing_summary"),
    path("profile/", profile, name="profile"),
    path("profile/password/", change_password, name="change_password"),
    path("auth/csrf/", csrf),
    path("auth/login/", login_view),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", logout_view),
    path("auth/me/", me),
]
