from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.html import format_html
from django.utils.translation import gettext as _

register = template.Library()


@register.simple_tag
def cascade_context():
    """What the shared checkbox cascade (``_filter_multiselect_js.html``) needs from the server: its words."""
    return {"more": _("%(count)s more: refine the search")}


@register.filter
def getitem(form, field_name):
    try:
        return form[field_name].value()
    except (KeyError, AttributeError):
        return None


def _utc_offset(moment) -> str:
    """``UTC+5``, ``UTC+5:30``, ``UTC-3``, ``UTC`` -- the same in every language."""
    minutes = int(moment.utcoffset().total_seconds()) // 60
    if not minutes:
        return "UTC"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{'+' if minutes > 0 else '-'}{hours}" + (f":{rest:02d}" if rest else "")


@register.simple_tag(takes_context=True)
def event_time(context, moment, event_zone):
    """A moment bound to an event's place (issue #344): in the event's zone with its offset, and
    again in the reader's when their browser has told it and the two offsets differ at that moment."""
    if moment is None:
        return ""
    there = timezone.localtime(moment, event_zone)
    shown = f"{date_format(there, 'd.m.Y H:i')} ({_utc_offset(there)})"
    reader_zone = getattr(context.get("request"), "reader_timezone", None)
    if reader_zone is None:
        return shown
    here = timezone.localtime(moment, reader_zone)
    if here.utcoffset() == there.utcoffset():
        return shown
    return format_html(
        "{} &middot; {}",
        shown,
        _("your time: %(time)s") % {"time": f"{date_format(here, 'd.m.Y H:i')} ({_utc_offset(here)})"},
    )
