# coding: utf-8
from __future__ import unicode_literals

from uuid import uuid4

import six
from django.conf.urls import url
from django.core.urlresolvers import reverse
from django.views.generic.base import RedirectView, View


class BaseAction(object):
    name = None
    label = ''
    short_description = ''

    change = True
    list = False

    button_attrs = None

    def __init__(self, label=None, short_description=None, change=None, list=None, name=None, button_attrs=None):
        self.label = label or self.label
        self.short_description = short_description or self.short_description
        if change is not None:
            self.change = change
        if list is not None:
            self.list = list

        self.name = name and name
        if not self.name:
            self.name = str(uuid4())

        if button_attrs:
            self.button_attrs = button_attrs

    def get_button_attrs(self):
        return self.button_attrs

    def as_view(self, admin, model, back):
        raise NotImplementedError()

    def get_url(self, **kwargs):
        tool_name = "admin:" + self.get_url_name()
        return reverse(tool_name, kwargs=kwargs)

    def get_url_name(self):
        url_name = self.name
        if not url_name:
            url_name = "%s_action" % self.name
        return url_name

    def get_patterns(self, base_name, admin):
        admin_site = admin.admin_site
        urls = []

        if self.change:
            urls.append(
                url(r'^(?P<pk>[0-9a-f\-]+)/actions/o/(?P<tool>{})/$'.format(self.name),
                    admin_site.admin_view(  # checks permissions
                        self.as_view(
                            model=admin.model,
                            admin=admin,
                            back='admin:%s_change' % base_name,
                        )
                    ),
                    name=self.get_url_name())
            )

        if self.list:
            urls.append(
                # changelist
                url(r'^actions/o/(?P<tool>{})/$'.format(self.name),
                    admin_site.admin_view(  # checks permissions
                        self.as_view(
                            model=admin.model,
                            admin=self,
                            back='admin:%s_changelist' % base_name,
                        )
                    ),
                    name=self.get_url_name()),
            )
        return urls


class UrlAction(BaseAction):
    def __init__(self, url, **kwargs):
        self.url = url
        super(UrlAction, self).__init__(**kwargs)

    def as_view(self, admin, model, back):
        return RedirectView.as_view(permanent=False, url=self.url)


class ViewAction(BaseAction):
    def __init__(self, view, view_params=None, **kwargs):
        self.view = view
        self.view_params = view_params

        if not kwargs.get('name'):
            if isinstance(view, six.string_types):
                self.name = view

        super(ViewAction, self).__init__(**kwargs)

    def as_view(self, admin, model, back):
        view_handler = self.view

        if isinstance(view_handler, six.string_types):
            view_handler = getattr(admin, view_handler)

        if isinstance(view_handler, View):
            view_handler = view_handler.as_view(admin=admin)

        if callable(self.view_params):
            view_params = self.view_params

            @six.wraps(view_handler)
            def _wrap(request, *args, **kwargs):
                args, kwargs = view_params(*args, **kwargs)
                return view_handler(request, *args, **kwargs)

            return _wrap

        return view_handler
