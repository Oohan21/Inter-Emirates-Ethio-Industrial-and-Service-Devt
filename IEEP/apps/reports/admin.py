from django.contrib import admin
from .models import ReportTemplate, GeneratedReport

@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'output_format', 'is_active']
    list_filter = ['report_type', 'output_format', 'is_active']
    search_fields = ['name']

@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ['report_template', 'generated_by', 'status', 'generated_at']
    list_filter = ['status']
    readonly_fields = ['generated_at', 'completed_at']
