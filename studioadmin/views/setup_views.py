from django.views.generic import ListView

from braces.views import LoginRequiredMixin

from booking.models import AllowedGroup, EventType
from studioadmin.views.helpers import StaffUserMixin


class EventTypeListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = EventType
    template_name = 'studioadmin/setup_event_types.html'
    context_object_name = 'event_types'
    
    def get_queryset(self):
        return EventType.objects.visible()
    

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sidenav_selection"] = "event_types"
        return context
    

class AllowedGroupListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = AllowedGroup
    template_name = 'studioadmin/setup_allowed_groups.html'
    context_object_name = 'allowed_groups'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sidenav_selection"] = "allowed_groups"
        return context