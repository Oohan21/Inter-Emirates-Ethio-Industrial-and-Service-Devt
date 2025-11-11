# maintenance/templatetags/maintenance_tags.py
from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def get_maintenance_status(asset):
    return asset.maintenance_status

@register.filter
def is_due_for_maintenance(asset):
    return asset.requires_maintenance

@register.filter
def format_operating_hours(hours):
    return f"{hours:,.2f}"