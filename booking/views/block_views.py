import logging

from decimal import Decimal

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
from django.template.response import TemplateResponse
from braces.views import LoginRequiredMixin

from accounts.utils import has_active_disclaimer, has_expired_disclaimer
from payments.forms import PayPalPaymentsListForm
from booking.models import Booking, Block, BlockVoucher, UsedBlockVoucher
from booking.forms import BlockCreateForm, VoucherForm
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
            log='Block {} created; Block type: {}; by user: {}'.format(
                block.id, block.block_type, self.request.user.username
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

    def validate_voucher_code(self, voucher, user):
        if voucher.has_expired:
            return 'Voucher code has expired'
        elif voucher.max_vouchers and \
            UsedBlockVoucher.objects.filter(voucher=voucher).count() >= \
                voucher.max_vouchers:
            return 'Voucher has limited number of uses and has now expired'
        elif not voucher.has_started:
            return 'Voucher code is not valid until {}'.format(
                voucher.start_date.strftime("%d %b %y")
            )
        elif voucher.max_per_user and UsedBlockVoucher.objects.filter(
                voucher=voucher, user=user
        ).count() >= voucher.max_per_user:
            return 'Voucher code has already been used the maximum number ' \
                   'of times ({})'.format(
                    voucher.max_per_user
                    )
        else:
            user_unpaid_blocks = [
                block for block in Block.objects.filter(user=user, paid=False)
                if not block.expired
            ]
            for block in user_unpaid_blocks:
                if voucher.check_block_type(block.block_type):
                    return None
            return 'Code is not valid for any of your currently unpaid ' \
                   'blocks'

    def post(self, request):
        if "apply_voucher" in request.POST:
            voucher_error = None
            code = request.POST['code'].strip()
            try:
                voucher = BlockVoucher.objects.get(code=code)
            except BlockVoucher.DoesNotExist:
                voucher = None
                voucher_error = 'Invalid code' if code else 'No code provided'

            if voucher:
                voucher_error = self.validate_voucher_code(
                    voucher, self.request.user
                )

            context = {'blocks': self.get_queryset()}
            extra_context = self.get_extra_context(
                voucher=voucher, voucher_error=voucher_error, code=code,
            )
            context.update(**extra_context)
            return TemplateResponse(self.request, self.template_name, context)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)
        extra_context = self.get_extra_context()
        context.update(**extra_context)
        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')

    def get_extra_context(self, **kwargs):
        context = {}
        context['disclaimer'] = has_active_disclaimer(self.request.user)
        context['expired_disclaimer'] = has_expired_disclaimer(
            self.request.user
        )

        types_available_to_book = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        if types_available_to_book:
            context['can_book_block'] = True

        voucher = kwargs.get('voucher', None)
        voucher_error = kwargs.get('voucher_error', None)
        code = kwargs.get('code', None)
        context['voucher_form'] = VoucherForm(initial={'code': code})
        if voucher:
            context['voucher'] = voucher
        if voucher_error:
            context['voucher_error'] = voucher_error
        valid_voucher = False
        if voucher:
            valid_voucher = not bool(voucher_error)
            context['valid_voucher'] = valid_voucher

        blockformlist = []
        for block in self.get_queryset():
            expired = block.expiry_date < timezone.now()
            paypal_cost = None
            voucher_applied = False

            if not block.paid and not expired:
                context['has_unpaid_block'] = True
                paypal_cost = block.block_type.cost
                if valid_voucher and voucher.check_block_type(block.block_type):
                    paypal_cost = Decimal(
                        float(paypal_cost) * ((100 - voucher.discount) / 100)
                    ).quantize(Decimal('.05'))
                    voucher_applied = True

                invoice_id = create_block_paypal_transaction(
                    self.request.user, block).invoice_id
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                paypal_form = PayPalPaymentsListForm(
                    initial=context_helpers.get_paypal_dict(
                        host,
                        paypal_cost,
                        block.block_type,
                        invoice_id,
                        '{} {}{}'.format(
                            'block', block.id, ' {}'.format(code)
                            if valid_voucher else ''
                        ),
                        paypal_email=block.block_type.paypal_email
                    )
                )
            else:
                paypal_form = None
            full = Booking.objects.filter(
                block__id=block.id).count() >= block.block_type.size
            blockform = {
                'block': block,
                'voucher_applied': voucher_applied,
                'block_cost': paypal_cost,
                'paypalform': paypal_form,
                'expired': expired or full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        return context


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
