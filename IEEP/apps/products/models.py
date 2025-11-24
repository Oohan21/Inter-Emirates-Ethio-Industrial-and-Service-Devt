from django.db import models
from django.conf import settings
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def products_count(self):
        return self.product_set.count()
    
    @property
    def finished_goods_count(self):
        return self.product_set.filter(product_type='finished').count()
    
    @property
    def raw_materials_count(self):
        return self.product_set.filter(product_type='raw').count()
    
    @property
    def intermediate_count(self):
        return self.product_set.filter(product_type='intermediate').count()

class UnitOfMeasure(models.Model):
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} ({self.symbol})"

class Product(models.Model):
    PRODUCT_TYPES = (
        ('finished', 'Finished Good'),
        ('raw', 'Raw Material'),
        ('intermediate', 'Intermediate Compound'),
        ('packaging', 'Packaging Material'),
    )
    
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    unit_of_measure = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_code = models.CharField(max_length=50, blank=True, null=True)
    specifications = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reorder_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Default minimum stock level before a reorder alert is triggered. "
                  "Can be overridden per warehouse in StockItem."
    )
    
    class Meta:
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"
    
    @property
    def margin_percentage(self):
        if self.cost_price > 0 and self.selling_price > 0:
            return ((self.selling_price - self.cost_price) / self.cost_price) * 100
        return 0

    @property
    def total_stock(self):
        """
        Total quantity across all warehouses.
        Uses string-based relation to avoid circular import.
        """
        if hasattr(self, '_total_stock'):
            return self._total_stock  # Use annotated value from view

        # Safe: uses reverse relation string 'stock_items'
        total = self.stock_items.aggregate(
            total=Coalesce(Sum('quantity'), Decimal('0'))
        )['total']
        return total
    
    @property
    def is_low_stock(self):
        return 0 < self.total_stock <= self.reorder_threshold

    @property
    def is_out_of_stock(self):
        return self.total_stock <= 0
    
    @property
    def warehouse_availability(self):
        """Get stock availability by warehouse"""
        try:
            from apps.inventory.models import StockItem
            return self.stock_items.select_related('warehouse').values(
                'warehouse__code', 'warehouse__name', 'quantity'
            )
        except:
            return []

class BOM(models.Model):
    BOM_STATUS = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    
    bom_code = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='boms')
    version = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, null=True)
    instructions = models.TextField(blank=True, null=True)
    effective_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=True)
    labor_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_yield_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['product', 'version']
    
    def __str__(self):
        return f"{self.bom_code} - v{self.version}"
    
    @property
    def total_material_cost(self):
        return sum(component.total_cost for component in self.components.all())
    
    @property
    def total_cost(self):
        return self.total_material_cost + self.labor_cost + self.overhead_cost

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/images/', blank=True, null=True)
    is_main = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_main'] 

    def __str__(self):
        return f"Image for {self.product.name} ({'Main' if self.is_main else 'Secondary'})"

class BOMComponent(models.Model):
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name='components')
    component = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='used_in_boms')
    quantity = models.DecimalField(max_digits=10, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    waste_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['component__sku']
    
    def __str__(self):
        return f"{self.component.sku} in {self.bom.bom_code}"
    
    @property
    def total_cost(self):
        return self.quantity * self.unit_cost
    
    @property
    def effective_quantity(self):
        return self.quantity * (1 + self.waste_percentage / 100)