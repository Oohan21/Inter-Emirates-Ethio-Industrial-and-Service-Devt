from django import forms
from .models import Product, Category, UnitOfMeasure, BOM, BOMComponent
from django.forms import inlineformset_factory

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'sku', 'name', 'description', 'product_type', 'category',
            'unit_of_measure', 'cost_price', 'selling_price', 'product_code',
            'specifications', 'is_active', 'reorder_threshold'
        ]
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'name': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 4}),
            'product_type': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'category': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'unit_of_measure': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'cost_price': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.01'}),
            'product_code': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'specifications': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded'}),
            'reorder_threshold': forms.NumberInput(
                attrs={'step': '0.01', 'min': '0', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].required = False
        self.fields['product_code'].required = False
        self.fields['description'].required = False
        self.fields['specifications'].required = False

class BOMForm(forms.ModelForm):
    class Meta:
        model = BOM
        fields = [
            'bom_code', 'product', 'version', 'description', 'instructions',
            'effective_date', 'labor_cost', 'overhead_cost',
            'expected_yield_percentage',
        ]
        widgets = {
            'bom_code': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'product': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'version': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 3}),
            'instructions': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 5}),
            'effective_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'labor_cost': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'overhead_cost': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'expected_yield_percentage': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(
            product_type='finished', is_active=True
        )
        self.fields['bom_code'].required = True
        self.fields['product'].required = True


class BOMComponentForm(forms.ModelForm):
    class Meta:
        model = BOMComponent
        fields = ['component', 'quantity', 'unit_cost', 'waste_percentage', 'notes']
        widgets = {
            'component': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'quantity': forms.NumberInput(attrs={'step': '0.0001', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'unit_cost': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'waste_percentage': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['component'].queryset = Product.objects.filter(is_active=True)

BOMComponentFormSet = inlineformset_factory(
    BOM,
    BOMComponent,
    form=BOMComponentForm,
    extra=1,
    can_delete=True,
)