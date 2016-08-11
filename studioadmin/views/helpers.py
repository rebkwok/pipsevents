import urllib

from functools import wraps

from django.core.cache import cache
from django.contrib.auth.models import Group
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect


def staff_required(func):
    def decorator(request, *args, **kwargs):
        cached_is_staff = cache.get('user_%s_is_staff' % str(request.user.id))
        if cached_is_staff is not None:
            user_is_staff = bool(cached_is_staff)
        else:
            user_is_staff = request.user.is_staff
            # cache for 30 mins
            cache.set(
                'user_%s_is_staff' % str(request.user.id), user_is_staff, 1800
            )

        if user_is_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


def is_instructor_or_staff(func):
    def decorator(request, *args, **kwargs):
        cached_is_instructor_or_staff = cache.get(
            'user_%s_is_instructor_or_staff' % str(request.user.id)
        )
        if cached_is_instructor_or_staff is not None:
            user_is_instructor_or_staff = bool(cached_is_instructor_or_staff)
        else:
            group = Group.objects.get(name='instructors')
            user_is_instructor_or_staff = request.user.is_staff \
                                          or group in request.user.groups.all()
            cache.set(
                'user_%s_is_instructor_or_staff' % str(request.user.id),
                user_is_instructor_or_staff, 1800
            )

        if user_is_instructor_or_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


class StaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        cached_is_staff = cache.get('user_%s_is_staff' % str(request.user.id))
        if cached_is_staff is not None:
            user_is_staff = bool(cached_is_staff)
        else:
            user_is_staff = self.request.user.is_staff
            cache.set(
                'user_%s_is_staff' % str(request.user.id), user_is_staff, 1800
            )
        if not user_is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(StaffUserMixin, self).dispatch(request, *args, **kwargs)


class InstructorOrStaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        cached_is_instructor_or_staff = cache.get(
            'user_%s_is_instructor_or_staff' % str(request.user.id)
        )
        if cached_is_instructor_or_staff is not None:
            user_is_instructor_or_staff = bool(cached_is_instructor_or_staff)
        else:
            group = Group.objects.get(name='instructors')
            user_is_instructor_or_staff = self.request.user.is_staff or \
                        group in self.request.user.groups.all()
            cache.set(
                'user_%s_is_instructor_or_staff' % str(request.user.id),
                user_is_instructor_or_staff, 1800
            )
        if user_is_instructor_or_staff:
            return super(
                InstructorOrStaffUserMixin, self
            ).dispatch(request, *args, **kwargs)
        return HttpResponseRedirect(reverse('booking:permission_denied'))


def url_with_querystring(path, **kwargs):
    return path + '?' + urllib.parse.urlencode(kwargs)

