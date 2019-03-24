import datetime
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from django.contrib import messages
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.urls import reverse
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, Http404
from django.views.generic import UpdateView, DeleteView, ListView
from django.utils import timezone

from accounts.models import OnlineDisclaimer, NonRegisteredDisclaimer
from studioadmin.forms import StudioadminDisclaimerForm, DisclaimerUserListSearchForm
from studioadmin.utils import str_int, dechaffify
from studioadmin.views.helpers import is_instructor_or_staff, \
    InstructorOrStaffUserMixin, StaffUserMixin

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@is_instructor_or_staff
def user_disclaimer(request, encoded_user_id):
    # get last disclaimer for this user
    user_id = dechaffify(str_int(encoded_user_id))

    disclaimer = OnlineDisclaimer.objects.filter(user__id=user_id).last()

    ctx = {'disclaimer': disclaimer, 'encoded_user_id': encoded_user_id}

    return TemplateResponse(
        request, "studioadmin/user_disclaimer.html", ctx
    )


class DisclaimerUpdateView(StaffUserMixin, UpdateView):

    model = OnlineDisclaimer
    form_class = StudioadminDisclaimerForm
    template_name = 'studioadmin/update_user_disclaimer.html'

    def get_object(self):
        encoded_user_id = self.kwargs.get('encoded_user_id')
        user_id = dechaffify(str_int(encoded_user_id))
        obj = OnlineDisclaimer.objects.filter(user__id=user_id).last()
        return obj if obj else Http404

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(
            DisclaimerUpdateView, self
        ).get_form_kwargs(**kwargs)
        form_kwargs["user"] = self.object.user
        return form_kwargs

    def get_context_data(self, **kwargs):
        context = super(DisclaimerUpdateView, self).get_context_data(**kwargs)
        user = self.get_object().user
        context['user'] = user
        return context

    def form_valid(self, form):
        changed = form.changed_data
        if 'dob' in form.changed_data:
            old = OnlineDisclaimer.objects.get(id=self.object.id)
            if old.dob == form.instance.dob:
                changed.remove('dob')
        if 'password' in form.changed_data:
             changed.remove('password')

        if changed:
            disclaimer = form.save(commit=False)
            password = form.cleaned_data['password']
            if disclaimer.user.check_password(password):
                disclaimer.date_updated = timezone.now()
                disclaimer.save()
                messages.success(
                    self.request,
                    "Disclaimer for {} has been updated".format(
                        disclaimer.user.username
                    )
                )
                ActivityLog.objects.create(
                    log="Online disclaimer for {} updated by admin "
                        "user {} (user password supplied)".format(
                        disclaimer.user.username, self.request.user.username
                    )
                )
            else:
                messages.error(self.request, "Password is incorrect")
                form = StudioadminDisclaimerForm(
                    form.data, user=disclaimer.user
                )
                return TemplateResponse(
                    self.request, self.template_name, {'form': form}
                )
        else:
            messages.info(self.request, "No changes made")

        return super(DisclaimerUpdateView, self).form_valid(form)

    def get_success_url(self):
        return reverse('studioadmin:users')


class DisclaimerDeleteView(StaffUserMixin, DeleteView):

    model = OnlineDisclaimer
    fields = '__all__'
    template_name = 'studioadmin/delete_user_disclaimer.html'

    def dispatch(self, *args, **kwargs):
        encoded_user_id = self.kwargs.get('encoded_user_id')
        user_id = dechaffify(str_int(encoded_user_id))
        self.user = User.objects.get(id=user_id)
        return super(DisclaimerDeleteView, self).dispatch(*args, **kwargs)

    def get_object(self):
        return get_object_or_404(OnlineDisclaimer, user=self.user)

    def get_context_data(self, **kwargs):
        context = super(DisclaimerDeleteView, self).get_context_data(**kwargs)
        context['user'] = self.user
        return context

    def get_success_url(self):
        messages.success(
            self.request, "Disclaimer deleted for {} {} ({})".format(
                self.user.first_name, self.user.last_name, self.user.username
            )
        )
        ActivityLog.objects.create(
            log="Disclaimer deleted for {} {} ({}) by admin user {}".format(
                self.user.first_name, self.user.last_name, self.user.username,
                self.request.user.username
            )
        )
        return reverse('studioadmin:users')


class NonRegisteredDisclaimersListView(InstructorOrStaffUserMixin, ListView):

    model = NonRegisteredDisclaimer
    fields = '__all__'
    template_name = 'studioadmin/non_registered_disclaimer_list.html'
    context_object_name = 'disclaimers'
    paginate_by = 30

    def get_queryset(self):
        queryset = super().get_queryset()
        reset = self.request.GET.get('reset')
        search_submitted = self.request.GET.get('search_submitted')
        search_text = self.request.GET.get('search')
        search_date = self.request.GET.get('search_date')
        if reset or (search_submitted and not search_text and not search_date) or (not reset and not search_submitted):
            pass
        else:
            if search_text:
                queryset = queryset.annotate(search=SearchVector('first_name', 'last_name')).filter(search=search_text)
            if search_date:
                search_date = datetime.datetime.strptime(search_date, '%d-%b-%Y').date()
                queryset = queryset.filter(event_date=search_date)
        return queryset

    def get_context_data(self):
        context = super().get_context_data()
        context['sidenav_selection'] = 'users'
        context['search_submitted'] = self.request.GET.get('search_submitted')
        search_date = self.request.GET.get('search_date', '')
        search_text = self.request.GET.get('search',  '')
        reset = self.request.GET.get('reset')

        if reset:
            search_text = ''
        form = DisclaimerUserListSearchForm(initial={'search': search_text, 'search_date': search_date})
        context['form'] = form
        return context


@login_required
@is_instructor_or_staff
def nonregistered_disclaimer(request, user_uuid):
    disclaimer = get_object_or_404(NonRegisteredDisclaimer, user_uuid=user_uuid)

    ctx = {'disclaimer': disclaimer}

    return TemplateResponse(
        request, "studioadmin/non_registered_disclaimer.html", ctx
    )
