# users/forms.py
from django import forms
from django.contrib.auth import get_user_model
from .models import Role

User = get_user_model()

class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        required=False,
        help_text="Leave blank to auto-generate"
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'department', 'role', 'is_active']
        widgets = {
            'role': forms.Select(attrs={'class': 'w-full rounded-md border-gray-300'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.all()
        self.fields['role'].empty_label = "— No Role —"
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'})

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.instance.pk and not password:
            import secrets
            import string
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(12))
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user