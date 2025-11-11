# quality/models.py
from django.db import models

class QCChecklist(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class QCChecklistItem(models.Model):
    checklist = models.ForeignKey(QCChecklist, on_delete=models.CASCADE, related_name='items')
    parameter = models.CharField(max_length=200)
    specification = models.CharField(max_length=200)
    min_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    target_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.checklist} - {self.parameter}"

class QCRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('rework', 'Sent for Rework'),
    ]
    
    record_number = models.CharField(max_length=50, unique=True)
    production_order = models.ForeignKey('production.ProductionOrder', on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    batch_number = models.CharField(max_length=100)
    checklist = models.ForeignKey(QCChecklist, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    quantity_tested = models.DecimalField(max_digits=10, decimal_places=4)
    quantity_passed = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    quantity_failed = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    tested_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    tested_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['record_number']),
            models.Index(fields=['status']),
            models.Index(fields=['batch_number']),
        ]

    def __str__(self):
        return f"{self.record_number} - {self.product.sku}"

class TestResult(models.Model):
    qc_record = models.ForeignKey(QCRecord, on_delete=models.CASCADE, related_name='test_results')
    checklist_item = models.ForeignKey(QCChecklistItem, on_delete=models.PROTECT)
    actual_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    text_value = models.TextField(blank=True)
    is_pass = models.BooleanField(null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.qc_record} - {self.checklist_item.parameter}"

class QCAttachment(models.Model):
    qc_record = models.ForeignKey(QCRecord, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='qc_attachments/')
    description = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.qc_record} - {self.description}"

class QCCertificate(models.Model):
    qc_record = models.OneToOneField(QCRecord, on_delete=models.CASCADE)
    certificate_number = models.CharField(max_length=100, unique=True)
    issued_by = models.ForeignKey('users.User', on_delete=models.PROTECT)
    issued_date = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateField(null=True, blank=True)
    certificate_file = models.FileField(upload_to='qc_certificates/', null=True, blank=True)

    def __str__(self):
        return self.certificate_number