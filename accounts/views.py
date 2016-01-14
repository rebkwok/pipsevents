from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import IntegrityError
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404
from django.views.generic import UpdateView, CreateView
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from braces.views import LoginRequiredMixin

from allauth.account.views import LoginView

from accounts.forms import DisclaimerForm


def profile(request):
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

    return render(request, 'account/profile.html', {'disclaimer': disclaimer})


class ProfileUpdateView(LoginRequiredMixin, UpdateView):

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


class DisclaimerCreateView(LoginRequiredMixin, CreateView):

    form_class = DisclaimerForm
    template_name = 'account/disclaimer_form.html'

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            try:
                request.user.online_disclaimer
                return HttpResponseRedirect(reverse('disclaimer_form'))
            except ObjectDoesNotExist:
                pass
        return super(DisclaimerCreateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DisclaimerCreateView, self).get_context_data(**kwargs)

        try:
            self.request.user.online_disclaimer
            context['disclaimer'] = True
        except ObjectDoesNotExist:
            pass
        try:
            self.request.user.print_disclaimer
            context['disclaimer'] = True
        except ObjectDoesNotExist:
            pass

        return context

    def form_valid(self, form):
        disclaimer = form.save(commit=False)

        password = form.cleaned_data['password']
        if self.request.user.check_password(password):
            disclaimer.user = self.request.user
            disclaimer.save()
        else:
            messages.error(self.request, "Password is incorrect")
            form = DisclaimerForm(form.data)
            return render(self.request, self.template_name, {'form':form})

        return super(DisclaimerCreateView, self).form_valid(form)


    def get_success_url(self):
        return reverse('profile:profile')


def data_protection(request):
    return render(request, 'account/data_protection_statement.html')