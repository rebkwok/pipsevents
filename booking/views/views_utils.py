from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect


class DisclaimerRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has a disclaimer

        disclaimer = False
        try:
            request.user.online_disclaimer
            disclaimer = True
        except ObjectDoesNotExist:
            pass

        try:
            request.user.print_disclaimer
            disclaimer = True
        except ObjectDoesNotExist:
            pass

        if not disclaimer:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(DisclaimerRequiredMixin, self).dispatch(request, *args, **kwargs)
