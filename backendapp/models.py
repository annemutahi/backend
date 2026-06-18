from django.db import models
from django.utils import timezone
import uuid
class Customer(models.Model):
    INDIVIDUAL = "individual"
    CORPORATE = "corporate"
    TYPE_CHOICES = [(INDIVIDUAL, "Individual"), (CORPORATE, "Corporate")]
    name = models.CharField(max_length=255)
    customer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=INDIVIDUAL)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name
    @property
    def outstanding_balance(self):
        return sum((inv.outstanding_balance for inv in self.invoices.all()), 0)
class Product(models.Model):
    # Keep a list of common categories for suggestions, but allow free-form categories
    COMMON_CATEGORY_CHOICES = [
        ("whole_chicken", "Whole Chicken"),
        ("cuts", "Cuts"),
        ("offal", "Offal"),
        ("eggs", "Eggs"),
    ]
    name = models.CharField(max_length=255)
    # Allow arbitrary category values so users can add custom categories.
    category = models.CharField(max_length=50)
    unit = models.CharField(max_length=30, default="kg")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name
class Sale(models.Model):
    CASH = "cash"
    CREDIT = "credit"
    PAYMENT_TYPE_CHOICES = [(CASH, "Cash"), (CREDIT, "Credit")]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default=CASH)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sale_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    def recalc_total(self):
        self.total_amount = sum(item.line_total for item in self.items.all())
        self.save(update_fields=["total_amount"])
class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    @property
    def line_total(self):
        return self.quantity * self.unit_price
class Invoice(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    STATUS_CHOICES = [
        (DRAFT, "Draft"), (SENT, "Sent"), (PARTIAL, "Partial"),
        (PAID, "Paid"), (OVERDUE, "Overdue"),
    ]
    invoice_number = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="invoice", null=True, blank=True)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    @property
    def outstanding_balance(self):
        return max(self.total_amount - self.amount_paid, 0)
    def refresh_status(self):
        if self.amount_paid <= 0:
            self.status = self.SENT
        elif self.amount_paid >= self.total_amount:
            self.status = self.PAID
        else:
            self.status = self.PARTIAL
        self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        # Ensure invoice_number exists for any created invoice
        if not self.invoice_number:
            # generate a short unique invoice id
            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
class Payment(models.Model):
    METHOD_CHOICES = [
        ("cash", "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("mobile_money", "Mobile Money"),
        ("cheque", "Cheque"),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="cash")
    payment_date = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # update invoice balance + status
        inv = self.invoice
        inv.amount_paid = sum(p.amount for p in inv.payments.all())
        inv.save(update_fields=["amount_paid"])
        inv.refresh_status()
