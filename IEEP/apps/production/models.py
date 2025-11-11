# production/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.products.models import Product, BOM
from apps.maintenance.models import Asset  

class ProductionOrder(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('qc_pending', 'QC Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    order_number = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    bom = models.ForeignKey('products.BOM', on_delete=models.PROTECT)
    planned_quantity = models.DecimalField(max_digits=10, decimal_places=4)
    actual_quantity = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    expected_yield = models.DecimalField(max_digits=5, decimal_places=2, default=95.0)
    actual_yield = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    scrap_quantity = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    assigned_machine = models.ForeignKey('maintenance.Asset', on_delete=models.SET_NULL, null=True)  # Updated to Asset
    assigned_operator = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='created_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['status']),
            models.Index(fields=['scheduled_start', 'scheduled_end']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.product.sku}"

class WorkOrder(models.Model):
    STATUS_CHOICES = (
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('qc_pending', 'QC Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    order_number = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE)
    planned_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    actual_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    scrap_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Scheduling
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    
    # Resources - Updated to Asset
    assigned_machine = models.ForeignKey('maintenance.Asset', on_delete=models.SET_NULL, null=True, blank=True)  # Updated
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders')
    
    # QC
    qc_passed = models.BooleanField(null=True, blank=True)
    qc_notes = models.TextField(blank=True, null=True)
    
    # Tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_work_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.order_number} - {self.product.sku}"
    
    @property
    def actual_yield(self):
        if self.actual_quantity and self.planned_quantity and self.planned_quantity > 0:
            return (self.actual_quantity / self.planned_quantity) * 100
        return 0
    
    @property
    def completion_percentage(self):
        if self.actual_quantity and self.planned_quantity and self.planned_quantity > 0:
            return min((self.actual_quantity / self.planned_quantity) * 100, 100)
        return 0
    
    @property
    def is_behind_schedule(self):
        from django.utils import timezone
        if self.scheduled_end and self.status in ['planned', 'in_progress']:
            return timezone.now() > self.scheduled_end
        return False

class ProductionStep(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    expected_duration = models.DurationField(null=True, blank=True)
    actual_duration = models.DurationField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['step_number']
        unique_together = ['work_order', 'step_number']
    
    def __str__(self):
        return f"{self.work_order.order_number} - Step {self.step_number}: {self.name}"

class ProductionLog(models.Model):
    ACTION_CHOICES = (
        ('start', 'Start Production'),
        ('stop', 'Stop Production'),
        ('pause', 'Pause Production'),
        ('resume', 'Resume Production'),
        ('complete', 'Complete Production'),
        ('qc_check', 'QC Check'),
        ('material_issue', 'Material Issue'),
        ('downtime', 'Downtime'),
        ('yield_update', 'Yield Update'),
    )
    
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='production_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity_scrap = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.work_order.order_number} - {self.get_action_display()}"

class ProductionOrderItem(models.Model):
    """
    Line item for ProductionOrder – tracks actual material consumption.
    """
    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    bom_component = models.ForeignKey(
        'products.BOMComponent',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT
    )
    planned_quantity = models.DecimalField(max_digits=12, decimal_places=4)
    actual_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit_of_measure = models.CharField(max_length=20)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ['production_order', 'product']
        ordering = ['product__sku']

    def __str__(self):
        return f"{self.product.sku} × {self.planned_quantity}"

    @property
    def variance(self):
        return self.actual_quantity - self.planned_quantity

    @property
    def variance_percentage(self):
        if self.planned_quantity > 0:
            return round((self.variance / self.planned_quantity) * 100, 2)
        return 0
        
class MaterialIssue(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='material_issues')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-issued_at']
    
    def __str__(self):
        return f"{self.work_order.order_number} - {self.product.sku}"

class DowntimeLog(models.Model):
    DOWNTIME_TYPES = (
        ('planned', 'Planned Maintenance'),
        ('unplanned', 'Unplanned Breakdown'),
        ('setup', 'Setup/Changeover'),
        ('material_wait', 'Material Waiting'),
        ('operator_wait', 'Operator Waiting'),
        ('other', 'Other'),
    )
    
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='downtime_logs', null=True, blank=True)
    machine = models.ForeignKey('maintenance.Asset', on_delete=models.CASCADE)  # Updated to Asset
    downtime_type = models.CharField(max_length=20, choices=DOWNTIME_TYPES)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    reason = models.TextField()
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.machine.asset_code} - {self.get_downtime_type_display()}"  # Updated to asset_code
    
    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            self.duration = self.end_time - self.start_time
        super().save(*args, **kwargs)

class MaterialConsumption(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='material_consumption')
    material_sku = models.CharField(max_length=100)
    material_name = models.CharField(max_length=200)
    planned_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    actual_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_of_measure = models.CharField(max_length=20)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        ordering = ['material_sku']
    
    def __str__(self):
        return f"{self.work_order.order_number} - {self.material_name}"
    
    @property
    def variance(self):
        return self.actual_quantity - self.planned_quantity
    
    @property
    def variance_percentage(self):
        if self.planned_quantity > 0:
            return (self.variance / self.planned_quantity) * 100
        return 0
