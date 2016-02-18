import urllib

from functools import wraps

from django.contrib.auth.models import Group
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect


def staff_required(func):
    def decorator(request, *args, **kwargs):
        if request.user.is_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


def is_instructor_or_staff(func):
    def decorator(request, *args, **kwargs):
        group = Group.objects.get(name='instructors')
        if request.user.is_staff or group in request.user.groups.all():
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


class StaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(StaffUserMixin, self).dispatch(request, *args, **kwargs)


class InstructorOrStaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        group = Group.objects.get(name='instructors')
        if self.request.user.is_staff or \
                        group in self.request.user.groups.all():
            return super(
                InstructorOrStaffUserMixin, self
            ).dispatch(request, *args, **kwargs)
        return HttpResponseRedirect(reverse('booking:permission_denied'))


def url_with_querystring(path, **kwargs):
    return path + '?' + urllib.parse.urlencode(kwargs)

