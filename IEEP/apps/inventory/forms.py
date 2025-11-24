# inventory/forms.py
from django import forms
from .models import StockItem, StockTransaction, Warehouse
from apps.products.models import Product
from django.utils import timezone
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
            'product', 'warehouse', 'quantity', 'batch_number', 'unit_cost',
            'location', 'expiry_date', 'manufactured_date', 'notes',
            'procurement_status' 
        ]
        widgets = {
            'product': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'data-placeholder': 'Select a product'
            }),
            'warehouse': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 
                'step': '0.01'
            }),
            'batch_number': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'unit_cost': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'step': '0.01',
                'min': '0'
            }),
            'location': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'expiry_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'manufactured_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 
                'rows': 4
            }),
            'procurement_status': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['unit_cost'].initial = self.instance.unit_cost
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('sku')
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).order_by('code')
        
        # Add product information display for existing instances
        if self.instance and self.instance.pk:
            self.fields['product'].disabled = True
            self.fields['product'].help_text = f"SKU: {self.instance.product.sku} | Type: {self.instance.product.get_product_type_display()}"

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

# inventory/forms.py - Enhanced transaction forms
class StockAdjustmentForm(forms.ModelForm):
    ADJUSTMENT_TYPES = [
        ('set', 'Set Absolute Quantity'),
        ('add', 'Add Quantity'),
        ('subtract', 'Subtract Quantity'),
    ]
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        initial='set',
        widget=forms.RadioSelect(attrs={'class': 'flex space-x-4'})
    )
    quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
            'step': '0.01'
        })
    )
    
    class Meta:
        model = StockTransaction
        fields = ['stock_item', 'quantity', 'reference', 'notes']
        widgets = {
            'stock_item': forms.Select(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'placeholder': 'e.g., Stock count, correction...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Optional notes about this adjustment...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter active stock items
        self.fields['stock_item'].queryset = StockItem.objects.select_related(
            'product', 'warehouse'
        ).filter(quantity__gte=0)
        
        # Set initial reference
        if not self.instance.pk:
            self.fields['reference'].initial = f"ADJ-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
    
    def clean(self):
        cleaned_data = super().clean()
        stock_item = cleaned_data.get('stock_item')
        quantity = cleaned_data.get('quantity')
        adjustment_type = cleaned_data.get('adjustment_type')
        
        if stock_item and quantity is not None:
            current_quantity = stock_item.quantity
            
            if adjustment_type == 'subtract':
                if quantity > current_quantity:
                    raise forms.ValidationError(
                        f"Cannot subtract {quantity} from current stock of {current_quantity}"
                    )
            elif adjustment_type == 'set':
                if quantity < 0:
                    raise forms.ValidationError("Stock quantity cannot be negative")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.transaction_type = 'adjustment'
        instance.created_by = self.user
        
        # Calculate adjustment quantity based on type
        adjustment_type = self.cleaned_data.get('adjustment_type')
        quantity = self.cleaned_data.get('quantity')
        current_quantity = instance.stock_item.quantity
        
        if adjustment_type == 'set':
            instance.quantity = quantity - current_quantity
        elif adjustment_type == 'add':
            instance.quantity = quantity
        elif adjustment_type == 'subtract':
            instance.quantity = -quantity
        
        if commit:
            instance.save()
        return instance

class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['stock_item', 'destination_warehouse', 'quantity', 'reference', 'notes']
        widgets = {
            'stock_item': forms.Select(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            }),
            'destination_warehouse': forms.Select(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'step': '0.01'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'placeholder': 'e.g., Transfer to Main Warehouse...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Optional transfer notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter stock items with positive quantity
        self.fields['stock_item'].queryset = StockItem.objects.select_related(
            'product', 'warehouse'
        ).filter(quantity__gt=0)
        
        # Filter active warehouses (excluding source warehouse)
        self.fields['destination_warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        
        # Set initial reference
        if not self.instance.pk:
            self.fields['reference'].initial = f"TRF-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
    
    def clean(self):
        cleaned_data = super().clean()
        stock_item = cleaned_data.get('stock_item')
        quantity = cleaned_data.get('quantity')
        destination_warehouse = cleaned_data.get('destination_warehouse')
        
        if stock_item and quantity and destination_warehouse:
            # Check if transferring to same warehouse
            if stock_item.warehouse == destination_warehouse:
                raise forms.ValidationError("Cannot transfer to the same warehouse")
            
            # Check available quantity
            if quantity > stock_item.quantity:
                raise forms.ValidationError(
                    f"Insufficient stock. Available: {stock_item.quantity}, Requested: {quantity}"
                )
            
            # Check if quantity is positive
            if quantity <= 0:
                raise forms.ValidationError("Transfer quantity must be positive")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.transaction_type = 'transfer'
        instance.created_by = self.user
        instance.quantity = -self.cleaned_data['quantity']  # Negative for source warehouse
        
        if commit:
            instance.save()
        return instance

class StockInForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['stock_item', 'quantity', 'reference', 'notes']
        widgets = {
            'stock_item': forms.Select(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'step': '0.01'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'placeholder': 'e.g., Purchase receipt, production...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Optional notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set initial reference
        if not self.instance.pk:
            self.fields['reference'].initial = f"IN-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
    
    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity <= 0:
            raise forms.ValidationError("Stock in quantity must be positive")
        return quantity
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.transaction_type = 'in'
        instance.created_by = self.user
        
        if commit:
            instance.save()
        return instance