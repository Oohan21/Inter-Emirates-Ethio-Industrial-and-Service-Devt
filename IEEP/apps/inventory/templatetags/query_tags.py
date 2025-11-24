# inventory/templatetags/query_tags.py
from django import template
from urllib.parse import urlencode

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

@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Returns the URL-encoded querystring for the current page,
    updating the params with the key/value pairs passed to the tag.
    
    Usage: {% query_transform page=2 sort='name' %}
    """
    query = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value is not None:
            query[key] = value
        else:
            query.pop(key, None)
    return query.urlencode()


@register.simple_tag(takes_context=True)
def query_remove(context, *args):
    """
    Returns the URL-encoded querystring for the current page,
    removing the specified parameters.
    
    Usage: {% query_remove 'page' 'sort' %}
    """
    query = context['request'].GET.copy()
    for key in args:
        query.pop(key, None)
    return query.urlencode()


@register.simple_tag(takes_context=True)
def current_query(context):
    """
    Returns the current query string without the page parameter.
    Useful for maintaining filters when changing pages.
    """
    query = context['request'].GET.copy()
    if 'page' in query:
        query.pop('page')
    return query.urlencode()

@register.filter
def sub(value, arg):
    """Subtract the arg from the value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def div(value, arg):
    """Divide the value by the arg"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def mul(value, arg):
    """Multiply the value by the arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0