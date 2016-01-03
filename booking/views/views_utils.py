from django.contrib.auth.models import Permission
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect

from accounts.models import Disclaimer


class DisclaimerRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has a disclaimer saved and add the permission
        # if not already assigned
        if not request.user.has_perm("booking.has_signed_disclaimer"):
            try:
                Disclaimer.objects.get(user=request.user)
                perm = Permission.objects.get(codename='has_signed_disclaimer')
                request.user.user_permissions.add(perm)
            except Disclaimer.DoesNotExist:
                return HttpResponseRedirect(reverse('booking:permission_denied'))

        return super(DisclaimerRequiredMixin, self).dispatch(request, *args, **kwargs)


class DisclaimerMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has a disclaimer saved and add the permission
        # if not already assigned
        if not request.user.is_anonymous() and not \
                request.user.has_perm("booking.has_signed_disclaimer"):
            try:
                Disclaimer.objects.get(user=request.user)
                perm = Permission.objects.get(codename='has_signed_disclaimer')
                request.user.user_permissions.add(perm)
            except Disclaimer.DoesNotExist:
                pass

        return super(DisclaimerMixin, self).dispatch(request, *args, **kwargs)