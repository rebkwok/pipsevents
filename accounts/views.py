from django.shortcuts import render, HttpResponse, get_object_or_404
from django.views.generic import UpdateView, CreateView
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from braces.views import LoginRequiredMixin

from allauth.account.views import LoginView

from accounts.forms import DisclaimerForm

from booking.views.views_utils import DisclaimerMixin


def profile(request):
    return render(request, 'account/profile.html')


class ProfileUpdateView(DisclaimerMixin, LoginRequiredMixin, UpdateView):

    model = User
    template_name = 'account/update_profile.html'
    fields = ('username', 'first_name', 'last_name',)

    def get_object(self):
        return get_object_or_404(User, username=self.request.user.username, email=self.request.user.email)

    def get_success_url(self):
        return reverse('profile:profile')


class CustomLoginView(LoginView):

    def get_success_url(self):
        super(CustomLoginView, self).get_success_url()

        ret = self.request.POST.get('next') or self.request.GET.get('next')
        if not ret or ret == '/accounts/password/change/':
            ret = reverse('profile:profile')

        return ret


class DisclaimerCreateView(DisclaimerMixin, CreateView):

    form_class = DisclaimerForm
    template_name = 'account/disclaimer_form.html'


    def form_valid(self, form):

        disclaimer = form.save(commit=False)
        disclaimer.user = self.request.user
        disclaimer.save()

        disclaimer_perm = Permission.objects.get(codename="has_signed_disclaimer")
        self.request.user.user_permissions.add(disclaimer_perm)

        return super(DisclaimerCreateView, self).form_valid(form)


    def get_success_url(self):
        return reverse('profile:profile')
