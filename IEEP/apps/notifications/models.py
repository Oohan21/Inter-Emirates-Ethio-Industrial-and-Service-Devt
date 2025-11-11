# notifications/models.py
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone

class Notification(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    NOTIFICATION_TYPES = [
        ('low_stock', 'Low Stock Alert'),
        ('overdue_maintenance', 'Overdue Maintenance'),
        ('late_work_order', 'Late Work Order'),
        ('qc_failure', 'QC Failure'),
        ('system', 'System Notification'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Generic foreign key to link to any object
    related_object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('related_object_type', 'related_object_id')
    
    # Action URL for the notification
    action_url = models.CharField(max_length=500, blank=True, null=True)
    
    # Read status and timestamps
    is_read = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
    def mark_as_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
    
    def mark_as_sent(self):
        self.is_sent = True
        self.save()

class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Email preferences
    email_notifications = models.BooleanField(default=True)
    email_frequency = models.CharField(max_length=20, choices=[
        ('immediate', 'Immediate'),
        ('daily', 'Daily Digest'),
        ('weekly', 'Weekly Digest'),
    ], default='immediate')
    
    # Alert type preferences
    low_stock_alerts = models.BooleanField(default=True)
    maintenance_alerts = models.BooleanField(default=True)
    work_order_alerts = models.BooleanField(default=True)
    qc_alerts = models.BooleanField(default=True)
    system_alerts = models.BooleanField(default=True)
    
    # In-app notification preferences
    in_app_notifications = models.BooleanField(default=True)
    desktop_notifications = models.BooleanField(default=False)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences - {self.user.username}"

class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='managed_departments'  # CHANGED: Added related_name
    )
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

class Ticket(models.Model):
    TICKET_STATUS = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    TICKET_TYPES = [
        ('it_support', 'IT Support'),
        ('maintenance', 'Maintenance'),
        ('inventory', 'Inventory Issue'),
        ('production', 'Production Issue'),
        ('quality', 'Quality Concern'),
        ('hr', 'HR Related'),
        ('other', 'Other'),
    ]
    
    ticket_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    ticket_type = models.CharField(max_length=50, choices=TICKET_TYPES)
    status = models.CharField(max_length=20, choices=TICKET_STATUS, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_LEVELS, default='medium')
    
    # Assignment and tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='created_tickets'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True, 
        related_name='assigned_tickets'
    )
    assigned_department = models.ForeignKey(
        'Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='department_tickets'  # CHANGED: Added related_name
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Related objects
    related_object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, 
                                          null=True, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('related_object_type', 'related_object_id')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ticket_number']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['created_by', 'status']),
        ]
    
    def __str__(self):
        return f"{self.ticket_number} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = self.generate_ticket_number()
        super().save(*args, **kwargs)
    
    def generate_ticket_number(self):
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        last_ticket = Ticket.objects.filter(
            ticket_number__startswith=f"TKT-{date_str}"
        ).order_by('-ticket_number').first()
        
        if last_ticket:
            last_num = int(last_ticket.ticket_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"TKT-{date_str}-{new_num:04d}"
    
    @property
    def is_overdue(self):
        if self.due_date and self.status not in ['resolved', 'closed', 'cancelled']:
            return timezone.now() > self.due_date
        return False
    
    @property
    def age_in_days(self):
        return (timezone.now() - self.created_at).days

class TicketMessage(models.Model):
    ticket = models.ForeignKey(
        Ticket, 
        on_delete=models.CASCADE, 
        related_name='ticket_messages'  # CHANGED: Added related_name
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    attachments = models.FileField(upload_to='ticket_attachments/%Y/%m/%d/', null=True, blank=True)
    is_internal_note = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Message for {self.ticket.ticket_number} by {self.user.username}"

class InternalMessage(models.Model):
    MESSAGE_TYPES = [
        ('direct', 'Direct Message'),
        ('group', 'Group Message'),
        ('announcement', 'Announcement'),
    ]
    
    subject = models.CharField(max_length=200)
    message = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='direct')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='sent_messages'
    )
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        through='MessageRecipient',
        related_name='received_messages'
    )
    parent_message = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='message_replies'
    )
    
    # Read tracking
    is_urgent = models.BooleanField(default=False)
    requires_confirmation = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subject} - {self.sender.username}"
    
    def save(self, *args, **kwargs):
        # Ensure the message is saved before setting many-to-many relationships
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"InternalMessage saved - PK: {self.pk}, Subject: {self.subject}")

class MessageRecipient(models.Model):
    message = models.ForeignKey(
        InternalMessage, 
        on_delete=models.CASCADE,
        related_name='recipient_entries'  # CHANGED: Added related_name
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='message_recipients'  # CHANGED: Added related_name
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['message', 'recipient']

class TicketWorkflow(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ticket_type = models.CharField(max_length=50, choices=Ticket.TICKET_TYPES)
    assigned_department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE,
        related_name='workflows'  # CHANGED: Added related_name
    )
    auto_assign = models.BooleanField(default=False)
    sla_hours = models.PositiveIntegerField(default=24)  # Service Level Agreement
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.ticket_type}"

