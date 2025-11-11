# notifications/admin.py
from django.contrib import admin
from .models import Notification, NotificationPreference, Ticket, TicketMessage, TicketWorkflow, InternalMessage, Department

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'priority', 'is_read', 'created_at']
    list_filter = ['notification_type', 'priority', 'is_read', 'created_at']
    search_fields = ['user__username', 'title', 'message']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Notification Details', {
            'fields': ('user', 'title', 'message', 'notification_type', 'priority')
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id', 'action_url')
        }),
        ('Status', {
            'fields': ('is_read', 'is_sent', 'read_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_notifications', 'in_app_notifications', 'updated_at']
    list_filter = ['email_notifications', 'in_app_notifications']
    search_fields = ['user__username']
    readonly_fields = ['updated_at']

# notifications/admin.py - ADD THESE ADMIN CLASSES
@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'title', 'ticket_type', 'status', 'priority', 
                   'created_by', 'assigned_to', 'created_at', 'is_overdue']
    list_filter = ['ticket_type', 'status', 'priority', 'created_at', 'assigned_to']
    search_fields = ['ticket_number', 'title', 'description', 'created_by__username']
    readonly_fields = ['created_at', 'updated_at', 'ticket_number']
    fieldsets = (
        ('Ticket Information', {
            'fields': ('ticket_number', 'title', 'description', 'ticket_type', 'priority')
        }),
        ('Status & Assignment', {
            'fields': ('status', 'created_by', 'assigned_to', 'assigned_department', 'due_date')
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id')
        }),
        ('Resolution', {
            'fields': ('resolved_at', 'closed_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'user', 'created_at', 'is_internal_note']
    list_filter = ['is_internal_note', 'created_at']
    search_fields = ['ticket__ticket_number', 'user__username', 'message']

@admin.register(InternalMessage)
class InternalMessageAdmin(admin.ModelAdmin):
    list_display = ['subject', 'sender', 'message_type', 'is_urgent', 'created_at']
    list_filter = ['message_type', 'is_urgent', 'created_at']
    search_fields = ['subject', 'message', 'sender__username']

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'manager', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'manager__username']

@admin.register(TicketWorkflow)
class TicketWorkflowAdmin(admin.ModelAdmin):
    list_display = ['name', 'ticket_type', 'assigned_department', 'sla_hours', 'is_active']
    list_filter = ['ticket_type', 'is_active']