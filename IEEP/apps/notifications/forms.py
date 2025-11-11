# notifications/forms.py
from django import forms
from .models import NotificationPreference, InternalMessage

class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = [
            'email_notifications', 'email_frequency',
            'low_stock_alerts', 'maintenance_alerts', 'work_order_alerts',
            'qc_alerts', 'system_alerts', 'in_app_notifications', 
            'desktop_notifications'
        ]
        widgets = {
            'email_frequency': forms.Select(attrs={'class': 'form-control'}),
        }

class InternalMessageForm(forms.ModelForm):
    class Meta:
        model = InternalMessage
        fields = [
            'subject', 'message', 'message_type', 'recipients',
            'is_urgent', 'requires_confirmation'
        ]
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'message_type': forms.Select(attrs={'class': 'form-control'}),
            'recipients': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }