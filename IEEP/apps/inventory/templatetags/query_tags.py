# inventory/templatetags/query_tags.py
from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def query_string(context, key, value):
    request = context['request']
    params = request.GET.copy()
    if key in params and params[key] == value:
        params[key] = f'-{value}'  # Toggle to descending
    else:
        params[key] = value  # Set to ascending
    return params.urlencode()