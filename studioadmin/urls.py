from django.conf.urls import patterns, url
from django.views.generic import RedirectView
from studioadmin.views import (ConfirmRefundView,
                               ConfirmPaymentView,
                               EventAdminUpdateView,
                               EventAdminCreateView,
                               TimetableListView,
                               TimetableSessionDetailView)


urlpatterns = patterns('',
    url(r'^confirm-payment/(?P<pk>\d+)/$', ConfirmPaymentView.as_view(),
        name='confirm-payment'),
    url(r'^confirm-refunded/(?P<pk>\d+)/$', ConfirmRefundView.as_view(),
        name='confirm-refund'),
    url(r'^register/(?P<event_slug>[\w-]+)/$',
        'studioadmin.views.register_view',
        name='register'),
    url(r'^register/(?P<event_slug>[\w-]+)/(?P<status_choice>[\w-]+)$',
        'studioadmin.views.register_view',
        name='register'),
    url(r'^events/(?P<slug>[\w-]+)/$', EventAdminUpdateView.as_view(),
        name='edit_event'),
    url(r'^events/$', 'studioadmin.views.event_admin_list',
        {'ev_type': 'events'}, name='events'),
    # url(r'^events/new/$', EventAdminCreateView(), name='add_event'),
    url(r'^classes/(?P<slug>[\w-]+)/$', EventAdminUpdateView.as_view(),
        name='edit_lesson'),
    url(r'^classes/$', 'studioadmin.views.event_admin_list',
        {'ev_type': 'lessons'}, name='lessons'),
    # url(r'^classes/new/$', EventAdminCreateView(), name='add_lesson'),
    url(r'^$', RedirectView.as_view(url='/studioadmin/classes/', permanent=True)),
    )
