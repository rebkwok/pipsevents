from sqlite3 import IntegrityError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404
from django.views.generic import UpdateView, CreateView, FormView
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_variables, sensitive_post_parameters
from django.contrib.auth.models import User
from django.urls import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe

from allauth.account.views import EmailView, LoginView

from braces.views import LoginRequiredMixin

from .forms import DisclaimerForm, DataPrivacyAgreementForm, NonRegisteredDisclaimerForm, UserProfileForm
from .models import CookiePolicy, DataPrivacyPolicy, SignedDataPrivacy, active_data_privacy_cache_key, active_disclaimer_cache_key, \
    has_active_data_privacy_agreement, has_active_disclaimer, has_expired_disclaimer
from activitylog.models import ActivityLog
from booking.email_helpers import send_mail
from common.mailchimp_utils import update_mailchimp


@login_required
def profile(request):
    # don't use the cache here as sometimes just after completing a disclaimer
    # we seem to miss the cache
    disclaimer = any(
        [
            True for od in list(request.user.online_disclaimer.all())
            if od.is_active
        ]
    )
    if not disclaimer and hasattr(request.user, "print_disclaimer"):
        disclaimer = request.user.print_disclaimer.is_active
    expired_disclaimer = has_expired_disclaimer(request.user)

    return render(
        request, 'account/profile.html',
        {'disclaimer': disclaimer, 'expired_disclaimer': expired_disclaimer})


class ProfileUpdateView(LoginRequiredMixin, UpdateView):

    model = User
    form_class = UserProfileForm
    template_name = 'account/update_profile.html'

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
        if (first_name_changed or last_name_changed) and form.instance.subscribed():
            update_mailchimp(form.instance, 'update_profile')
            ActivityLog.objects.create(
                log='User profile changed for {} ({}); MailChimp list updated '
                    'with new first/last name'.format(
                    form.instance.username, form.instance.email
                )
            )
        user = form.save()
        if 'pronouns' in form.changed_data:
            user.userprofile.pronouns = form.cleaned_data["pronouns"]
            user.userprofile.save()
        return super().form_valid(form)


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

    @method_decorator(sensitive_post_parameters())
    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST' and not request.user.is_anonymous:
            if has_active_disclaimer(request.user):
                return HttpResponseRedirect(reverse('profile:profile'))
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

    @method_decorator(sensitive_variables("password"))
    def form_valid(self, form):
        disclaimer = form.save(commit=False)
        disclaimer.version = form.disclaimer_content.version
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

        if not self.request.user.check_password(password):
            form = DisclaimerForm(form.data, user=self.request.user)
            return render(self.request, self.template_name, {'form':form, 'password_error': 'Password is incorrect'})
        disclaimer.user = self.request.user
        disclaimer.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('profile:profile')


class NonRegisteredDisclaimerCreateView(CreateView):

    form_class = NonRegisteredDisclaimerForm
    template_name = 'account/nonregistered_disclaimer_form.html'

    @method_decorator(sensitive_variables("disclaimer", "email"))
    def form_valid(self, form):
        # email user
        disclaimer = form.save(commit=False)
        disclaimer.version = form.disclaimer_content.version
        email = disclaimer.email
        host = 'https://{}'.format(self.request.META.get('HTTP_HOST'))
        ctx = {
            'host': host,
            'contact_email': settings.DEFAULT_STUDIO_EMAIL
        }
        send_mail('{} Disclaimer recevied'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            get_template('account/email/nonregistered_disclaimer_received.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [email],
            html_message=get_template(
                'account/email/nonregistered_disclaimer_received.html').render(ctx),
            fail_silently=False)
        disclaimer.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('nonregistered_disclaimer_submitted')


def nonregistered_disclaimer_submitted(request):
    return render(request, 'account/nonregistered_disclaimer_created.html')


def data_privacy_policy(request):
    return render(
        request, 'account/data_privacy_policy.html',
        {'data_privacy_policy': DataPrivacyPolicy.current(),
         'cookie_policy': CookiePolicy.current()}
    )


def cookie_policy(request):
    return render(
        request, 'account/cookie_policy.html',
        {'cookie_policy': CookiePolicy.current()}
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


class SignedDataPrivacyCreateView(LoginRequiredMixin, FormView):
    template_name = 'account/data_privacy_review.html'
    form_class = DataPrivacyAgreementForm

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated and \
                has_active_data_privacy_agreement(self.request.user):
            return HttpResponseRedirect(
                self.request.GET.get('next', reverse('booking:lessons'))
            )
        return super().dispatch(*args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['next_url'] = self.request.GET.get('next')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        update_needed = (
            SignedDataPrivacy.objects.filter(
                user=self.request.user,
                version__lt=DataPrivacyPolicy.current_version()
            ).exists() and not has_active_data_privacy_agreement(
                self.request.user)
        )

        context.update({
            'data_protection_policy': DataPrivacyPolicy.current(),
            'update_needed': update_needed
        })
        return context

    def form_valid(self, form):        
        user = self.request.user
        
        try:
            SignedDataPrivacy.objects.create(
                user=user, version=form.data_privacy_policy.version
            )
        except IntegrityError:
            cache.set(
                active_data_privacy_cache_key(self.user), True, timeout=600
            )
            return HttpResponseRedirect(self.get_success_url(form))

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
        return HttpResponseRedirect(self.get_success_url(form))

    def get_success_url(self, form=None):
        if form and form.next_url:
            return form.next_url
        return reverse('booking:lessons')
