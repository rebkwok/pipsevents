import urllib

from functools import wraps

from django.core.cache import cache
from django.contrib.auth.models import Group
from django.urls import reverse
from django.shortcuts import HttpResponseRedirect


def staff_required(func):
    def decorator(request, *args, **kwargs):
        # cached_is_staff = cache.get('user_%s_is_staff' % str(request.user.id))
        # if cached_is_staff is not None:
        #     user_is_staff = bool(cached_is_staff)
        # else:
        #     user_is_staff = request.user.is_staff
        #     # cache for 30 mins
        #     cache.set(
        #         'user_%s_is_staff' % str(request.user.id), user_is_staff, 1800
        #     )
        user_is_staff = request.user.is_staff
        if user_is_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


def _is_instructor_or_staff(user):
    # user_is_instructor_or_staff = cache.get(
    #         'user_%s_is_instructor_or_staff' % str(user.id)
    #     )
    # if user_is_instructor_or_staff is None:
    #     group = Group.objects.get(name='instructors')
    #     user_is_instructor_or_staff = user.is_staff or \
    #                 group in user.groups.all()
    #     cache.set(
    #         'user_%s_is_instructor_or_staff' % str(user.id),
    #         user_is_instructor_or_staff, 1800
    #     )
    group = Group.objects.get(name='instructors')
    user_is_instructor_or_staff = user.is_staff or group in user.groups.all()
    return user_is_instructor_or_staff


def _can_view_event_disclaimers(user):
    # cached_can_view_event_disclaimers = cache.get(
    #         'user_%s_can_view_event_disclaimers' % str(user.id)
    #     )
    # if cached_can_view_event_disclaimers is not None:
    #     return bool(cached_can_view_event_disclaimers)

    # is_instructor_or_staff = _is_instructor_or_staff(user)
    # if is_instructor_or_staff:
    #     user_can_view_event_disclaimers = True
    # else:
    #     user_can_view_event_disclaimers = user.has_perm("accounts.view_nonregistereddisclaimer")
    #     cache.set(
    #         'user_%s_can_view_event_disclaimers' % str(user.id),
    #         user_can_view_event_disclaimers, 1800
    #     )
    is_instructor_or_staff = _is_instructor_or_staff(user)
    if is_instructor_or_staff:
        user_can_view_event_disclaimers = True
    else:
        user_can_view_event_disclaimers = user.has_perm("accounts.view_nonregistereddisclaimer")
    return user_can_view_event_disclaimers


def is_instructor_or_staff(func):
    def decorator(request, *args, **kwargs):
        if _is_instructor_or_staff(request.user):
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


def can_view_event_disclaimers(func):
    def decorator(request, *args, **kwargs):
        if _can_view_event_disclaimers(request.user):
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


class StaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # cached_is_staff = cache.get('user_%s_is_staff' % str(request.user.id))
        # if cached_is_staff is not None:
        #     user_is_staff = bool(cached_is_staff)
        # else:
        #     user_is_staff = self.request.user.is_staff
        #     cache.set(
        #         'user_%s_is_staff' % str(request.user.id), user_is_staff, 1800
        #     )
        user_is_staff = self.request.user.is_staff
        if not user_is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(StaffUserMixin, self).dispatch(request, *args, **kwargs)


class InstructorOrStaffUserMixin:

    def _has_permission(self, request):
        return _is_instructor_or_staff(request.user)

    def dispatch(self, request, *args, **kwargs):
        if self._has_permission(request):
            return super(
                InstructorOrStaffUserMixin, self
            ).dispatch(request, *args, **kwargs)
        return HttpResponseRedirect(reverse('booking:permission_denied'))


class CanViewNonRegisteredDIsclaimersMixin(InstructorOrStaffUserMixin):
    
    def _has_permission(self, request):
        return _can_view_event_disclaimers(request.user)


def url_with_querystring(path, **kwargs):
    return path + '?' + urllib.parse.urlencode(kwargs)

