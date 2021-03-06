from __future__ import unicode_literals

from functools import wraps
from itertools import chain

from django.conf.urls import url
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models.query import QuerySet
from django.http import Http404, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.list import MultipleObjectMixin

from django_object_actions.actions import BaseAction


class BaseDjangoObjectActions(object):
    """
    ModelAdmin mixin to add new actions just like adding admin actions.

    Attributes
    ----------
    model : django.db.models.Model
        The Django Model these actions work on. This is populated by Django.
    change_actions : list of str
        Write the names of the methods of the model admin that can be used as
        tools in the change view.
    changelist_actions : list of str
        Write the names of the methods of the model admin that can be used as
        tools in the changelist view.
    tools_view_name : str
        The name of the Django Object Actions admin view, including the 'admin'
        namespace. Populated by `_get_action_urls`.
    """
    change_actions = []
    changelist_actions = []
    tools_view_name = None

    # EXISTING ADMIN METHODS MODIFIED
    #################################

    def get_urls(self):
        """Prepend `get_urls` with our own patterns."""
        urls = super(BaseDjangoObjectActions, self).get_urls()
        return self._get_action_urls() + urls


    def _get_change_context(self, request, object_id, form_url=''):
        extra_context = {
            'objectactions': [
                self._get_tool_dict(action) for action in
                self.get_change_actions(request, object_id, form_url)
                ],
            'tools_view_name': self.tools_view_name,
        }
        return extra_context



    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = self._get_change_context(request, object_id, form_url='')
        return super(BaseDjangoObjectActions, self).change_view(
            request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update({
            'objectactions': [
                self._get_tool_dict(action) for action in
                self.get_changelist_actions(request)
                ],
            'tools_view_name': self.tools_view_name,
        })
        return super(BaseDjangoObjectActions, self).changelist_view(
            request, extra_context)

    # USER OVERRIDABLE
    ##################

    def get_change_actions(self, request, object_id, form_url):
        """
        Override this to customize what actions get to the change view.

        This takes the same parameters as `change_view`.

        For example, to restrict actions to superusers, you could do:

            class ChoiceAdmin(DjangoObjectActions, admin.ModelAdmin):
                def get_change_actions(self, request, **kwargs):
                    if request.user.is_superuser:
                        return super(ChoiceAdmin, self).get_change_actions(
                            request, **kwargs
                        )
                    return []
        """
        return self.change_actions

    def get_changelist_actions(self, request, queryset=None, form_url=''):
        """
        Override this to customize what actions get to the changelist view.
        """
        return self.changelist_actions

    # INTERNAL METHODS
    ##################
    def _get_base_url_name(self):
        try:
            model_name = self.model._meta.model_name
        except AttributeError:  # pragma: no cover
            # DJANGO15
            model_name = self.model._meta.module_name
        base_url_name = '%s_%s' % (self.model._meta.app_label, model_name)
        return base_url_name

    def _get_admin_namespace(self):
        return self.admin_site.name

    def _get_action_urls(self):
        """Get the url patterns that route each action to a view."""
        actions = {}

        # e.g.: polls_poll
        base_url_name = self._get_base_url_name()
        # e.g.: polls_poll_actions
        model_actions_url_name = '%s_actions' % base_url_name

        namespace = self._get_admin_namespace()
        self.tools_view_name = '%s:%s' % (namespace, model_actions_url_name)

        urls = [
            # change, supports pks that are numbers or uuids
            url(r'^(?P<pk>[0-9a-f\-]+)/actions/(?P<tool>\w+)/$',
                self.admin_site.admin_view(  # checks permissions
                    ChangeActionView.as_view(
                        model=self.model,
                        admin=self,
                        back='%s:%s_change' % (namespace, base_url_name),
                    )
                ),
                name=model_actions_url_name),
            # changelist
            url(r'^actions/(?P<tool>\w+)/$',
                self.admin_site.admin_view(  # checks permissions
                    ChangeListActionView.as_view(
                        model=self.model,
                        admin=self,
                        back='%s:%s_changelist' % (namespace, base_url_name),
                    )
                ),
                # Dupe name is fine. https://code.djangoproject.com/ticket/14259
                name=model_actions_url_name),
        ]

        for action in chain(self.change_actions, self.changelist_actions):
            if isinstance(action, BaseAction):
                urls.extend(action.get_patterns(base_url_name, admin=self))
        return urls

    def _get_tool_dict(self, tool_name):
        """Represents the tool as a dict with extra meta."""
        url = None
        if isinstance(tool_name, BaseAction):
            tool = tool_name
            tool_name = tool.get_url_name()
            url = tool.get_url

        elif callable(tool_name):
            tool = tool_name
            tool_name = tool.__name__
        else:
            tool = getattr(self, tool_name)

        standard_attrs, custom_attrs = self._get_button_attrs(tool)


        tool_data = dict(
            name=tool_name,
            url=url,
            label=getattr(tool, 'label', tool_name),
            standard_attrs=standard_attrs,
            custom_attrs=custom_attrs,
            method=tool,
        )
        return tool_data

    def _get_button_attrs(self, tool):
        """
        Get the HTML attributes associated with a tool.

        There are some standard attributes (class and title) that the template
        will always want. Any number of additional attributes can be specified
        and passed on. This is kinda awkward and due for a refactor for
        readability.
        """
        attrs = getattr(tool, 'attrs', {})
        # href is not allowed to be set. should an exception be raised instead?
        if 'href' in attrs:
            attrs.pop('href')
        # title is not allowed to be set. should an exception be raised instead?
        # `short_description` should be set instead to parallel django admin
        # actions
        if 'title' in attrs:
            attrs.pop('title')
        default_attrs = {
            'class': attrs.get('class', ''),
            'title': getattr(tool, 'short_description', ''),
        }
        standard_attrs = {}
        custom_attrs = {}
        for k, v in dict(default_attrs, **attrs).items():
            if k in default_attrs:
                standard_attrs[k] = v
            else:
                custom_attrs[k] = v
        return standard_attrs, custom_attrs


class DjangoObjectActions(BaseDjangoObjectActions):
    change_form_template = "django_object_actions/change_form.html"
    change_list_template = "django_object_actions/change_list.html"


class BaseActionView(View):
    """
    The view that runs a change/changelist action callable.

    Attributes
    ----------
    back : str
        The urlpattern name to send users back to. This is set in
        `_get_action_urls` and turned into a url with the `back_url` property.
    model : django.db.model.Model
        The model this tool operates on.
    actions : dict
        A mapping of action names to callables.
    """
    back = None
    model = None
    actions = None
    admin = None

    def get_actions(self):
        return self.actions or []

    @property
    def view_args(self):
        """
        tuple: The argument(s) to send to the action (excluding `request`).

        Change actions are called with `(request, obj)` while changelist
        actions are called with `(request, queryset)`.
        """
        raise NotImplementedError

    @property
    def back_url(self):
        """
        str: The url path the action should send the user back to.

        If an action does not return a http response, we automagically send
        users back to either the change or the changelist page.
        """
        raise NotImplementedError

    def get(self, request, tool, **kwargs):
        action_list = map(self.admin._get_tool_dict, self.get_actions(request, *self.view_args))
        action_map = {action['name']: action for action in action_list}

        try:
            action_info = action_map[tool]
        except KeyError:
            raise Http404('Action does not exist')
        view = action_info['method']

        ret = view(request, *self.view_args)
        if isinstance(ret, HttpResponseBase):
            return ret

        return HttpResponseRedirect(self.back_url)

    # HACK to allow POST requests too
    post = get

    def message_user(self, request, message):
        """
        Mimic Django admin actions's `message_user`.

        Like the second example:
        https://docs.djangoproject.com/en/1.9/ref/contrib/admin/actions/#custom-admin-action
        """
        messages.info(request, message)


class ChangeActionView(SingleObjectMixin, BaseActionView):
    def get_actions(self, request, obj):
        return self.admin.get_change_actions(request, obj.id, form_url='')

    @property
    def view_args(self):
        return (self.get_object(),)

    @property
    def back_url(self):
        return reverse(self.back, args=(self.kwargs['pk'],))


class ChangeListActionView(MultipleObjectMixin, BaseActionView):
    def get_actions(self, request, queryset):
        return self.admin.get_changelist_actions(request, queryset, form_url='')

    @property
    def view_args(self):
        return (self.get_queryset(),)

    @property
    def back_url(self):
        return reverse(self.back)


def takes_instance_or_queryset(func):
    """Decorator that makes standard Django admin actions compatible."""

    @wraps(func)
    def decorated_function(self, request, queryset):
        # func follows the prototype documented at:
        # https://docs.djangoproject.com/en/dev/ref/contrib/admin/actions/#writing-action-functions
        if not isinstance(queryset, QuerySet):
            try:
                # Django >=1.8
                queryset = self.get_queryset(request).filter(pk=queryset.pk)
            except AttributeError:
                try:
                    # Django >=1.6,<1.8
                    model = queryset._meta.model
                except AttributeError:  # pragma: no cover
                    # Django <1.6
                    model = queryset._meta.concrete_model
                queryset = model.objects.filter(pk=queryset.pk)
        return func(self, request, queryset)

    return decorated_function
