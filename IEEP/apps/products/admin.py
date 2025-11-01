from django.contrib import admin
from .models import Category, UnitOfMeasure, Product, BOM, BOMComponent

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'products_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    def products_count(self, obj):
        return obj.product_set.count()
    products_count.short_description = 'Products'

@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ['name', 'symbol', 'description']
    search_fields = ['name', 'symbol']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'product_type', 'category', 'unit_of_measure', 'cost_price', 'selling_price', 'is_active', 'reorder_threshold']
    list_filter = ['product_type', 'category', 'is_active', 'created_at']
    search_fields = ['sku', 'name', 'product_code']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['reorder_threshold']
    fieldsets = (
        ('Basic Information', {
            'fields': ('sku', 'name', 'description', 'product_type', 'category', 'unit_of_measure')
        }),
        ('Pricing', {
            'fields': ('cost_price', 'selling_price')
        }),
        ('Additional Information', {
            'fields': ('product_code', 'specifications')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class BOMComponentInline(admin.TabularInline):
    model = BOMComponent
    extra = 1
    fields = ['component', 'quantity', 'unit_cost', 'waste_percentage', 'notes']

@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ['bom_code', 'product', 'version', 'is_active', 'is_draft', 'effective_date', 'created_by']
    list_filter = ['is_active', 'is_draft', 'effective_date', 'created_at']
    search_fields = ['bom_code', 'product__sku', 'product__name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [BOMComponentInline]
    fieldsets = (
        ('BOM Information', {
            'fields': ('bom_code', 'product', 'version', 'description', 'instructions')
        }),
        ('Status & Dates', {
            'fields': ('is_active', 'is_draft', 'effective_date')
        }),
        ('Costing', {
            'fields': ('labor_cost', 'overhead_cost', 'expected_yield_percentage')
        }),
        ('Creator', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(BOMComponent)
class BOMComponentAdmin(admin.ModelAdmin):
    list_display = ['bom', 'component', 'quantity', 'unit_cost', 'total_cost', 'waste_percentage']
    list_filter = ['bom', 'component']
    search_fields = ['bom__bom_code', 'component__sku', 'component__name']
    
    def total_cost(self, obj):
        return obj.total_cost
    total_cost.short_description = 'Total Cost'
