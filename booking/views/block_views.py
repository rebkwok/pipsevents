import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, CreateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from braces.views import LoginRequiredMixin

from payments.forms import PayPalPaymentsListForm
from booking.models import Booking, Block
from booking.forms import BlockCreateForm
import booking.context_helpers as context_helpers
from booking.views.views_utils import DisclaimerRequiredMixin
from payments.helpers import create_block_paypal_transaction

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class BlockCreateView(DisclaimerRequiredMixin, LoginRequiredMixin, CreateView):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block booking created: {}'

    def dispatch(self, request, *args, **kwargs):
        # redirect if user already has active (paid or unpaid) blocks for all
        # blocktypes
        if self.request.session.get('no_available_block'):
            # if clicked Back after buying block
            del self.request.session['no_available_block']
            return HttpResponseRedirect(reverse('booking:block_list'))
        if not context_helpers.get_blocktypes_available_to_book(
                self.request.user):
            return HttpResponseRedirect(reverse('booking:has_active_block'))
        return super(BlockCreateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockCreateView, self).get_context_data(**kwargs)
        context['form'].fields['block_type'].queryset = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        context['block_types'] = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        return context

    def form_valid(self, form):
        block_type = form.cleaned_data['block_type']
        types_available = context_helpers.get_blocktypes_available_to_book(
            self.request.user)

        if block_type not in types_available:
            return HttpResponseRedirect(reverse('booking:has_active_block'))

        block = form.save(commit=False)
        block.user = self.request.user
        block.save()

        if not context_helpers.get_blocktypes_available_to_book(
            self.request.user
        ):
            self.request.session['no_available_block'] = True

        ActivityLog.objects.create(
            log='Block {} created; Block type: {}; user: {}'.format(
                block.id, block.block_type, block.user.username
            )
        )

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        ctx = {
                          'host': host,
                          'user': block.user,
                          'block_type': block.block_type,
                          'start_date': block.start_date,
                          'expiry_date': block.expiry_date,
                      }
        send_mail('{} Block created'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            get_template('booking/email/block_booked.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [block.user.email],
            html_message=get_template(
                'booking/email/block_booked.html').render(ctx),
            fail_silently=False)

        messages.success(
            self.request, self.success_message.format(block.block_type)
            )
        return HttpResponseRedirect(block.get_absolute_url())


class BlockListView(LoginRequiredMixin, ListView):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)

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

        types_available_to_book = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        if types_available_to_book:
            context['can_book_block'] = True

        blockformlist = []
        for block in self.object_list:
            expired = block.expiry_date < timezone.now()

            if not block.paid and not expired:
                invoice_id = create_block_paypal_transaction(
                    self.request.user, block).invoice_id
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                paypal_form = PayPalPaymentsListForm(
                    initial=context_helpers.get_paypal_dict(
                        host,
                        block.block_type.cost,
                        block.block_type,
                        invoice_id,
                        '{} {}'.format('block', block.id),
                        paypal_email=block.block_type.paypal_email
                    )
                )
            else:
                paypal_form = None

            full = Booking.objects.filter(
                block__id=block.id).count() >= block.block_type.size
            blockform = {
                'block': block,
                'paypalform': paypal_form,
                'expired': expired or full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')


class BlockDeleteView(LoginRequiredMixin, DisclaimerRequiredMixin, DeleteView):

    model = Block
    template_name = 'booking/delete_block.html'

    def dispatch(self, request, *args, **kwargs):
        # redirect if block is paid or has bookings
        self.block = get_object_or_404(Block, id=self.kwargs['pk'])
        if self.block.paid or self.block.bookings.exists():
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(BlockDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockDeleteView, self).get_context_data(**kwargs)
        context['block_to_delete'] = self.block
        return context

    def delete(self, request, *args, **kwargs):
        block_id = self.block.id
        block_user = self.block.user.username
        block_type = self.block.block_type

        ActivityLog.objects.create(
            log='User {} deleted unpaid and unused block {} ({})'.format(
                block_user, block_id, block_type
            )
        )
        messages.success(self.request, 'Block has been deleted')

        response = super(BlockDeleteView, self).delete(request, *args, **kwargs)
        # remove session flag if necessary
        if request.session.get('no_available_block') and \
                context_helpers.get_blocktypes_available_to_book(
            request.user
        ):
            del request.session['no_available_block']
        return response

    def get_success_url(self):
        return reverse('booking:block_list')
