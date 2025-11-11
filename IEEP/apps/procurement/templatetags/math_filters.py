# apps/procurement/templatetags/math_filters.py
from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def currency(value, currency_symbol="ETB"):
    """Format value as currency"""
    try:
        return f"{currency_symbol} {float(value):,.2f}"
    except (ValueError, TypeError):
        return f"{currency_symbol} 0.00"