# maintenance/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class Asset(models.Model):
    ASSET_TYPES = (
        ('production_machine', 'Production Machine'),
        ('mixer', 'Mixer'),
        ('filler', 'Filler'),
        ('packaging', 'Packaging Line'),
        ('vehicle', 'Vehicle'),
        ('other', 'Other Equipment'),
    )
    
    STATUS_CHOICES = (
        ('operational', 'Operational'),
        ('idle', 'Idle'),
        ('maintenance', 'Under Maintenance'),
        ('broken', 'Broken'),
        ('retired', 'Retired'),
    )
    
    # Basic Information
    asset_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES)
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    installation_date = models.DateField(null=True, blank=True)
    
    # Status & Location
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idle')
    capacity = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    
    # Maintenance Tracking
    last_maintenance = models.DateField(null=True, blank=True)
    next_maintenance = models.DateField(null=True, blank=True)
    maintenance_interval_days = models.PositiveIntegerField(default=30)
    
    # Operational Data (for machines/equipment)
    total_operating_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_order = models.ForeignKey('production.WorkOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_asset')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['asset_code']
        indexes = [
            models.Index(fields=['asset_code']),
            models.Index(fields=['asset_type']),
            models.Index(fields=['status']),
            models.Index(fields=['next_maintenance']),
        ]
    
    def __str__(self):
        return f"{self.asset_code} - {self.name}"
    
    @property
    def is_available(self):
        return self.status in ['operational', 'idle']
    
    @property
    def requires_maintenance(self):
        """Check if asset requires maintenance"""
        if self.next_maintenance and self.next_maintenance <= timezone.now().date():
            return True
        return False
    
    @property
    def is_overdue_maintenance(self):
        """Check if maintenance is overdue"""
        if self.next_maintenance and self.next_maintenance < timezone.now().date():
            return True
        return False
    
    def check_and_notify_maintenance(self):
        """Check maintenance status and send notifications if needed"""
        if self.requires_maintenance:
            # Create notification for maintenance team
            from apps.notifications.utils import create_notification_safe
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Get maintenance team users
            maintenance_users = User.objects.filter(
                groups__name='maintenance_team'
            ) or User.objects.filter(is_staff=True)
            
            for user in maintenance_users:
                create_notification_safe(
                    user=user,
                    title=f"Maintenance Due: {self.asset_code}",
                    message=f"Asset {self.name} ({self.asset_code}) requires maintenance. Due date: {self.next_maintenance}",
                    notification_type='overdue_maintenance',
                    priority='high',
                    action_url=reverse('asset-detail', kwargs={'pk': self.pk})
                )
    
    @property
    def maintenance_status(self):
        if self.requires_maintenance:
            return "Due for Maintenance"
        elif self.status == 'maintenance':
            return "Under Maintenance"
        elif self.status == 'broken':
            return "Needs Repair"
        else:
            return "Operational"

class MaintenanceOrder(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    
    STATUS_CHOICES = (
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    
    MAINTENANCE_TYPES = (
        ('preventive', 'Preventive Maintenance'),
        ('corrective', 'Corrective Maintenance'),
        ('predictive', 'Predictive Maintenance'),
        ('breakdown', 'Breakdown Repair'),
    )
    
    order_number = models.CharField(max_length=50, unique=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='maintenance_orders')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPES, default='preventive')
    
    # Maintenance details
    description = models.TextField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='requested_maintenance')
    
    # Scheduling
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_duration = models.DurationField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    actual_duration = models.DurationField(null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_maintenance')
    
    # Completion
    work_performed = models.TextField(blank=True, null=True)
    parts_used = models.TextField(blank=True, null=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_maintenance')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.order_number} - {self.asset.asset_code}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        from datetime import datetime
        return f"MO-{datetime.now().strftime('%Y%m%d')}-{MaintenanceOrder.objects.count() + 1:04d}"

    @property
    def is_overdue(self):
        """Check if maintenance order is overdue"""
        if self.scheduled_date and self.scheduled_date < timezone.now().date():
            return self.status in ['requested', 'in_progress']
        return False
    
    @property
    def requires_attention(self):
        """Check if order requires immediate attention"""
        if self.status == 'requested' and self.priority in ['high', 'urgent']:
            return True
        if self.is_overdue:
            return True
        return False
    
    def check_and_notify_status(self):
        """Send notifications based on order status"""
        from apps.notifications.utils import create_notification_safe
        
        if self.requires_attention:
            # Notify assigned technician or maintenance team
            users_to_notify = []
            if self.assigned_to:
                users_to_notify.append(self.assigned_to)
            else:
                # Notify maintenance team if no one assigned
                from django.contrib.auth import get_user_model
                User = get_user_model()
                maintenance_users = User.objects.filter(groups__name='maintenance_team')
                users_to_notify.extend(maintenance_users)
            
            for user in users_to_notify:
                create_notification_safe(
                    user=user,
                    title=f"Maintenance Attention Required: {self.order_number}",
                    message=f"Maintenance order {self.order_number} for {self.asset.name} requires attention. Status: {self.get_status_display()}",
                    notification_type='maintenance_alert',
                    priority='high' if self.is_overdue else 'medium',
                    action_url=reverse('maintenance-order-detail', kwargs={'pk': self.pk})
                )

class MaintenanceLog(models.Model):
    ACTION_CHOICES = (
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('note_added', 'Note Added'),
        ('status_updated', 'Status Updated'),
    )
    
    maintenance_order = models.ForeignKey(MaintenanceOrder, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='created')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_logs')
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                 null=True, blank=True, related_name='technician_logs')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.maintenance_order.order_number} - {self.action}"
    
    def save(self, *args, **kwargs):
        # Auto-set technician to created_by if not specified
        if not self.technician:
            self.technician = self.created_by
        super().save(*args, **kwargs)

class SparePartUsage(models.Model):
    maintenance_order = models.ForeignKey(MaintenanceOrder, on_delete=models.CASCADE, related_name='spare_parts')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    stock_item = models.ForeignKey('inventory.StockItem', on_delete=models.SET_NULL, null=True)
    used_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.maintenance_order} - {self.product.sku}"
    
    @property
    def total_cost(self):
        return self.quantity * self.unit_cost