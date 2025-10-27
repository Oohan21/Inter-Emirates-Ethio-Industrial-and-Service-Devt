# inventory/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.products.models import Product

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=200)
    capacity = models.CharField(max_length=100, blank=True, null=True)  # e.g., "1000 sq ft"
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    @property
    def total_items(self):
        return self.stock_items.count()
    
    @property
    def total_value(self):
        return sum(item.total_value for item in self.stock_items.all())
    
    @property
    def low_stock_count(self):
        return self.stock_items.filter(is_low_stock=True).count()
    
    @property
    def usage_percentage(self):
        if self.capacity and hasattr(self, '_capacity_numeric'):
            return (self.total_items / self._capacity_numeric) * 100
        return 0

class StockItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_items')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='stock_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    manufactured_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    procurement_status = models.CharField(max_length=20, choices=[
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('pending', 'Pending'),
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)  # Added
    updated_at = models.DateTimeField(auto_now=True)      # Added
    
    @property
    def total_value(self):
        return self.quantity * self.unit_cost if self.unit_cost else 0
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_threshold and self.quantity > 0
    
    @property
    def is_expired(self):
        return self.expiry_date and self.expiry_date < timezone.now().date()
    
    class Meta:
        ordering = ['product__sku', 'batch_number']
        unique_together = ['product', 'warehouse', 'batch_number']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['location']),
            models.Index(fields=['notes']),
            models.Index(fields=['quantity', 'reorder_threshold']),
            models.Index(fields=['procurement_status']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['created_at', 'updated_at']),  # Added for timestamp queries
        ]
    
    def __str__(self):
        return f"{self.product.sku} at {self.warehouse.code} (Batch: {self.batch_number or '-'})"
    
    def __str__(self):
        return f"{self.product.sku} at {self.warehouse.code} (Batch: {self.batch_number or '-'})"

    @property
    def total_value(self):
        return self.quantity * self.unit_cost

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_threshold

    @property
    def is_expired(self):
        if self.expiry_date:
            return timezone.now().date() > self.expiry_date
        return False

    def update_usage_rate(self):
        """Calculate average daily usage based on recent 'out' transactions."""
        from django.db.models import Sum
        from datetime import timedelta
        lookback_days = 30
        start_date = timezone.now() - timedelta(days=lookback_days)
        total_used = self.transactions.filter(
            transaction_type='out',
            created_at__gte=start_date
        ).aggregate(total=Sum('quantity'))['total'] or 0
        self.usage_rate = total_used / lookback_days if total_used else 0
        if self.usage_rate > 0:
            days_to_reorder = (self.quantity - self.reorder_threshold) / self.usage_rate
            self.forecast_reorder_date = timezone.now().date() + timedelta(days=days_to_reorder)
        else:
            self.forecast_reorder_date = None
        self.save()

class StockTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
    )
    
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True)  # PO number, WO number, etc.
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.stock_item.product.sku} - {self.get_transaction_type_display()}"
    
    def save(self, *args, **kwargs):
        # Update stock item quantity based on transaction type
        if self.transaction_type == 'in':
            self.stock_item.quantity += self.quantity
        elif self.transaction_type == 'out':
            self.stock_item.quantity -= self.quantity
        elif self.transaction_type == 'adjustment':
            self.stock_item.quantity = self.quantity
        
        self.stock_item.save()
        super().save(*args, **kwargs)

class ReorderAlert(models.Model):
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='reorder_alerts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=(
            ('active', 'Active'),
            ('resolved', 'Resolved'),
            ('cancelled', 'Cancelled'),
        ),
        default='active'
    )
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reorder Alert for {self.stock_item.product.sku} at {self.stock_item.warehouse.code}"

class Order(models.Model):
    ORDER_STATUS = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )
    
    order_number = models.CharField(max_length=50, unique=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='orders')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Order {self.order_number}"
    
    def update_stock(self):
        """Update stock quantities when order is confirmed."""
        if self.status != 'confirmed':
            return
        
        for item in self.order_items.all():
            stock_item = StockItem.objects.filter(
                product=item.product,
                warehouse=self.warehouse,
                quantity__gte=item.quantity
            ).first()
            
            if not stock_item:
                raise ValueError(f"Insufficient stock for {item.product.sku} in warehouse {self.warehouse.code}")
            
            # Create stock transaction
            StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type='out',
                quantity=item.quantity,
                reference=f"Order {self.order_number}",
                notes=f"Stock deducted for order {self.order_number}",
                created_by=self.created_by
            )

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['order', 'product']
    
    def __str__(self):
        return f"{self.quantity} x {self.product.sku} for Order {self.order.order_number}"
