# inventory/admin.py
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
    list_display = [
        'created_at', 'get_product_sku', 'get_transaction_type', 
        'get_quantity_change', 'get_warehouse', 'reference', 'created_by'
    ]
    list_filter = ['transaction_type', 'created_at', 'stock_item__warehouse']
    search_fields = [
        'stock_item__product__sku', 'stock_item__product__name', 
        'reference', 'notes'
    ]
    readonly_fields = ['created_at', 'updated_at', 'previous_quantity', 'new_quantity']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('stock_item', 'transaction_type', 'quantity', 'destination_warehouse')
        }),
        ('Tracking', {
            'fields': ('previous_quantity', 'new_quantity', 'reference', 'notes')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_product_sku(self, obj):
        return obj.stock_item.product.sku
    get_product_sku.short_description = 'Product SKU'
    get_product_sku.admin_order_field = 'stock_item__product__sku'
    
    def get_transaction_type(self, obj):
        return obj.get_transaction_type_display()
    get_transaction_type.short_description = 'Type'
    
    def get_quantity_change(self, obj):
        color = 'green' if obj.is_positive else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.absolute_quantity_change
        )
    get_quantity_change.short_description = 'Quantity Change'
    
    def get_warehouse(self, obj):
        if obj.destination_warehouse:
            return format_html(
                '{} → {}',
                obj.stock_item.warehouse.code,
                obj.destination_warehouse.code
            )
        return obj.stock_item.warehouse.code
    get_warehouse.short_description = 'Warehouse'

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