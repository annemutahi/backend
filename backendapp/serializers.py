from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import uuid
from .models import Customer, Product, Sale, SaleItem, Invoice, Payment

class CustomerSerializer(serializers.ModelSerializer):
    outstanding_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    class Meta:
        model = Customer
        fields = "__all__"

class ProductSerializer(serializers.ModelSerializer):
    available_quantity = serializers.DecimalField(source="stock", max_digits=12, decimal_places=2, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "unit_price",
            "available_quantity",
            "unit",
            "description",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def to_internal_value(self, data):
        # Accept common camelCase keys from frontend (e.g. productName, unitPrice)
        if isinstance(data, dict):
            mapped = dict(data)
            if "productName" in data and "name" not in data:
                mapped["name"] = data.get("productName")
            if "unitPrice" in data and "unit_price" not in data:
                mapped["unit_price"] = data.get("unitPrice")
            if "availableQuantity" in data and "stock" not in data and "available_quantity" not in data:
                # Map common camelCase to source field
                mapped["stock"] = data.get("availableQuantity")
            # also allow available_quantity through snake_case
            if "available_quantity" in data and "stock" not in data:
                mapped["stock"] = data.get("available_quantity")
            data = mapped
        return super().to_internal_value(data)

    def validate_unit_price(self, value):
        if value is None:
            raise serializers.ValidationError("unit_price is required.")
        if value < 0:
            raise serializers.ValidationError("unit_price must be non-negative.")
        return value

class SaleItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "quantity", "unit_price", "line_total"]

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    class Meta:
        model = Sale
        fields = ["id", "customer", "customer_name", "payment_type", "total_amount",
                  "sale_date", "notes", "items"]
        read_only_fields = ["total_amount"]
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        sale = Sale.objects.create(**validated_data)
        total = 0
        for item in items_data:
            unit_price = item.get("unit_price") or item["product"].unit_price
            SaleItem.objects.create(sale=sale, product=item["product"],
                                    quantity=item["quantity"], unit_price=unit_price)
            total += item["quantity"] * unit_price
        sale.total_amount = total
        sale.save(update_fields=["total_amount"])
        # Auto-generate invoice
        Invoice.objects.create(
            invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
            customer=sale.customer,
            sale=sale,
            due_date=timezone.now().date() + timedelta(days=30),
            total_amount=total,
            amount_paid=total if sale.payment_type == Sale.CASH else 0,
            status=Invoice.PAID if sale.payment_type == Sale.CASH else Invoice.SENT,
        )
        return sale

class InvoiceSerializer(serializers.ModelSerializer):
    outstanding_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    class Meta:
        model = Invoice
        fields = "__all__"

class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    class Meta:
        model = Payment
        fields = "__all__"

class TransactionSerializer(serializers.Serializer):
    """Unified serializer for Sales and Payments as transactions."""
    id = serializers.IntegerField()
    type = serializers.CharField()
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateTimeField()
    payment_type_or_method = serializers.CharField(required=False)
    
    class Meta:
        fields = ["id", "type", "customer_id", "customer_name", "amount", "date", "payment_type_or_method"]

class PaymentsCardSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    count = serializers.IntegerField()

class PaymentsDueSoonSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    due_by = serializers.DateField()

class LandingSummaryCardsSerializer(serializers.Serializer):
    payments_received = PaymentsCardSerializer()
    total_credit_limit = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_outstanding_credit = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_credit = serializers.DecimalField(max_digits=12, decimal_places=2)
    payments_due_soon = PaymentsDueSoonSerializer()

class MonthlySalesSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    count = serializers.IntegerField()
    period = serializers.CharField()

class LandingSummaryInvoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    customer_name = serializers.CharField()
    due_date = serializers.DateField()
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()

class LandingSummarySerializer(serializers.Serializer):
    monthly_sales = MonthlySalesSerializer()
    cards = LandingSummaryCardsSerializer()
    payments_due_soon_invoices = LandingSummaryInvoiceSerializer(many=True)

class ProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

class ProfileUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True)

    def validate_password(self, value):
        if value and len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value