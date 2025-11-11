# production/admin.py
from django.contrib import admin
from .models import WorkOrder, ProductionStep, ProductionLog, MaterialIssue, DowntimeLog

@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'product', 'planned_quantity', 'status', 'priority', 'scheduled_start', 'assigned_machine']
    list_filter = ['status', 'priority', 'scheduled_start', 'created_at']
    search_fields = ['order_number', 'product__sku', 'product__name']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'product', 'bom', 'planned_quantity', 'status', 'priority')
        }),
        ('Scheduling', {
            'fields': ('scheduled_start', 'scheduled_end', 'actual_start', 'actual_end')
        }),
        ('Production Results', {
            'fields': ('actual_quantity', 'scrap_quantity', 'qc_passed', 'qc_notes')
        }),
        ('Resources', {
            'fields': ('assigned_machine', 'operator')
        }),
        ('Creator', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ProductionStep)
class ProductionStepAdmin(admin.ModelAdmin):
    list_display = ['work_order', 'step_number', 'name', 'is_completed', 'completed_at']
    list_filter = ['is_completed', 'work_order']
    search_fields = ['work_order__order_number', 'name']
    readonly_fields = ['completed_at']
    fieldsets = (
        ('Step Information', {
            'fields': ('work_order', 'step_number', 'name', 'description')
        }),
        ('Timing', {
            'fields': ('expected_duration', 'actual_duration')
        }),
        ('Completion', {
            'fields': ('is_completed', 'completed_at')
        }),
    )

@admin.register(ProductionLog)
class ProductionLogAdmin(admin.ModelAdmin):
    list_display = ['work_order', 'action', 'quantity_produced', 'created_by', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['work_order__order_number', 'action', 'notes']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Log Information', {
            'fields': ('work_order', 'action', 'quantity_produced', 'quantity_scrap', 'notes')
        }),
        ('User Information', {
            'fields': ('created_by', 'created_at')
        }),
    )

@admin.register(MaterialIssue)
class MaterialIssueAdmin(admin.ModelAdmin):
    list_display = ['work_order', 'product', 'quantity', 'batch_number', 'issued_by', 'issued_at']
    list_filter = ['issued_at', 'product']
    search_fields = ['work_order__order_number', 'product__sku', 'batch_number']
    readonly_fields = ['issued_at']
    fieldsets = (
        ('Issue Information', {
            'fields': ('work_order', 'product', 'quantity', 'batch_number', 'notes')
        }),
        ('Issuer Information', {
            'fields': ('issued_by', 'issued_at')
        }),
    )

@admin.register(DowntimeLog)
class DowntimeLogAdmin(admin.ModelAdmin):
    list_display = ['machine', 'downtime_type', 'start_time', 'end_time', 'duration', 'work_order']
    list_filter = ['downtime_type', 'start_time']
    search_fields = ['machine__asset_code', 'machine__name', 'reason']
    readonly_fields = ['duration']
    fieldsets = (
        ('Downtime Information', {
            'fields': ('work_order', 'machine', 'downtime_type', 'reason')
        }),
        ('Timing', {
            'fields': ('start_time', 'end_time', 'duration')
        }),
        ('Resolution', {
            'fields': ('resolved_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
