from django.shortcuts import render, HttpResponse, get_object_or_404
from django.views.generic import UpdateView
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from braces.views import LoginRequiredMixin

from allauth.account.views import LoginView

def profile(request):
    return render(request, 'account/profile.html')


class ProfileUpdateView(LoginRequiredMixin, UpdateView):

    model = User
    template_name = 'account/update_profile.html'
    fields = ('username', 'first_name', 'last_name',)

    def get_object(self):
        return get_object_or_404(User, username=self.request.user.username, email=self.request.user.email)

    def get_success_url(self):
        return reverse('profile:profile')


class CustomLoginView(LoginView):

    def get_context_data(self, **kwargs):
        context = super(CustomLoginView, self).get_context_data(**kwargs)

        next_redirect = self.request.POST.get('next') or self.request.GET.get('next')
        if next_redirect and next_redirect == '/accounts/password/change/':
            redirect_field_value = reverse('profile:profile')
            context.update({"redirect_field_value": redirect_field_value})

        return context
