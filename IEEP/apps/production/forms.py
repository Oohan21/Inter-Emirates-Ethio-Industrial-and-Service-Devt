from django import forms
from django.forms import inlineformset_factory
from ..products.models import Product, BOM, BOMComponent
from .models import ProductionOrder, ProductionOrderItem
from apps.inventory.models import StockItem
from apps.maintenance.models import Asset

class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = [
            'product', 'bom', 'planned_quantity', 'scheduled_start', 'scheduled_end',
            'assigned_machine', 'assigned_operator', 'expected_yield'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'bom': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'planned_quantity': forms.NumberInput(attrs={'step': '0.0001', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'scheduled_start': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'scheduled_end': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'assigned_machine': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'assigned_operator': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'expected_yield': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active BOMs
        self.fields['bom'].queryset = BOM.objects.filter(is_active=True)
        # Only finished goods
        self.fields['product'].queryset = Product.objects.filter(product_type='finished', is_active=True)
        # Updated to Asset model - show operational production machines
        self.fields['assigned_machine'].queryset = Asset.objects.filter(
            status__in=['operational', 'idle'],
            asset_type__in=['production_machine', 'mixer', 'filler', 'packaging']
        )

class ProductionOrderItemForm(forms.ModelForm):
    class Meta:
        model = ProductionOrderItem
        fields = ['product', 'planned_quantity', 'batch_number', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'planned_quantity': forms.NumberInput(attrs={'step': '0.0001', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'batch_number': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only raw/intermediate/packaging materials
        self.fields['product'].queryset = Product.objects.filter(
            product_type__in=['raw', 'intermediate', 'packaging'],
            is_active=True
        )


# Formset for inline items
ProductionOrderItemFormSet = inlineformset_factory(
    ProductionOrder,
    ProductionOrderItem,
    form=ProductionOrderItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)