# maintenance/forms.py
from django import forms
from .models import Asset, MaintenanceOrder

class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = [
            'asset_code', 'name', 'description', 'asset_type', 'manufacturer', 'model',
            'serial_number', 'installation_date', 'status', 'capacity', 'location',
            'last_maintenance', 'next_maintenance', 'maintenance_interval_days',
            'total_operating_hours', 'current_order'
        ]
        widgets = {
            'asset_code': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'name': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 4}),
            'asset_type': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'manufacturer': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'model': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'serial_number': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'installation_date': forms.DateInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'capacity': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'location': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'last_maintenance': forms.DateInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'type': 'date'}),
            'next_maintenance': forms.DateInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'type': 'date'}),
            'maintenance_interval_days': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'total_operating_hours': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.01'}),
            'current_order': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }

class AssetCreateForm(forms.ModelForm):
    """Form for creating new assets with required fields only"""
    class Meta:
        model = Asset
        fields = [
            'asset_code', 'name', 'asset_type', 'status', 'location'
        ]
        widgets = {
            'asset_code': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'name': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'asset_type': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'status': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'location': forms.TextInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }
    
    def clean_asset_code(self):
        asset_code = self.cleaned_data.get('asset_code')
        if Asset.objects.filter(asset_code=asset_code).exists():
            raise forms.ValidationError("An asset with this code already exists.")
        return asset_code
        
class MaintenanceOrderForm(forms.ModelForm):
    class Meta:
        model = MaintenanceOrder
        fields = ['asset', 'priority', 'maintenance_type', 'description', 'scheduled_date', 'assigned_to']
        widgets = {
            'asset': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'priority': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'maintenance_type': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
            'description': forms.Textarea(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'rows': 4}),
            'scheduled_date': forms.DateInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        }