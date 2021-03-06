import logging

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.urls import reverse

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, CreateView, DeleteView
from django.core.mail import send_mail
from django.template.loader import get_template
from django.utils import timezone
from braces.views import LoginRequiredMixin

from accounts.models import has_active_disclaimer, has_expired_disclaimer
from booking.models import Block
from booking.forms import BlockCreateForm
import booking.context_helpers as context_helpers
from booking.views.views_utils import (
    DisclaimerRequiredMixin, DataPolicyAgreementRequiredMixin
)

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class BlockCreateView(
    DisclaimerRequiredMixin, DataPolicyAgreementRequiredMixin,
    LoginRequiredMixin, CreateView
):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block added: {}'

    def dispatch(self, request, *args, **kwargs):
        # redirect if user already has active (paid or unpaid) blocks for all
        # blocktypes

        # remove cart items from session since we're getting a new block
        if self.request.session.get('cart_items'):
            del self.request.session['cart_items']

        if (
                self.request.user.is_authenticated and not
                context_helpers.get_blocktypes_available_to_book(self.request.user)
        ):
            return HttpResponseRedirect(reverse('booking:block_list'))

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
        return HttpResponseRedirect(reverse('booking:shopping_basket'))


class BlockListView(
    DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView
):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)
        context['disclaimer'] = has_active_disclaimer(self.request.user)
        context['expired_disclaimer'] = has_expired_disclaimer(
            self.request.user
        )
        types_available_to_book = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        if types_available_to_book:
            context['can_book_block'] = True

        blockformlist = []

        for block in context['blocks']:
            blockform = {
                'block': block,
                'block_cost': block.block_type.cost,
                'expired': block.expired or block.full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        return context

    def get_queryset(self):
        return Block.objects.filter(user=self.request.user).order_by('-start_date')


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
        delete_from_shopping_basket = request.GET.get('ref') == 'basket'

        ActivityLog.objects.create(
            log='User {} deleted unpaid and unused block {} ({})'.format(
                block_user, block_id, block_type
            )
        )

        super().delete(request, *args, **kwargs)

        if delete_from_shopping_basket:
            return HttpResponse('Block deleted')

        messages.success(self.request, 'Block has been deleted')

        next = request.POST.get('next', 'block_list')

        params = {}
        if request.POST.get('booking_code'):
            params['booking_code'] = request.POST['booking_code']
        if request.POST.get('block_code'):
            params['block_code'] = request.POST['block_code']

        url = self.get_success_url(next)
        if params:
            url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)

    def get_success_url(self, next='block_list'):
        return reverse('booking:{}'.format(next))


@login_required
def blocks_modal(request):
    # order by expiry date
    blocks = request.user.blocks.filter(expiry_date__gte=timezone.now()).order_by("expiry_date")
    # # already sorted by expiry date,
    active_blocks = [block for block in blocks if block.active_block()]

    unpaid_blocks = [
        block for block in request.user.blocks.filter(expiry_date__gte=timezone.now(), paid=False, paypal_pending=False)
        if not block.full
    ]
    types_available_to_book = context_helpers.get_blocktypes_available_to_book(request.user)
    context = {'active_blocks': active_blocks, 'unpaid_blocks': unpaid_blocks, 'can_book_block': types_available_to_book}
    return render(request, 'booking/includes/blocks_modal_content.html', context)
