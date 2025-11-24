from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal  
from datetime import timedelta
import uuid
from apps.products.models import Product

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=200)
    capacity = models.CharField(max_length=100, blank=True, null=True) 
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
        """Count items that are low stock (0 < quantity <= reorder_threshold)"""
        from django.db.models import Q, F
        return self.stock_items.filter(
            Q(quantity__gt=0) & 
            Q(quantity__lte=F('product__reorder_threshold'))
        ).count()
    
    @property
    def out_of_stock_count(self):
        """Count items that are out of stock (quantity <= 0)"""
        return self.stock_items.filter(quantity__lte=0).count()

    @property
    def _capacity_numeric(self):
        """Extract numeric capacity from string field"""
        if not self.capacity:
            return 0
        try:
            # Extract numbers from capacity string (e.g., "1000 units" -> 1000)
            import re
            numbers = re.findall(r'\d+', self.capacity)
            return float(numbers[0]) if numbers else 0
        except (ValueError, IndexError):
            return 0
    
    @property
    def usage_percentage(self):
        capacity = self._capacity_numeric
        if capacity > 0:
            return (self.total_items / capacity) * 100
        return 0

class StockItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_items')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='stock_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Cost per unit in this stock item (for batch-specific costing)."
    )
    location = models.CharField(max_length=100, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    manufactured_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    procurement_status = models.CharField(max_length=20, choices=[
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('pending', 'Pending'),
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)  
    updated_at = models.DateTimeField(auto_now=True)      
    last_low_stock_alert = models.DateTimeField(null=True, blank=True)
    alert_cooldown_days = models.PositiveSmallIntegerField(default=1)
    ALERT_COOLDOWN_HOURS = 24

    @property
    def should_send_alert(self):
        """Check if we should send a low stock alert"""
        if not self.is_low_stock:
            return False
        
        if not self.last_low_stock_alert:
            return True
        return (timezone.now() - self.last_low_stock_alert) > timedelta(hours=24)
        
    def mark_alert_sent(self):
        """Mark that an alert has been sent"""
        self.last_low_stock_alert = timezone.now()  
        self.save(update_fields=['last_low_stock_alert'])
    
    @property
    def alert_recipients(self):
        """Get users who should receive alerts for this stock item"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        recipients = set()
        
        if self.warehouse.manager:
            recipients.add(self.warehouse.manager)
        
        inventory_users = User.objects.filter(
            groups__name__in=['Inventory Manager', 'Procurement Manager']
        )
        recipients.update(inventory_users)
        
        return list(recipients)
    
    class Meta:
        ordering = ['product__sku', 'batch_number']
        unique_together = ['product', 'warehouse', 'batch_number']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['location']),
            models.Index(fields=['notes']),
            models.Index(fields=['quantity']),
            models.Index(fields=['procurement_status']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['created_at', 'updated_at']),
        ]
    
    def __str__(self):
        return f"{self.product.sku} at {self.warehouse.code} (Batch: {self.batch_number or '-'})"

    def save(self, *args, **kwargs):
        if not self.pk and self.product.reorder_threshold == 0:
            if self.product.reorder_threshold > 0:
                self.reorder_threshold = self.product.reorder_threshold

        super().save(*args, **kwargs)

    @property
    def total_value(self):
        return self.quantity * self.unit_cost

    @property
    def effective_reorder_threshold(self):
        """Use product's reorder threshold"""
        return self.product.reorder_threshold or Decimal('0')

    @property
    def is_low_stock(self):
        return (
            self.quantity <= self.effective_reorder_threshold
            and self.quantity > 0
    )

    @property
    def usage_rate(self):
        """Calculate usage rate from recent transactions"""
        from django.db.models import Sum
        thirty_days_ago = timezone.now() - timedelta(days=30)
        total_used = self.transactions.filter(
            transaction_type='out',
            created_at__gte=thirty_days_ago
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        return total_used / Decimal('30.0')

    @property
    def forecast_reorder_date(self):
        """Forecast when reorder will be needed"""
        if self.usage_rate > 0 and self.quantity > 0:
            days_until_reorder = (self.quantity - self.effective_reorder_threshold) / self.usage_rate
            if days_until_reorder > 0:
                return timezone.now().date() + timedelta(days=float(days_until_reorder))
        return None 

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

# inventory/models.py - StockTransaction updates
class StockTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
        ('count', 'Stock Count'),
        ('quality', 'Quality Check'),
    )
    
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # For transfer transactions
    destination_warehouse = models.ForeignKey(
        'Warehouse', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='incoming_transfers'
    )
    
    # For adjustment tracking
    previous_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Quantity before adjustment"
    )
    new_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Quantity after adjustment"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stock_item', 'created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.stock_item.product.sku} - {self.get_transaction_type_display()} - {self.quantity}"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Set default reference if not provided
        if not self.reference:
            prefix = self.get_transaction_type_display().upper().replace(' ', '')
            self.reference = f"{prefix}-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
        
        # For adjustments, track quantity changes
        if self.transaction_type == 'adjustment' and is_new:
            self.previous_quantity = self.stock_item.quantity
            self.new_quantity = self.stock_item.quantity + self.quantity
        
        # Save the transaction first
        super().save(*args, **kwargs)
        
        # Update stock quantity after saving
        if is_new:
            self.update_stock_quantity()
    
    def update_stock_quantity(self):
        """Update stock item quantity based on transaction type"""
        stock_item = self.stock_item
        
        print(f"DEBUG: Updating stock for {stock_item.product.sku}, type: {self.transaction_type}, quantity: {self.quantity}")
        
        if self.transaction_type == 'in':
            stock_item.quantity += self.quantity
            print(f"DEBUG: Added {self.quantity}, new quantity: {stock_item.quantity}")
        elif self.transaction_type == 'out':
            if stock_item.quantity < self.quantity:
                raise ValidationError(
                    f"Insufficient stock. Available: {stock_item.quantity}, Required: {self.quantity}"
                )
            stock_item.quantity -= self.quantity
            print(f"DEBUG: Subtracted {self.quantity}, new quantity: {stock_item.quantity}")
        elif self.transaction_type == 'adjustment':
            new_quantity = stock_item.quantity + self.quantity
            if new_quantity < 0:
                raise ValidationError(
                    f"Adjustment would result in negative stock. Current: {stock_item.quantity}, Adjustment: {self.quantity}"
                )
            stock_item.quantity = new_quantity
            print(f"DEBUG: Adjusted by {self.quantity}, new quantity: {stock_item.quantity}")
        elif self.transaction_type == 'transfer':
            # For transfers, we only deduct from source
            # The destination stock will be handled in create_transfer_transaction
            if stock_item.quantity < abs(self.quantity):
                raise ValidationError(
                    f"Insufficient stock for transfer. Available: {stock_item.quantity}, Required: {abs(self.quantity)}"
                )
            stock_item.quantity += self.quantity  # quantity is negative for transfers
            print(f"DEBUG: Transfer deducted {abs(self.quantity)}, new quantity: {stock_item.quantity}")
        
        # Update the stock item
        stock_item.save(update_fields=['quantity', 'updated_at'])
        
        # For transfers, create corresponding transaction for destination
        if self.transaction_type == 'transfer' and self.destination_warehouse:
            self.create_transfer_transaction()
    
    def create_transfer_transaction(self):
        """Create corresponding transaction for transfer destination"""
        if self.transaction_type != 'transfer' or not self.destination_warehouse:
            return
        
        print(f"DEBUG: Creating transfer transaction for destination warehouse {self.destination_warehouse.code}")
        
        # Get or create destination stock item
        destination_stock, created = StockItem.objects.get_or_create(
            product=self.stock_item.product,
            warehouse=self.destination_warehouse,
            batch_number=self.stock_item.batch_number,
            defaults={
                'quantity': 0,
                'unit_cost': self.stock_item.unit_cost,
                'location': self.stock_item.location,
                'expiry_date': self.stock_item.expiry_date,
                'manufactured_date': self.stock_item.manufactured_date,
                'procurement_status': self.stock_item.procurement_status,
            }
        )
        
        print(f"DEBUG: Destination stock - created: {created}, current quantity: {destination_stock.quantity}")
        
        # Create incoming transfer transaction
        incoming_transaction = StockTransaction.objects.create(
            stock_item=destination_stock,
            transaction_type='in',
            quantity=abs(self.quantity),  # Positive quantity for destination
            reference=f"Transfer from {self.stock_item.warehouse.code}",
            notes=f"Transferred from {self.stock_item.warehouse.name}. {self.notes or ''}",
            created_by=self.created_by,
        )
        
        print(f"DEBUG: Created incoming transaction with quantity: {abs(self.quantity)}")
        print(f"DEBUG: Destination stock new quantity: {destination_stock.quantity}")
    
    @property
    def absolute_quantity_change(self):
        """Get absolute quantity change for display"""
        if self.transaction_type in ['in', 'adjustment'] and self.quantity > 0:
            return f"+{self.quantity}"
        elif self.transaction_type in ['out', 'adjustment'] and self.quantity < 0:
            return f"{self.quantity}"
        elif self.transaction_type == 'count':
            return f"→ {self.quantity}"
        return f"{self.quantity}"
    
    @property
    def is_positive(self):
        """Check if transaction increases stock"""
        return self.transaction_type in ['in'] or (
            self.transaction_type == 'adjustment' and self.quantity > 0
        )

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
    
    order_number = models.CharField(max_length=50, unique=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='orders')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Order {self.order_number}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    def generate_order_number(self):
        prefix = "ORD"
        date_str = timezone.now().strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{date_str}-{unique_id}"
        
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
