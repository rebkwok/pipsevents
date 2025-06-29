from django.urls import path

from studioadmin.views import stats


urlpatterns = [
    path("", stats.view_stats, name="stats"),
    path("filter-options/", stats.view_filter_options, name="filter_options"),
    path("memberships/", stats.view_memberships_types, name="memberships"),
    path("users-by-age/", stats.view_users_by_age, name="users_by_age"),
    path("users-booked-past-month/", stats.view_new_users_booked_in_past_month, name="new_users_booked_in_past_month"),
    path("bookings/<int:year>/", stats.view_bookings_count, name="bookings_count"),
    path("scheduled-events/<int:year>/", stats.view_events_count, name="events_count"),
    path("users/<int:year>/", stats.view_new_user_registration, name="new_user_registration"),
    path("cumulative-users/", stats.view_cumulative_user_registrations, name="cumulative_user_registrations"),
    path("payment-methods/<int:year>/<str:event_types>/", stats.view_payment_methods, name="payment_methods"),
    path("pct-bookings/<int:year>/", stats.view_pct_bookings_per_class, name="pct_bookings_per_class"),
    path("pct-waiting-list/<int:year>/", stats.view_pct_events_with_waiting_list, name="pct_events_with_waiting_list"),
    path("no-shows/<int:year>/", stats.view_average_no_show_per_class, name="average_no_show_per_class"),
    path("late-cancellations/<int:year>/", stats.view_average_late_cancellation_per_class, name="average_late_cancellation_per_class")
]