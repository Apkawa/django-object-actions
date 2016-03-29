# coding: utf-8
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.template import Variable, VariableDoesNotExist
from django import template
from django.template.defaultfilters import floatformat
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.simple_tag(takes_context=True)
def tool_url(context, tool, pk=None, tools_view_name=None):
    if not tools_view_name:
        tools_view_name = context['tools_view_name']

    url_kwargs = {
        'tool': tool['name']
    }
    if pk:
        url_kwargs['pk'] = pk
    url = tool.get('url')
    if url:
        if callable(url):
            url = url(**url_kwargs)
        return url

    url = reverse(tools_view_name, kwargs=url_kwargs)
    return url
