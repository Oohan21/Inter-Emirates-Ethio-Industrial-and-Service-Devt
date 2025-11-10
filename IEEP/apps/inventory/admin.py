from django.contrib import admin
from .models import Warehouse, StockItem, StockTransaction, ReorderAlert, Order, OrderItem
from django.contrib.auth import get_user_model

User = get_user_model() 

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity', 'batch_number', 'procurement_status', 'expiry_date', 'created_at']
    list_filter = ['warehouse', 'procurement_status', 'expiry_date', 'created_at']
    search_fields = ['product__sku', 'product__name', 'batch_number', 'location', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'warehouse', 'quantity', 'unit_cost', 'batch_number', 'location')
        }),
        ('Status and Dates', {
            'fields': ('procurement_status', 'expiry_date', 'manufactured_date', 'reorder_threshold')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['stock_item', 'transaction_type', 'quantity', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['stock_item__product__sku', 'reference']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(ReorderAlert)
class ReorderAlertAdmin(admin.ModelAdmin):
    list_display = ['stock_item', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['stock_item__product__sku']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['order_number']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__sku', 'product__name']
    readonly_fields = ['created_at', 'updated_at']
