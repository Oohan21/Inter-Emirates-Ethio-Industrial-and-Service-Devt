# reports/models.py
from django.db import models

class ReportTemplate(models.Model):
    REPORT_TYPES = [
        ('stock_ledger', 'Stock Ledger'),
        ('production_summary', 'Production Summary'),
        ('maintenance_log', 'Maintenance Log'),
        ('inventory_status', 'Inventory Status'),
        ('bom_cost', 'BOM Cost Analysis'),
        ('procurement_aging', 'Procurement Aging'),
        ('low_stock', 'Low Stock Report'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('csv', 'CSV'),
        ('excel', 'Excel'),
    ]
    
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    description = models.TextField(blank=True)
    template_query = models.TextField(blank=True)
    output_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='pdf')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class GeneratedReport(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    report_template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE)
    generated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    parameters = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['generated_at']),
        ]

    def __str__(self):
        return f"{self.report_template} - {self.generated_at}"