from django import template

register = template.Library()

@register.filter(name='split_string')
def split_string(value, arg):
    return value.split(arg)

@register.filter(name='last_item')
def last_item(value):
    if isinstance(value, list) and value:
        return value[-1]
    return value
