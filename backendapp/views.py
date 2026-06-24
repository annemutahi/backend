from rest_framework import filters, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .models import Customer, Product, Sale, Invoice, Payment, SaleAuditLog
from .serializers import (
    CustomerSerializer, ProductSerializer, SaleSerializer,
    InvoiceSerializer, PaymentSerializer, TransactionSerializer,
    LandingSummarySerializer, ProfileSerializer, ProfileUpdateSerializer,
)
from django.contrib.auth import authenticate
from django.middleware.csrf import get_token
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Sum, Count, F, DecimalField
from django.utils import timezone
from datetime import timedelta
from .permissions import CanEditSales

@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    get_token(request)
    return Response({"detail": "ok"})

@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
    if not user:
        return Response({"detail": "Invalid credentials"}, status=400)
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "user": {"id": user.id, "username": user.username, "email": user.email},
    })

@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    return Response(status=204)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({
        "id": u.id, "username": u.username, "email": u.email, 
        "is_staff": u.is_staff, "is_superuser": u.is_superuser,
    })

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.prefetch_related("invoices", "sales").order_by("name")
    serializer_class = CustomerSerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by("category", "name")
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "category"]
    ordering_fields = ["name", "category", "unit_price", "stock", "created_at"]
    ordering = ["category", "name"]

class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.select_related("customer").prefetch_related("items__product").order_by("-sale_date")
    # serializer_class = SaleSerializer
    # class SaleViewSet(viewsets.ModelViewSet):
    # queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [CanEditSales]
    http_method_names = ["get", "post", "put", "patch", "delete"]

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related("customer", "sale").prefetch_related("sale__items__product", "payments").order_by("-issue_date")
    serializer_class = InvoiceSerializer

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("invoice__customer").order_by("-payment_date")
    serializer_class = PaymentSerializer
@api_view(["GET"])
@permission_classes([AllowAny])
def receivables(request):
    """Aggregate outstanding balances per customer."""
    data = []
    for c in Customer.objects.all():
        balance = sum((inv.outstanding_balance for inv in c.invoices.all()), 0)
        if balance > 0:
            data.append({
                "customer_id": c.id,
                "customer_name": c.name,
                "customer_type": c.customer_type,
                "outstanding_balance": balance,
                "credit_limit": c.credit_limit,
            })
    return Response(data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transactions_list(request):
    """Get combined Sales and Payments as transactions."""
    sales = Sale.objects.select_related("customer").prefetch_related("items__product").values(
        "id", "customer__name", "customer__id", "payment_type", "total_amount", "sale_date"
    )
    
    payments = Payment.objects.select_related("invoice__customer").values(
        "id", "invoice__customer__name", "invoice__customer__id", "method", "amount", "payment_date"
    )
    
    sales_data = [{
        "id": s["id"],
        "type": "sale",
        "customer_id": s["customer__id"],
        "customer_name": s["customer__name"],
        "amount": s["total_amount"],
        "payment_type_or_method": s["payment_type"],
        "date": s["sale_date"],
    } for s in sales]
    
    payments_data = [{
        "id": p["id"],
        "type": "payment",
        "customer_id": p["invoice__customer__id"],
        "customer_name": p["invoice__customer__name"],
        "amount": p["amount"],
        "payment_type_or_method": p["method"],
        "date": p["payment_date"],
    } for p in payments]
    
    transactions = sales_data + payments_data
    transactions.sort(key=lambda x: x["date"], reverse=True)
    return Response(transactions)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_dashboard(request):
    """Computed dashboard views and KPIs."""
    # Summary statistics
    total_customers = Customer.objects.count()
    total_sales = Sale.objects.aggregate(total=Sum("total_amount"))["total"] or 0
    total_payments = Payment.objects.aggregate(total=Sum("amount"))["total"] or 0
    total_outstanding = Invoice.objects.aggregate(
        total=Sum(F("total_amount") - F("amount_paid"), output_field=DecimalField())
    )["total"] or 0
    
    # Sales by period (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_sales = Sale.objects.filter(sale_date__gte=thirty_days_ago).aggregate(
        total=Sum("total_amount"),
        count=Count("id")
    )
    
    # Invoice status breakdown
    invoice_status = Invoice.objects.values("status").annotate(count=Count("id"), total=Sum("total_amount"))
    
    # Top customers by sales
    top_customers = Customer.objects.annotate(
        total_sales=Sum("sales__total_amount"),
        outstanding=Sum("invoices__total_amount") - Sum("invoices__amount_paid")
    ).filter(total_sales__isnull=False).order_by("-total_sales")[:10]
    
    # Outstanding invoices
    outstanding_invoices = Invoice.objects.filter(
        status__in=[Invoice.SENT, Invoice.PARTIAL, Invoice.OVERDUE]
    ).select_related("customer").values(
        "id", "invoice_number", "customer__name", "total_amount", "amount_paid", "due_date", "status"
    )
    
    return Response({
        "summary": {
            "total_customers": total_customers,
            "total_sales": float(total_sales),
            "total_payments": float(total_payments),
            "total_outstanding": float(total_outstanding),
        },
        "recent_sales": {
            "total": float(recent_sales["total"] or 0),
            "count": recent_sales["count"],
            "period": "last_30_days"
        },
        "invoice_status": [
            {
                "status": item["status"],
                "count": item["count"],
                "total": float(item["total"] or 0)
            } for item in invoice_status
        ],
        "top_customers": [
            {
                "id": c.id,
                "name": c.name,
                "total_sales": float(c.total_sales or 0),
                "outstanding": float(c.outstanding or 0),
                "customer_type": c.customer_type,
            } for c in top_customers
        ],
        "outstanding_invoices": [
            {
                "id": inv["id"],
                "invoice_number": inv["invoice_number"],
                "customer_name": inv["customer__name"],
                "total_amount": float(inv["total_amount"]),
                "amount_paid": float(inv["amount_paid"]),
                "outstanding": float(inv["total_amount"] - inv["amount_paid"]),
                "due_date": inv["due_date"],
                "status": inv["status"],
            } for inv in outstanding_invoices
        ]
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def landing_summary(request):
    """Landing page summaries for monthly sales, payments, credit, and due invoices."""
    today = timezone.localdate()
    current_month_sales = Sale.objects.filter(
        sale_date__year=today.year,
        sale_date__month=today.month,
    ).aggregate(total=Sum("total_amount"), count=Count("id"))

    current_month_payments = Payment.objects.filter(
        payment_date__year=today.year,
        payment_date__month=today.month,
    ).aggregate(total=Sum("amount"), count=Count("id"))

    total_credit_limit = Customer.objects.aggregate(total=Sum("credit_limit"))["total"] or 0
    total_outstanding = Invoice.objects.aggregate(
        total=Sum(F("total_amount") - F("amount_paid"), output_field=DecimalField())
    )["total"] or 0
    available_credit = float(total_credit_limit - total_outstanding) if total_credit_limit else 0

    due_soon_cutoff = today + timedelta(days=7)
    due_soon_qs = Invoice.objects.filter(
        due_date__range=(today, due_soon_cutoff),
        status__in=[Invoice.SENT, Invoice.PARTIAL],
    ).select_related("customer")
    due_soon_stats = due_soon_qs.aggregate(
        total=Sum(F("total_amount") - F("amount_paid"), output_field=DecimalField()),
        count=Count("id"),
    )

    due_soon_invoices = [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "customer_name": inv.customer.name,
            "due_date": inv.due_date,
            "outstanding": float(inv.outstanding_balance),
            "status": inv.status,
        }
        for inv in due_soon_qs.order_by("due_date")
    ]

    response_data = {
        "monthly_sales": {
            "total": float(current_month_sales["total"] or 0),
            "count": current_month_sales["count"],
            "period": "current_month",
        },
        "cards": {
            "payments_received": {
                "total": float(current_month_payments["total"] or 0),
                "count": current_month_payments["count"],
            },
            "total_credit_limit": float(total_credit_limit),
            "total_outstanding_credit": float(total_outstanding),
            "available_credit": float(max(total_credit_limit - total_outstanding, 0)),
            "payments_due_soon": {
                "count": due_soon_stats["count"],
                "amount": float(due_soon_stats["total"] or 0),
                "due_by": due_soon_cutoff,
            },
        },
        "payments_due_soon_invoices": due_soon_invoices,
    }

    serializer = LandingSummarySerializer(data=response_data)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.data)

@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def profile(request):
    """Retrieve or update the authenticated user profile."""
    user = request.user
    if request.method == "PUT":
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        for field in ("first_name", "last_name", "email"):
            if field in validated:
                setattr(user, field, validated[field])

        password = validated.get("password")
        if password:
            user.set_password(password)

        if serializer.validated_data:
            user.save()

    response_serializer = ProfileSerializer(user)
    return Response(response_serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change the authenticated user's password."""
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")

    if not current_password or not new_password:
        return Response({"detail": "current_password and new_password are required."}, status=400)
    if not user.check_password(current_password):
        return Response({"detail": "Current password is incorrect."}, status=400)

    user.set_password(new_password)
    user.save()
    return Response({"detail": "Password updated."})

def perform_update(self, serializer):
    before = SaleSerializer(serializer.instance).data
    sale = serializer.save()
    SaleAuditLog.objects.create(
        sale=sale, user=self.request.user, action="updated",
        before=before, after=SaleSerializer(sale).data,
    )

def perform_destroy(self, instance):
    before = SaleSerializer(instance).data
    SaleAuditLog.objects.create(
        sale=None, user=self.request.user, action="deleted", before=before,
    )
    instance.delete()