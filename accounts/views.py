from requests import HTTPError

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib import messages
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404
from django.views.generic import UpdateView, CreateView
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe

from allauth.account.views import EmailView, LoginView

from braces.views import LoginRequiredMixin

from .forms import DisclaimerForm
from .utils import has_active_disclaimer, has_expired_disclaimer
from activitylog.models import ActivityLog
from common.mailchimp_utils import update_mailchimp


@login_required
def profile(request):
    disclaimer = has_active_disclaimer(request.user)
    expired_disclaimer = has_expired_disclaimer(request.user)

    return render(
        request, 'account/profile.html',
        {'disclaimer': disclaimer, 'expired_disclaimer': expired_disclaimer})


class ProfileUpdateView(LoginRequiredMixin, UpdateView):

    model = User
    template_name = 'account/update_profile.html'
    fields = ('username', 'first_name', 'last_name',)

    def get_object(self):
        return get_object_or_404(
            User, username=self.request.user.username,
            email=self.request.user.email
        )

    def get_success_url(self):
        return reverse('profile:profile')

    def form_valid(self, form):
        first_name_changed = 'first_name' in form.changed_data
        last_name_changed = 'last_name' in form.changed_data

        if first_name_changed or last_name_changed:
            update_mailchimp(form.instance, 'update_profile')
            ActivityLog.objects.create(
                log='User profile changed for {} ({}); MailChimp list updated '
                    'with new first/last name'.format(
                    form.instance.username, form.instance.email
                )
            )
        return super(ProfileUpdateView, self).form_valid(form)


class CustomLoginView(LoginView):

    def get_success_url(self):
        super(CustomLoginView, self).get_success_url()
        ret = self.request.POST.get('next') or self.request.GET.get('next')
        if not ret or ret in [
            '/accounts/password/change/', '/accounts/password/set/'
        ]:
            ret = reverse('profile:profile')

        return ret


class CustomEmailView(EmailView):

    def post(self, request, *args, **kwargs):
        old_email = request.user.email
        res = super(CustomEmailView, self).post(request, *args, **kwargs)

        if res.status_code == 302 and res.url == self.success_url and \
                request.POST.get("email") and "action_primary" in request.POST:
            update_mailchimp(request.user, 'update_email', old_email=old_email)
            ActivityLog.objects.create(
                log='Primary email changed to {} for {} {} ({}); MailChimp list '
                    'updated.'.format(
                    request.user.email, request.user.first_name,
                    request.user.last_name, request.user.username
                )
            )
        return res

custom_email_view = login_required(CustomEmailView.as_view())


class DisclaimerCreateView(LoginRequiredMixin, CreateView):

    form_class = DisclaimerForm
    template_name = 'account/disclaimer_form.html'

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            if has_active_disclaimer(request.user):
                return HttpResponseRedirect(reverse('disclaimer_form'))
        return super(DisclaimerCreateView, self).dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        context = super(DisclaimerCreateView, self).get_context_data(**kwargs)

        context['disclaimer'] = has_active_disclaimer(self.request.user)
        context['expired_disclaimer'] = has_expired_disclaimer(
            self.request.user
        )

        return context

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(DisclaimerCreateView, self).get_form_kwargs(**kwargs)
        form_kwargs["user"] = self.request.user
        return form_kwargs

    def form_valid(self, form):
        disclaimer = form.save(commit=False)

        password = form.cleaned_data['password']
        if not self.request.user.has_usable_password():
            messages.error(
                self.request,
                mark_safe(
                    "No password set on account.  "
                    "Please <a href='{}'>set a password</a> before "
                    "completing the disclaimer form.".format(
                        reverse('account_set_password')
                    )
                )
            )
            form = DisclaimerForm(form.data, user=self.request.user)
            return render(self.request, self.template_name, {'form':form})

        if self.request.user.check_password(password):
            disclaimer.user = self.request.user
            disclaimer.save()
        else:
            messages.error(self.request, "Password is incorrect")
            form = DisclaimerForm(form.data, user=self.request.user)
            return render(self.request, self.template_name, {'form':form})

        return super(DisclaimerCreateView, self).form_valid(form)

    def get_success_url(self):
        return reverse('profile:profile')


def data_protection(request):
    return render(request, 'account/data_protection_statement.html')


@login_required
def subscribe_view(request):

    if request.method == 'POST':
        group = Group.objects.get(name='subscribed')
        if 'subscribe' in request.POST:
            group.user_set.add(request.user)
            messages.success(
                request, 'You have been subscribed to the mailing list'
            )
            ActivityLog.objects.create(
                log='User {} {} ({}) has subscribed to the mailing list'.format(
                    request.user.first_name, request.user.last_name,
                    request.user.username
                )
            )
            update_mailchimp(request.user, 'subscribe')
            ActivityLog.objects.create(
                log='User {} {} ({}) has been subscribed to MailChimp'.format(
                    request.user.first_name, request.user.last_name,
                    request.user.username
                )
            )
        elif 'unsubscribe' in request.POST:
            group.user_set.remove(request.user)
            messages.success(request, 'You have been unsubscribed from the mailing list')
            ActivityLog.objects.create(
                log='User {} {} ({}) has unsubscribed from the mailing list'.format(
                    request.user.first_name, request.user.last_name,
                    request.user.username
                )
            )
            update_mailchimp(request.user, 'unsubscribe')
            ActivityLog.objects.create(
                log='User {} {} ({}) has been unsubscribed from MailChimp'.format(
                    request.user.first_name, request.user.last_name,
                    request.user.username
                )
            )

    return TemplateResponse(
        request, 'account/mailing_list_subscribe.html'
    )
