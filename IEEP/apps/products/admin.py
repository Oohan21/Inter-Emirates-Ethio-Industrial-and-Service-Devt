# products/admin.py
from django.contrib import admin
from django.utils.html import mark_safe
from .models import Category, UnitOfMeasure, Product, BOM, BOMComponent, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'is_main', 'image_preview']
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        """Thumbnail preview in inline (100x100px)."""
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="100" height="100" style="object-fit: cover; border-radius: 8px;" alt="Image Preview" />')
        return "No Image"
    image_preview.short_description = 'Preview'

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
    list_display = ['sku', 'name', 'product_type', 'category', 'unit_of_measure', 'cost_price', 'selling_price', 'is_active', 'reorder_threshold', 'main_image_thumbnail']
    list_filter = ['product_type', 'category', 'is_active', 'created_at']
    search_fields = ['sku', 'name', 'product_code']
    readonly_fields = ['created_at', 'updated_at', 'main_image_preview']
    list_editable = ['reorder_threshold']
    inlines = [ProductImageInline]
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
        ('Images', {
            'fields': ('main_image_preview',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def main_image_thumbnail(self, obj):
        """Thumbnail for product list (50x50px)."""
        main_image = obj.images.filter(is_main=True).first() or obj.images.first()
        if main_image and main_image.image:
            return mark_safe(f'<img src="{main_image.image.url}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" alt="Main Image" />')
        return "No Image"
    main_image_thumbnail.short_description = 'Image'

    def main_image_preview(self, obj):
        """Full preview in change form (200x200px)."""
        main_image = obj.images.filter(is_main=True).first() or obj.images.first()
        if main_image and main_image.image:
            return mark_safe(f'<img src="{main_image.image.url}" width="200" height="200" style="object-fit: cover; border-radius: 8px;" alt="Main Image Preview" />')
        return "No Images Uploaded"
    main_image_preview.short_description = 'Main Image Preview'

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

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'image_thumbnail', 'is_main']
    list_filter = ['is_main']
    search_fields = ['product__sku', 'product__name']

    def image_thumbnail(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="50" height="50" style="object-fit: cover;" alt="Image" />')
        return "No Image"
    image_thumbnail.short_description = 'Image'
