# quality/admin.py
from django.contrib import admin
from .models import QCChecklist, QCChecklistItem, QCRecord, TestResult, QCAttachment, QCCertificate

@admin.register(QCChecklist)
class QCChecklistAdmin(admin.ModelAdmin):
    list_display = ['name', 'product', 'is_active', 'created_by']
    list_filter = ['is_active']
    search_fields = ['name', 'product__sku']

@admin.register(QCRecord)
class QCRecordAdmin(admin.ModelAdmin):
    list_display = ['record_number', 'product', 'batch_number', 'status', 'tested_by', 'tested_at']
    list_filter = ['status']
    search_fields = ['record_number', 'batch_number', 'product__sku']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ['qc_record', 'checklist_item', 'actual_value', 'is_pass']
    list_filter = ['is_pass']

@admin.register(QCCertificate)
class QCCertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_number', 'qc_record', 'issued_by', 'issued_date']
    search_fields = ['certificate_number']
    readonly_fields = ['issued_date']