from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import mark_safe
from .models import User, Role, AuditLog

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    list_filter = ['name']
    search_fields = ['name']

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'department', 'is_active', 'last_login', 'profile_picture_thumbnail']
    list_filter = ['role', 'is_active', 'department']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = UserAdmin.fieldsets + (
        ('ERP Information', {'fields': ('role', 'phone', 'department')}),
        ('Profile Picture', {'fields': ('profile_picture', 'profile_picture_preview')}),
    )
    readonly_fields = ('profile_picture_preview',)

    def profile_picture_thumbnail(self, obj):
        """Thumbnail for user list (50x50px)."""
        if obj.profile_picture:
            return mark_safe(f'<img src="{obj.profile_picture.url}" width="50" height="50" style="border-radius: 50%; object-fit: cover;" alt="Profile Picture" />')
        return "No Image"
    profile_picture_thumbnail.short_description = 'Profile Picture'

    def profile_picture_preview(self, obj):
        """Full preview in change form (150x150px)."""
        if obj.profile_picture:
            return mark_safe(f'<img src="{obj.profile_picture.url}" width="150" height="150" style="border-radius: 50%; object-fit: cover;" alt="Profile Picture" />')
        return "No Profile Picture Uploaded"
    profile_picture_preview.short_description = 'Current Profile Picture'

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'model_name', 'object_id', 'timestamp']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['user__username', 'model_name', 'object_id']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'changes', 'timestamp', 'ip_address']
