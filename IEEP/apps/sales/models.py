# sales/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Q
from decimal import Decimal
import uuid

class Customer(models.Model):
    CUSTOMER_TYPES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
        ('government', 'Government'),
    ]
    
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPES, default='company')
    code = models.CharField(max_length=50, unique=True, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_terms = models.PositiveIntegerField(default=30, help_text="Payment terms in days")
    is_active = models.BooleanField(default=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_customer_code()
        super().save(*args, **kwargs)
    
    def generate_customer_code(self):
        prefix = {
            'individual': 'IND',
            'company': 'COMP',
            'government': 'GOV'
        }.get(self.customer_type, 'CUST')
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{unique_id}"
    
    @property
    def total_outstanding_balance(self):
        try:
            outstanding_invoices = self.invoices.filter(
                status__in=['sent', 'overdue']
            )
            
            total_outstanding = Decimal('0.00')
            for invoice in outstanding_invoices:
                total_outstanding += (invoice.total_amount - invoice.paid_amount)
            
            return total_outstanding
        except Exception:
            return Decimal('0.00')
    
    @property
    def available_credit(self):
        try:
            return self.credit_limit - self.total_outstanding_balance
        except Exception:
            return self.credit_limit

class SalesInquiry(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Inventory Check'),
        ('approved', 'Approved - Available'),
        ('rejected', 'Rejected - Unavailable'),
        ('converted', 'Converted to Sale Order'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    inquiry_number = models.CharField(max_length=50, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='inquiries')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sales_inquiries')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    inquiry_date = models.DateTimeField(default=timezone.now)
    required_date = models.DateField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    notes = models.TextField(blank=True)
    
    # Response from inventory
    inventory_checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='checked_inquiries')
    inventory_response = models.TextField(blank=True)
    inventory_responded_at = models.DateTimeField(null=True, blank=True)
    
    # Financial information
    total_estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-inquiry_date']
        verbose_name_plural = "Sales inquiries"

    def __str__(self):
        return self.inquiry_number
    
    def save(self, *args, **kwargs):
        if not self.inquiry_number:
            self.inquiry_number = self.generate_inquiry_number()
        super().save(*args, **kwargs)
    
    def generate_inquiry_number(self):
        date_str = timezone.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"INQ-{date_str}-{unique_id}"
    
    def calculate_totals(self):
        """Calculate total estimated value from items"""
        total = Decimal('0.00')
        for item in self.items.all():
            total += item.estimated_value
        self.total_estimated_value = total
    
    @property
    def can_be_submitted(self):
        return self.status == 'draft' and self.items.exists()
    
    @property
    def can_be_approved(self):
        return (self.status == 'submitted' and 
                self.items.exists() and
                all(item.is_available for item in self.items.all()))
    
    @property
    def can_be_converted(self):
        return self.status == 'approved' and not hasattr(self, 'sale_order')

class SalesInquiryItem(models.Model):
    inquiry = models.ForeignKey(SalesInquiry, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Inventory response fields
    is_available = models.BooleanField(default=False)
    available_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    suggested_warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.SET_NULL, null=True, blank=True)
    suggested_stock_item = models.ForeignKey('inventory.StockItem', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ['inquiry', 'product']
    
    def __str__(self):
        return f"{self.inquiry.inquiry_number} - {self.product.sku}"
    
    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
    
    @property
    def estimated_value(self):
        price = self.unit_price or getattr(self.product, 'selling_price', Decimal('0.00'))
        return self.quantity * price

class SaleOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('invoiced', 'Invoiced'),
    ]
    
    order_number = models.CharField(max_length=50, unique=True, editable=False)
    inquiry = models.OneToOneField(SalesInquiry, on_delete=models.PROTECT, null=True, blank=True, related_name='sale_order')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sale_orders')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateTimeField(default=timezone.now)
    expected_ship_date = models.DateField(null=True, blank=True)
    actual_ship_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    
    # Financial fields
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.10)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return self.order_number
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        date_str = timezone.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"SO-{date_str}-{unique_id}"
    
    def calculate_totals(self):
        items_total = Decimal('0.00')
        total_discount = Decimal('0.00')
        
        for item in self.items.all():
            items_total += item.total_before_discount
            total_discount += item.discount_amount
        
        self.total_amount = items_total
        self.discount_amount = total_discount
        self.tax_amount = (items_total - total_discount) * self.tax_rate
        self.grand_total = items_total - total_discount + self.tax_amount
    
    @property
    def can_be_confirmed(self):
        return (self.status == 'draft' and 
                self.items.exists() and
                all(item.stock_item is not None for item in self.items.all()))

class SaleOrderItem(models.Model):
    sale_order = models.ForeignKey(SaleOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stock_item = models.ForeignKey('inventory.StockItem', on_delete=models.PROTECT, null=True, blank=True)
    
    class Meta:
        unique_together = ['sale_order', 'product']
    
    def __str__(self):
        return f"{self.sale_order.order_number} - {self.product.sku}"
    
    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})
        if not (0 <= self.discount_percent <= 100):
            raise ValidationError({'discount_percent': 'Discount must be between 0 and 100 percent.'})
    
    @property
    def total_before_discount(self):
        return self.unit_price * self.quantity
    
    @property
    def discount_amount(self):
        return self.total_before_discount * (self.discount_percent / Decimal('100.00'))
    
    @property
    def total_price(self):
        return self.total_before_discount - self.discount_amount

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    sale_order = models.OneToOneField(SaleOrder, on_delete=models.PROTECT, related_name='invoice')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date']

    def __str__(self):
        return self.invoice_number
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)
    
    def generate_invoice_number(self):
        date_str = timezone.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"INV-{date_str}-{unique_id}"
    
    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount