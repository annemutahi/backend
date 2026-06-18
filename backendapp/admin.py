from django.contrib import admin
from .models import Customer, Product, Sale, SaleItem, Invoice, Payment

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "payment_type", "total_amount", "sale_date")
    inlines = [SaleItemInline]

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "customer_type", "phone", "credit_limit")
    search_fields = ("name", "phone", "email")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "unit", "unit_price", "stock")

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "total_amount", "amount_paid", "status", "due_date")
    list_filter = ("status",)
    
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "method", "payment_date")