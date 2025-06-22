import urllib

from functools import wraps

from django.core.cache import cache
from django.contrib.auth.models import Group
from django.urls import reverse
from django.shortcuts import HttpResponseRedirect
from django.core.paginator import EmptyPage, PageNotAnInteger


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


def set_cloned_name(cloning_cls, event_or_session, cloned_event_or_session):
    cloned_event_or_session.name = f"[CLONED] {event_or_session.name}"
    split_name = event_or_session.name.rsplit("_", 1)
    base_name = split_name[0]
    try:
        counter = int(split_name[1])
    except (ValueError, IndexError):
        counter = 1
    while cloning_cls.objects.filter(name=cloned_event_or_session.name).exists():
        cloned_event_or_session.name = f"{base_name}_{counter}"
        counter += 1


def get_page(request, paginator, page=None):
    page = page or request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        return paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        return paginator.page(paginator.num_pages)
