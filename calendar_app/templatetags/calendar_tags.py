from django import template

register = template.Library()


@register.filter
def getitem(form, field_name):
    try:
        return form[field_name].value()
    except (KeyError, AttributeError):
        return None
