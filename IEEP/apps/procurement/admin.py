from django.contrib import admin
from .models import Supplier, PurchaseRequisition, PurchaseRequisitionItem, PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'supplier_type', 'contact_person', 'email', 'phone', 'is_active']
    list_filter = ['supplier_type', 'is_active', 'created_at']
    search_fields = ['code', 'name', 'contact_person', 'email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'supplier_type', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'email', 'phone', 'address')
        }),
        ('Business Information', {
            'fields': ('tax_id', 'payment_terms', 'lead_time_days', 'performance_rating')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(PurchaseRequisition)
class PurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ['requisition_number', 'requested_by', 'status', 'total_estimated_cost', 'created_at']
    list_filter = ['status', 'department']
    search_fields = ['requisition_number']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'status', 'order_date', 'expected_delivery_date', 'total_amount']
    list_filter = ['status']
    search_fields = ['po_number', 'supplier__name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ['gr_number', 'purchase_order', 'received_by', 'receipt_date']
    search_fields = ['gr_number']
    readonly_fields = ['created_at']