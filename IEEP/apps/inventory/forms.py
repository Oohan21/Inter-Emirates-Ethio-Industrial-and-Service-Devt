# inventory/forms.py
from django import forms
from .models import StockItem, StockTransaction, Warehouse
from apps.products.models import Product
from django.contrib.auth import get_user_model  

User = get_user_model()

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = [
            'code', 'name', 'description', 'location', 'capacity', 
            'manager', 'is_active'
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'e.g., WH-001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'e.g., Main Warehouse'
            }),
            'description': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'rows': 3,
                'placeholder': 'Optional description of the warehouse...'
            }),
            'location': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'e.g., Building A, Floor 2'
            }),
            'capacity': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'e.g., 1000 units, 500 sq ft'
            }),
            'manager': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active users for manager selection
        self.fields['manager'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        self.fields['manager'].required = False
        self.fields['description'].required = False
        self.fields['capacity'].required = False

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            # Check if code already exists (excluding current instance for updates)
            query = Warehouse.objects.filter(code__iexact=code)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            
            if query.exists():
                raise forms.ValidationError("A warehouse with this code already exists.")
        return code

class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = [
            'product', 'warehouse', 'quantity', 'unit_cost', 'batch_number',
            'location', 'expiry_date', 'manufactured_date', 'notes',
            'reorder_threshold', 'procurement_status'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'warehouse': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'step': '0.01'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'step': '0.01'}),
            'batch_number': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'location': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'manufactured_date': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'notes': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'rows': 4}),
            'reorder_threshold': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'step': '0.01'}),
            'procurement_status': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('sku')
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).order_by('code')
        self.fields['product'].required = True
        self.fields['warehouse'].required = True
        self.fields['quantity'].required = True

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['stock_item', 'transaction_type', 'quantity', 'reference', 'notes', 'created_by']
        widgets = {
            'stock_item': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'transaction_type': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.01'}),
            'reference': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'notes': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 4}),
            'created_by': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stock_item'].queryset = StockItem.objects.select_related('product__unit_of_measure', 'warehouse')
        self.fields['transaction_type'].choices = [('adjustment', 'Adjustment')]
        self.fields['created_by'].initial = self.initial.get('created_by')
