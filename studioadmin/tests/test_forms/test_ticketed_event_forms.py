# -*- coding: utf-8 -*-
import pytz

from model_bakery import baker

from django.conf import settings
from django.test import TestCase

from booking.models import TicketBooking, TicketedEvent
from payments.models import PaypalTicketBookingTransaction
from studioadmin.forms import TicketedEventAdminForm, TicketedEventFormSet, \
    TicketBookingInlineFormSet, PrintTicketsForm


class TicketedEventAdminFormTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')

    def form_data(self, extra_data={}):
        data = {
            'name': 'test_ticketed_event',
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'location': 'Watermelon Studio',
            'ticket_cost': 0,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        form = TicketedEventAdminForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    def test_form_with_invalid_contact_person(self):
        form = TicketedEventAdminForm(data=self.form_data({'contact_person': ''}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_person', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

    def test_form_with_invalid_contact_email(self):
        form = TicketedEventAdminForm(
            data=self.form_data({'contact_email': ''}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

        form = TicketedEventAdminForm(
            data=self.form_data({'contact_email': 'test_email'}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['Enter a valid email address.'], form.errors.values())

    def test_invalid_date(self):
        form = TicketedEventAdminForm(
            data=self.form_data({'date': '15 Jun 2015 25:00'})
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid date format', str(form.errors['date']))

    def test_invalid_payment_due_date(self):
        form = TicketedEventAdminForm(
            data=self.form_data({'payment_due_date': '31 Jun 2015'})
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid date format', str(form.errors['payment_due_date']))

    def test_payment_due_date_after_event_date(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 20:00',
                 'payment_due_date': '16 Jun 2015'},
            ))
        self.assertFalse(form.is_valid())
        self.assertIn('Payment due date must be before event date', str(form.errors['payment_due_date']))

    def test_valid_payment_due_date(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 20:00',
                 'ticket_cost': 10,
                 'advance_payment_required': True,
                 'payment_due_date': '10 Jun 2015'},
            ))
        self.assertTrue(form.is_valid())

    def test_extra_ticket_info_required(self):
        """
        If extra ticket info required or help text specified, label must be
        provided
        :return:
        """
        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info_label': 'Test data'},
            ))
        self.assertTrue(form.is_valid())

        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info_required': True},
            ))
        self.assertFalse(form.is_valid())
        self.assertIn('Provide a label for this extra ticket info field',
                      str(form.errors['extra_ticket_info_required']))

        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info_help': "Test help text"},
            ))
        self.assertFalse(form.is_valid())
        self.assertIn('Provide a label for this extra ticket info field',
                      str(form.errors['extra_ticket_info_help']))

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'extra_ticket_info_label': 'Test data',
                    'extra_ticket_info_required': True
                },
            )
        )
        self.assertTrue(form.is_valid())

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'extra_ticket_info_label': 'Test data',
                    'extra_ticket_info_help': "Test help text"
                },
            )
        )
        self.assertTrue(form.is_valid())


    def test_extra_ticket_info1_required(self):
        """
        If extra ticket info required or help text specified, label must be
        provided
        :return:
        """
        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info1_label': 'Test data'},
            ))
        self.assertTrue(form.is_valid())

        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info1_required': True},
            ))
        self.assertFalse(form.is_valid())
        self.assertIn('Provide a label for this extra ticket info field',
                      str(form.errors['extra_ticket_info1_required']))

        form = TicketedEventAdminForm(
            data=self.form_data(
                {'extra_ticket_info1_help': "Test help text"},
            ))
        self.assertFalse(form.is_valid())
        self.assertIn('Provide a label for this extra ticket info field',
                      str(form.errors['extra_ticket_info1_help']))

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'extra_ticket_info1_label': 'Test data',
                    'extra_ticket_info1_required': True
                },
            )
        )
        self.assertTrue(form.is_valid())

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'extra_ticket_info1_label': 'Test data',
                    'extra_ticket_info1_help': "Test help text"
                },
            )
        )
        self.assertTrue(form.is_valid())

    def test_adv_payment_req_requires_either_due_date_or_payment_time(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'ticket_cost': 1,
                },
            ))
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please provide either a payment due date or payment time allowed',
            str(form.errors['advance_payment_required'])
        )

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_due_date': '30 Jun 2015',
                    'payment_time_allowed': 4,
                    'ticket_cost': 1,
                },
            ))
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please provide either a payment due date or payment time '
            'allowed (but not both)',
            str(form.errors['payment_due_date'])
        )
        self.assertIn(
            'Please provide either a payment due date or payment time '
            'allowed (but not both)',
            str(form.errors['payment_time_allowed'])
        )

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_due_date': '01 Jun 2015',
                    'ticket_cost': 1,
                },
            ))
        self.assertTrue(form.is_valid())

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_time_allowed': 4,
                    'ticket_cost': 1,
                },
            ))
        self.assertTrue(form.is_valid())

    def test_payment_due_date_requires_advance_payment_req(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_due_date': '01 Jun 2015',
                    'ticket_cost': 1,
                },
            )
        )
        self.assertFalse(form.is_valid())

        self.assertIn(
            'To specify a payment due date, please also tick '
            '&quot;advance payment required&quot',
            str(form.errors['payment_due_date'])
        )

    def test_payment_time_allowed_requires_advance_payment_req(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_time_allowed': 4,
                    'ticket_cost': 1,
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'To specify payment time allowed, please also tick '
            '&quot;advance payment required&quot;',
            str(form.errors['payment_time_allowed'])
        )

    def test_adv_payment_due_date_and_time_allowed_require_ticket_cost(self):

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_due_date': '30 Jun 2015',
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a ticket cost greater than £0: '
            'advance payment required, payment due date',
            str(form.errors['ticket_cost'])
        )

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'payment_time_allowed': 4,
                    'advance_payment_required': True,
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a ticket cost greater than £0: '
            'advance payment required, payment time allowed',
            str(form.errors['ticket_cost'])
        )

    def test_form_for_cancelled_events(self):
        ticketed_event = baker.make_recipe('booking.ticketed_event_max10')

        data = {
            'id': ticketed_event.id,
            'name': ticketed_event.name,
            'date': ticketed_event.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y %H:%M'),
            'contact_email': ticketed_event.contact_email,
            'contact_person': ticketed_event.contact_person,
            'location': ticketed_event.location,
            'ticket_cost': ticketed_event.ticket_cost,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }
        form = TicketedEventAdminForm(data=data, instance=ticketed_event)
        self.assertTrue(form.is_valid())
        # event is not cancelled, so cancelled checkbox is hidden
        cancelled_field = form.fields['cancelled']
        self.assertEqual(
            cancelled_field.widget.attrs,
            {'disabled': 'disabled', 'id': 'cancelled_id', 'class': 'hide'}
        )
        self.assertEquals(
            cancelled_field.help_text,
            'To cancel, use the Cancel button on the event list page'
        )

        ticketed_event.cancelled = True
        ticketed_event.save()
        data.update({'cancelled': True})
        form = TicketedEventAdminForm(data=data, instance=ticketed_event)
        cancelled_field = form.fields['cancelled']
        self.assertTrue(form.is_valid())
        self.assertEqual(
            cancelled_field.widget.attrs,
            {'class': 'form-control regular-checkbox', 'id': 'cancelled_id'}
        )
        self.assertEquals(
            cancelled_field.help_text,
            'Untick to reopen event; note that this does not change any other '
            'event attributes and does not reopen previously cancelled ticket '
            'bookings.'
        )

    def test_paypal_email_check_required_if_paypal_email_changed(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {'paypal_email': 'newpaypal@test.com'}),
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please reenter paypal email to confirm changes',
            str(form.errors['paypal_email_check'])
        )

    def test_paypal_email_and_check_must_match(self):
        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal1@test.com'
                },
            ),
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Email addresses do not match',
            str(form.errors['paypal_email_check'])
        )
        self.assertIn(
            'Email addresses do not match',
            str(form.errors['paypal_email'])
        )

        form = TicketedEventAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal@test.com'
                },
            ),
        )
        self.assertTrue(form.is_valid())


class TicketedEventFormsetTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')


    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.ticketed_event.id),
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_event_formset_valid(self):
        formset = TicketedEventFormSet(data=self.formset_data())
        self.assertTrue(formset.is_valid())

    def test_additional_form_data(self):
        formset = TicketedEventFormSet(
            data=self.formset_data(), queryset=TicketedEvent.objects.all()
        )
        form = formset.forms[0]
        self.assertEquals(form.payment_open_id, 'payment_open_0')
        self.assertEquals(
            form.advance_payment_required_id, 'advance_payment_required_0'
        )
        self.assertEquals(form.DELETE_id, 'DELETE_0')

    def test_can_only_delete_if_no_confirmed_ticket_purchases(self):

        tb = baker.make(
            TicketBooking, purchase_confirmed=False,
            ticketed_event=self.ticketed_event
        )
        formset = TicketedEventFormSet(
            data=self.formset_data(), queryset=TicketedEvent.objects.all()
        )
        form = formset.forms[0]

        with self.assertRaises(AttributeError):
            form.cannot_delete

        tb.purchase_confirmed = True
        tb.save()
        formset = TicketedEventFormSet(
            data=self.formset_data(), queryset=TicketedEvent.objects.all()
        )
        form = formset.forms[0]
        self.assertTrue(form.cannot_delete)

    def test_can_delete(self):
        ev_to_delete = baker.make_recipe('booking.ticketed_event_max10')
        extra_data = {
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 2,
            'form-1-DELETE': 'on',
            'form-1-id': ev_to_delete.id,
            }
        formset = TicketedEventFormSet(
            data=self.formset_data(extra_data),
            queryset=TicketedEvent.objects.all()
        )
        self.assertEqual(len(formset.deleted_forms), 1)
        deleted_form = formset.deleted_forms[0]
        self.assertEqual(deleted_form.cleaned_data['id'], ev_to_delete)


class TicketBookingInlineFormsetTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')
        self.ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )

    def formset_data(self, extra_data={}):
        data = {
            'ticket_bookings-TOTAL_FORMS': 1,
            'ticket_bookings-INITIAL_FORMS': 1,
            'ticket_bookings-0-id': self.ticket_booking.id,
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        formset = TicketBookingInlineFormSet(
            data=self.formset_data(),
            instance=self.ticketed_event
        )
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_additional_data_in_form(self):
        formset = TicketBookingInlineFormSet(
            data=self.formset_data(),
            instance=self.ticketed_event
        )
        form = formset.forms[0]
        self.assertFalse(form.paypal)
        self.assertEqual(form.cancel_id, 'cancel_0')
        self.assertEqual(form.reopen_id, 'reopen_0')
        self.assertEqual(form.paid_id, 'paid_0')
        self.assertEqual(
            form.send_confirmation_id, 'send_confirmation_0'
        )

    def test_paypal(self):
        ppt = baker.make(
            PaypalTicketBookingTransaction,
            ticket_booking=self.ticket_booking
        )
        # paypal transaction exists but no transaction id
        # (i.e. not paid yet by paypal)
        formset = TicketBookingInlineFormSet(
            data=self.formset_data(),
            instance=self.ticketed_event
        )
        form = formset.forms[0]
        self.assertFalse(form.paypal)

        ppt.transaction_id = 'testid'
        ppt.save()

        formset = TicketBookingInlineFormSet(
            data=self.formset_data(),
            instance=self.ticketed_event
        )
        form = formset.forms[0]
        self.assertTrue(form.paypal)


class PrintTicketsFormTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')

    def form_data(self, extra_data={}):
        data = {
            'ticketed_event': self.ticketed_event.id,
            'show_fields': ['show_booking_user', 'show_date_booked',
                'show_booking_reference'],
            'order_field': 'ticket_booking__user__first_name'
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        form = PrintTicketsForm(
            data=self.form_data(),
            ticketed_event_instance=self.ticketed_event
        )
        self.assertTrue(form.is_valid())

    def test_show_fields_includes_extra_ticket_info(self):
        self.ticketed_event.extra_ticket_info_label = "Test"
        self.ticketed_event.save()

        form = PrintTicketsForm(
            data=self.form_data(),
            ticketed_event_instance=self.ticketed_event
        )
        show_fields_widget = form.fields['show_fields'].widget
        self.assertEqual(
            show_fields_widget.choices,
            [
                ('show_booking_user', 'User who made the booking'),
                ('show_date_booked', 'Date booked'),
                ('show_booking_reference', 'Booking reference'),
                ('show_paid', 'Paid status'),
                ('show_extra_ticket_info', 'Test (extra requested ticket info)')
            ]
        )

        self.ticketed_event.extra_ticket_info1_label = "Test1"
        self.ticketed_event.save()

        form = PrintTicketsForm(
            data=self.form_data(),
            ticketed_event_instance=self.ticketed_event
        )
        show_fields_widget = form.fields['show_fields'].widget
        self.assertEqual(
            show_fields_widget.choices,
            [
                ('show_booking_user', 'User who made the booking'),
                ('show_date_booked', 'Date booked'),
                ('show_booking_reference', 'Booking reference'),
                ('show_paid', 'Paid status'),
                ('show_extra_ticket_info', 'Test (extra requested ticket info)'),
                ('show_extra_ticket_info1', 'Test1 (extra requested ticket info)')
            ]
        )

    def test_can_submit_form_with_extra_ticket_info_show_fields(self):
        self.ticketed_event.extra_ticket_info_label = "Test"
        self.ticketed_event.extra_ticket_info1_label = "Test1"
        self.ticketed_event.save()

        form = PrintTicketsForm(
            data=self.form_data({'show_fields': ['show_extra_ticket_info']}),
            ticketed_event_instance=self.ticketed_event
        )
        self.assertTrue(form.is_valid())

        form = PrintTicketsForm(
            data=self.form_data(
                {'show_fields': ['show_extra_ticket_info1']}),
            ticketed_event_instance=self.ticketed_event
        )
        self.assertTrue(form.is_valid())

    def test_can_submit_form_with_extra_ticket_info_order_field(self):
        self.ticketed_event.extra_ticket_info_label = "Test"
        self.ticketed_event.extra_ticket_info_label = "Test1"
        self.ticketed_event.save()

        form = PrintTicketsForm(
            data=self.form_data({'order_field': 'extra_ticket_info'}),
            ticketed_event_instance=self.ticketed_event
        )
        self.assertTrue(form.is_valid())

        form = PrintTicketsForm(
            data=self.form_data(
                {'order_field': 'extra_ticket_info1'}),
            ticketed_event_instance=self.ticketed_event
        )
        self.assertTrue(form.is_valid())
