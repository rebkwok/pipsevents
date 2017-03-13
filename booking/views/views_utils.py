from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect

from accounts.utils import has_active_disclaimer


class DisclaimerRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has an active disclaimer
        if not has_active_disclaimer(request.user):
            return HttpResponseRedirect(reverse('booking:disclaimer_required'))
        return super(DisclaimerRequiredMixin, self).dispatch(request, *args, **kwargs)
