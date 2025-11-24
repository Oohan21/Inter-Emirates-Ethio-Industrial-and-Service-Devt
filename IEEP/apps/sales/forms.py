# sales/forms.py
from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from .models import Customer, SalesInquiry, SalesInquiryItem, SaleOrder, SaleOrderItem
from apps.products.models import Product
from apps.inventory.models import Warehouse

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['customer_type', 'name', 'email', 'phone', 'address', 'tax_id', 'credit_limit', 'payment_terms']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter customer name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter customer address'
            }),
            'tax_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter tax ID'
            }),
            'customer_type': forms.Select(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'payment_terms': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
        }
    
    def clean_credit_limit(self):
        credit_limit = self.cleaned_data.get('credit_limit')
        if credit_limit and credit_limit < 0:
            raise ValidationError("Credit limit cannot be negative.")
        return credit_limit

class SalesInquiryForm(forms.ModelForm):
    class Meta:
        model = SalesInquiry
        fields = ['customer', 'required_date', 'priority', 'notes']
        widgets = {
            'customer': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'required_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add any special requirements or notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True)

class SalesInquiryItemForm(forms.ModelForm):
    class Meta:
        model = SalesInquiryItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'required': True
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
    
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price and unit_price < 0:
            raise ValidationError("Unit price cannot be negative.")
        return unit_price

class SaleOrderForm(forms.ModelForm):
    class Meta:
        model = SaleOrder
        fields = ['customer', 'warehouse', 'expected_ship_date', 'tax_rate', 'notes']
        widgets = {
            'customer': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'warehouse': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'expected_ship_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add any special instructions or notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True)
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True)
    
    def clean_tax_rate(self):
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate and (tax_rate < 0 or tax_rate > 100):
            raise ValidationError("Tax rate must be between 0 and 100 percent.")
        return tax_rate

class SaleOrderItemForm(forms.ModelForm):
    class Meta:
        model = SaleOrderItem
        fields = ['product', 'quantity', 'unit_price', 'discount_percent']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'required': True
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'required': True
            }),
            'discount_percent': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        
        if not self.instance.pk:  
            self.fields['quantity'].initial = 1
            self.fields['discount_percent'].initial = 0
    
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is None:
            raise ValidationError("Quantity is required.")
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is None:
            raise ValidationError("Unit price is required.")
        if unit_price < 0:
            raise ValidationError("Unit price cannot be negative.")
        return unit_price
    
    def clean_discount_percent(self):
        discount_percent = self.cleaned_data.get('discount_percent')
        if discount_percent is None:
            return 0
        if discount_percent < 0 or discount_percent > 100:
            raise ValidationError("Discount must be between 0 and 100 percent.")
        return discount_percent

# Formsets
SalesInquiryItemFormSet = inlineformset_factory(
    SalesInquiry,
    SalesInquiryItem,
    form=SalesInquiryItemForm,
    extra=1,
    can_delete=True,
    fields=['product', 'quantity', 'unit_price']
)

SaleOrderItemFormSet = inlineformset_factory(
    SaleOrder,
    SaleOrderItem,
    form=SaleOrderItemForm,
    extra=1,
    can_delete=True,
    fields=['product', 'quantity', 'unit_price', 'discount_percent']
)