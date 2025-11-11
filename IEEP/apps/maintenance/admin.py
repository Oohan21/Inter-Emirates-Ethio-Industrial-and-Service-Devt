from django.contrib import admin
from .models import Asset, MaintenanceOrder, MaintenanceLog, SparePartUsage

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['asset_code', 'name', 'asset_type', 'status', 'location', 'last_maintenance', 'next_maintenance']
    list_filter = ['status', 'asset_type', 'location']
    search_fields = ['asset_code', 'name', 'serial_number']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('asset_code', 'name', 'description', 'asset_type', 'manufacturer', 'model', 'serial_number')
        }),
        ('Status & Location', {
            'fields': ('status', 'location', 'installation_date', 'capacity')
        }),
        ('Maintenance Schedule', {
            'fields': ('last_maintenance', 'next_maintenance', 'maintenance_interval_days')
        }),
        ('Operational Data', {
            'fields': ('total_operating_hours', 'current_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(MaintenanceOrder)
class MaintenanceOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'asset', 'maintenance_type', 'priority', 'status', 'scheduled_date', 'assigned_to']
    list_filter = ['status', 'priority', 'maintenance_type', 'scheduled_date']
    search_fields = ['order_number', 'asset__asset_code', 'asset__name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'asset', 'maintenance_type', 'priority', 'status')
        }),
        ('Maintenance Details', {
            'fields': ('description', 'requested_by')
        }),
        ('Scheduling', {
            'fields': ('scheduled_date', 'scheduled_duration')
        }),
        ('Assignment', {
            'fields': ('assigned_to',)
        }),
        ('Completion', {
            'fields': ('actual_start', 'actual_end', 'actual_duration', 'work_performed', 'parts_used', 'completed_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ['maintenance_order', 'action', 'created_by', 'technician', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['maintenance_order__order_number', 'action', 'notes']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Log Information', {
            'fields': ('maintenance_order', 'action', 'notes')
        }),
        ('User Information', {
            'fields': ('created_by', 'technician', 'created_at')
        }),
    )

@admin.register(SparePartUsage)
class SparePartUsageAdmin(admin.ModelAdmin):
    list_display = ['maintenance_order', 'product', 'quantity', 'unit_cost', 'total_cost', 'used_at']
    list_filter = ['used_at']
    search_fields = ['maintenance_order__order_number', 'product__sku', 'product__name']
    
    def total_cost(self, obj):
        return obj.total_cost
    total_cost.short_description = 'Total Cost'