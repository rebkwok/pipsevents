from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib import messages
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404
from django.views.generic import UpdateView, CreateView, FormView
from django.contrib.auth.models import User
from django.urls import reverse
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe

from allauth.account.views import EmailView, LoginView

from braces.views import LoginRequiredMixin

from .forms import DisclaimerForm, DataProtectionAgreementForm
from .models import DataProtectionPolicy, SignedDataProtection
from .utils import has_active_data_protection_agreement, \
    has_active_disclaimer, has_expired_disclaimer
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

        # update mailchimp only for a change in primary email, and only if
        # the change succeeded
        if request.POST.get("email") and "action_primary" in request.POST \
                and request.user.email != old_email:
            if request.user.subscribed():
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
    return render(
        request, 'account/data_protection_statement.html',
        {'data_protection_policy': DataProtectionPolicy.current()}
    )


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



class SignedDataProtectionCreateView(LoginRequiredMixin, FormView):
    template_name = 'account/data_protection_review.html'
    form_class = DataProtectionAgreementForm

    def dispatch(self, *args, **kwargs):
        if has_active_data_protection_agreement(self.request.user):
            return HttpResponseRedirect(
                self.request.GET.get('next', reverse('booking:lessons'))
            )
        return super(SignedDataProtectionCreateView, self).dispatch(*args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(SignedDataProtectionCreateView, self).get_form_kwargs()
        kwargs['next_url'] = self.request.GET.get('next')
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        update_needed = (
            SignedDataProtection.objects.filter(
                user=self.request.user,
                content_version__lt=DataProtectionPolicy.current_version()
            ).exists() and not has_active_data_protection_agreement(
                self.request.user)
        )

        context.update({
            'data_protection_policy': DataProtectionPolicy.current(),
            'update_needed': update_needed
        })
        return context

    def form_valid(self, form):        
        user = self.request.user
        SignedDataProtection.objects.create(
            user=user, content_version=form.data_protection_policy.version
        )

        mailing_list = form.cleaned_data.get('mailing_list') == 'yes'

        group = Group.objects.get(name='subscribed')
        if mailing_list and not user.subscribed():
            # add user to mailing list
            group.user_set.add(user)
            ActivityLog.objects.create(
                log='User {} {} ({}) has subscribed to the mailing list'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )
            update_mailchimp(user, 'subscribe')
            ActivityLog.objects.create(
                log='User {} {} ({}) has been subscribed to MailChimp'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )

        if not mailing_list and user.subscribed():
            # remove subscribed user from mailing list
            group.user_set.remove(user)
            ActivityLog.objects.create(
                log='User {} {} ({}) has unsubscribed from the mailing list'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )
            update_mailchimp(user, 'unsubscribe')
            ActivityLog.objects.create(
                log='User {} {} ({}) has been unsubscribed from MailChimp'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )
        next_url = form.next_url or reverse('booking:lessons')
        return self.get_success_url(next_url)

    def get_success_url(self, next):
        return HttpResponseRedirect(next)



