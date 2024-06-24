# -*- coding: utf-8 -*-
import json

from decimal import Decimal
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Q, Sum
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template.response import TemplateResponse

from payments.forms import PayPalPaymentsShoppingBasketForm

from accounts.models import DataPrivacyPolicy, has_active_data_privacy_agreement

from booking.models import (
    Block, BlockType, BlockVoucher, Booking, EventVoucher, UsedBlockVoucher,
    UsedEventVoucher
)
from booking.forms import BookingVoucherForm, BlockVoucherForm
import booking.context_helpers as context_helpers
from booking.views.views_utils import _get_block_status, validate_block_voucher_code, validate_voucher_code

from payments.helpers import (
    create_booking_paypal_transaction, create_multiblock_paypal_transaction,
    create_multibooking_paypal_transaction
)


def get_unpaid_bookings_context(user):
    unpaid_bookings_all = user.bookings.filter(
        paid=False, status='OPEN', event__date__gte=timezone.now(), no_show=False, paypal_pending=False
    )

    if settings.PAYMENT_METHOD == "paypal":
        unpaid_bookings_all_open = unpaid_bookings_all.filter(event__payment_open=True)
        unpaid_bookings_payment_not_open = unpaid_bookings_all.filter(event__payment_open=False)
        unpaid_bookings = unpaid_bookings_all_open.filter(event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL)
        unpaid_bookings_non_default_paypal = unpaid_bookings_all_open.exclude(event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL)

        include_warning = bool([True for bk in unpaid_bookings_all_open if not bk.can_cancel])
        block_booking_available = bool(
            [True for booking in unpaid_bookings if booking.has_available_block]
        )
        unpaid_block_booking_available = bool(
            [True for booking in unpaid_bookings if booking.has_unpaid_block]
        )
        block_types_available = any(booking for booking in unpaid_bookings if any(BlockType.objects.filter(active=True, event_type=booking.event.event_type)))

        return {
            'unpaid_bookings': unpaid_bookings,
            'unpaid_booking_ids': list(unpaid_bookings.values_list('id', flat=True)),
            'unpaid_bookings_non_default_paypal': unpaid_bookings_non_default_paypal,
            'unpaid_bookings_payment_not_open': unpaid_bookings_payment_not_open,
            'include_warning': include_warning,
            'block_booking_available': block_booking_available,
            'block_types_available': block_types_available,
            'unpaid_block_booking_available': unpaid_block_booking_available
        }
    else:
        unpaid_bookings = unpaid_bookings_all.filter(event__payment_open=True)
        unpaid_bookings_payment_not_open = unpaid_bookings_all.filter(event__payment_open=False)

        include_warning = bool([True for bk in unpaid_bookings if not bk.can_cancel])
        block_booking_available = bool(
            [True for booking in unpaid_bookings if booking.has_available_block]
        )
        unpaid_block_booking_available = bool(
            [True for booking in unpaid_bookings if booking.has_unpaid_block]
        )
        block_types_available = any(booking for booking in unpaid_bookings if any(BlockType.objects.filter(active=True, event_type=booking.event.event_type)))

        return {
            'unpaid_bookings': unpaid_bookings,
            'unpaid_booking_ids': list(unpaid_bookings.values_list('id', flat=True)),
            'unpaid_bookings_payment_not_open': unpaid_bookings_payment_not_open,
            'include_warning': include_warning,
            'block_booking_available': block_booking_available,
            'block_types_available': block_types_available,
            'unpaid_block_booking_available': unpaid_block_booking_available
        }


def remove_voucher(items):
    for item in items:
        item.reset_voucher_code()


def add_booking_voucher_context(booking_code, user, context):
    unpaid_bookings = context['unpaid_bookings']
    
    context['booking_code'] = booking_code
    try:
        booking_voucher = EventVoucher.objects.get(code=booking_code)
    except EventVoucher.DoesNotExist:
        booking_voucher = None
        context['booking_voucher_error'] = 'Invalid code' if booking_code else 'No code provided'
        remove_voucher(unpaid_bookings)

    if booking_voucher:
        booking_voucher_error = validate_voucher_code(booking_voucher, user)
        context['booking_voucher_error'] = booking_voucher_error

        times_booking_voucher_used = UsedEventVoucher.objects.filter(
            voucher=booking_voucher, user=user
        ).count()
        context['times_booking_voucher_used'] = times_booking_voucher_used

        valid_booking_voucher = not bool(booking_voucher_error)
        context['valid_booking_voucher'] = valid_booking_voucher
        context['booking_voucher'] = booking_voucher

        if valid_booking_voucher:
            booking_voucher_dict = apply_voucher_to_unpaid_bookings(
                booking_voucher, unpaid_bookings, times_booking_voucher_used
            )
            context.update(**booking_voucher_dict)
        else:
            remove_voucher(unpaid_bookings)
    return context


def add_total_bookings_and_payment_context(request, context):
    unpaid_bookings = context['unpaid_bookings']

    if context.get('total_unpaid_booking_cost') is None:
        # no voucher, or invalid voucher
        total_agg = unpaid_bookings.aggregate(Sum('event__cost'))
        # pop item from the aggregate dict
        _, total_booking_cost = total_agg.popitem()
        context['total_unpaid_booking_cost'] = total_booking_cost

    if settings.PAYMENT_METHOD == "paypal":
        booking_code = context.get('booking_code')
        # Add extra context for paypal
        if unpaid_bookings:
            if context['total_unpaid_booking_cost'] > 0:
                # total_unpaid_block_cost can be 0 if 100% voucher(s) applied;
                # paypal button replaced with an update button in template
                item_ids_str = ','.join([str(item.id) for item in unpaid_bookings])
                custom = context_helpers.get_paypal_custom(
                    item_type='booking',
                    item_ids=item_ids_str,
                    voucher_code=booking_code if context.get('valid_booking_voucher') else '',
                    voucher_applied_to=context.get("voucher_applied_bookings", []),
                    user_email=request.user.email
                )
                if not context.get("unpaid_blocks"):
                    # If we only have bookings to be paid, we can add the cart items to the session for paypal checks
                    request.session["cart_items"] = custom

                if len(unpaid_bookings) == 1:
                    booking = unpaid_bookings[0]
                    invoice_id = create_booking_paypal_transaction(
                        request.user, booking
                    ).invoice_id

                    paypal_booking_form = PayPalPaymentsShoppingBasketForm(
                        initial=context_helpers.get_paypal_dict(
                            request,
                            context['total_unpaid_booking_cost'],
                            booking.event,
                            invoice_id,
                            custom,
                            paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
                        )
                    )
                else:
                    invoice_id = create_multibooking_paypal_transaction(
                        request.user, unpaid_bookings
                    )
                    paypal_booking_form = PayPalPaymentsShoppingBasketForm(
                        initial=context_helpers.get_paypal_cart_dict(
                            request,
                            'booking',
                            unpaid_bookings,
                            invoice_id,
                            custom,
                            voucher_applied_items=context.get('voucher_applied_bookings', []),
                            voucher=context.get('booking_voucher') if context.get('valid_booking_voucher') else None,
                            paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
                        )
                    )

                context["bookings_paypalform"] = paypal_booking_form
        
    return context


def get_unpaid_block_context(user, context=None):
    context = context or {}
    unpaid_block_and_costs = [
        (block, block.block_type.cost)
        for block in user.blocks.filter(paid=False, paypal_pending=False, expiry_date__gte=timezone.now()) if not block.full
    ]
    unpaid_blocks, unpaid_block_costs = list(zip(*unpaid_block_and_costs)) \
        if unpaid_block_and_costs else ([], [0])

    context.update({
        'unpaid_blocks': unpaid_blocks,
        'unpaid_block_ids': [block.id for block in unpaid_blocks],
        'unpaid_block_costs': unpaid_block_costs
    })
    return context


def add_block_voucher_context(block_code, user, context):
    unpaid_blocks = context['unpaid_blocks']
    context['block_code'] = block_code

    try:
        block_voucher = BlockVoucher.objects.get(code=block_code)
    except BlockVoucher.DoesNotExist:
        block_voucher = None
        context['block_voucher_error'] = 'Invalid code' if block_code else 'No code provided'
        remove_voucher(unpaid_blocks)

    if block_voucher:
        block_voucher_error = validate_block_voucher_code(block_voucher, user)
        context['block_voucher_error'] =  block_voucher_error

        times_block_voucher_used = UsedBlockVoucher.objects.filter(
            voucher=block_voucher, user=user
        ).count()
        context['times_block_voucher_used'] = times_block_voucher_used

        valid_block_voucher = not bool(block_voucher_error)
        context['valid_block_voucher'] = valid_block_voucher
        context['block_voucher'] = block_voucher

        if valid_block_voucher:
            block_voucher_dict = apply_voucher_to_unpaid_blocks(
                block_voucher, unpaid_blocks, times_block_voucher_used
            )
            context.update(**block_voucher_dict)
        else:
            remove_voucher(unpaid_blocks)
    return context


def add_total_blocks_and_payment_context(request, context):
    unpaid_block_costs = context.pop('unpaid_block_costs')
    if context.get('total_unpaid_block_cost') is None:
        # no voucher, or invalid voucher
        context['total_unpaid_block_cost'] = sum(unpaid_block_costs)
    if settings.PAYMENT_METHOD == "paypal":
        # extra context needed for paypam
        block_code = context.get('block_code')
        unpaid_blocks = context['unpaid_blocks']
        if unpaid_blocks:
            if context['total_unpaid_block_cost'] > 0:
                # total_unpaid_block_cost can be 0 if 100% voucher(s) applied;
                # paypal button replaced with an update button in template
                item_ids_str = ','.join([str(item.id) for item in unpaid_blocks])
                custom = context_helpers.get_paypal_custom(
                    item_type='block',
                    item_ids=item_ids_str,
                    voucher_code=block_code
                    if context.get('valid_block_voucher') else '',
                    voucher_applied_to=context.get("voucher_applied_blocks", []),
                    user_email=request.user.email
                )
                invoice_id = create_multiblock_paypal_transaction(
                        request.user, unpaid_blocks
                    )
                paypal_block_form = PayPalPaymentsShoppingBasketForm(
                    initial=context_helpers.get_paypal_cart_dict(
                        request,
                        'block',
                        unpaid_blocks,
                        invoice_id,
                        custom,
                        voucher_applied_items=context.get('voucher_applied_blocks', []),
                        voucher=context.get('block_voucher') if context.get('valid_block_voucher') else None,
                        paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
                    )
                )
                context["blocks_paypalform"] = paypal_block_form

                if not context.get("unpaid_bookings"):
                    # If we only have blocks to be paid, we can add the cart items to the session for paypal checks
                    request.session["cart_items"] = custom  
    return context


@login_required
def shopping_basket(request):
    if DataPrivacyPolicy.current_version() > 0 and request.user.is_authenticated \
            and not has_active_data_privacy_agreement(request.user):
        return HttpResponseRedirect(
            reverse('profile:data_privacy_review') + '?next=' + request.path
        )
    

    if settings.PAYMENT_METHOD == "paypal":
        template_name = 'booking/shopping_basket.html'
        # Make sure the cart items is up to date; it'll be repopulated if necessary
        if "cart_items" in request.session:
            del request.session["cart_items"]
    else:
        assert settings.PAYMENT_METHOD == "stripe"
        template_name = 'booking/shopping_basket_stripe.html'

    # unpaid status for both bookings and blocks
    context = get_unpaid_bookings_context(request.user)
    context = get_unpaid_block_context(request.user, context)

     # bookings
    booking_code = request.GET.get('booking_code')
    if "remove_booking_voucher" in request.GET:
        remove_voucher(context["unpaid_bookings"])
    elif booking_code:
        booking_code = booking_code.strip()
        context = add_booking_voucher_context(
            booking_code, 
            request.user, 
            context, 
        )
    if context["unpaid_bookings"]:
        context['booking_voucher_form'] = BookingVoucherForm(
            initial={'booking_code': booking_code}
        )
        context = add_total_bookings_and_payment_context(request, context)
    
    # blocks
    block_code = request.GET.get('block_code', None)
    if "remove_block_voucher"in request.GET:
        remove_voucher(context["unpaid_blocks"])
    elif block_code:
        block_code = block_code.strip()
        context = add_block_voucher_context(
            block_code, 
            request.user, 
            context,
        )
    if context["unpaid_blocks"]:
        context['block_voucher_form'] = BlockVoucherForm(
            initial={'block_code': block_code}
        )
        context = add_total_blocks_and_payment_context(request, context)
    
    return TemplateResponse(
        request,
        template_name,
        context
    )


def apply_voucher_to_unpaid_bookings(voucher, bookings, times_used):
    check_max_per_user = False
    check_max_total = False
    max_per_user_exceeded = False
    max_total_exceeded = False

    total_booking_cost = 0
    voucher_applied_bookings = []
    invalid_event_types = []

    if voucher.max_per_user:
        check_max_per_user = True
        uses_per_user_left = voucher.max_per_user - times_used

    if voucher.max_vouchers:
        check_max_total = True
        max_voucher_uses_left = (
            voucher.max_vouchers -
            UsedEventVoucher.objects.filter(voucher=voucher).count()
        )

    for booking in bookings:
        can_use = voucher.check_event_type(booking.event.event_type)
        if check_max_per_user and uses_per_user_left <= 0:
            can_use = False
            max_per_user_exceeded = True
        if check_max_total and max_voucher_uses_left <= 0:
            can_use = False
            max_total_exceeded = True

        if can_use:
            booking.voucher_code = voucher.code
            booking.save()
            
            voucher_applied_bookings.append(booking.id)
            if check_max_per_user:
                uses_per_user_left -= 1
            if check_max_total:
                max_voucher_uses_left -= 1
        else:
            # voucher can't be used; make sure it's unset on the booking
            booking.reset_voucher_code()
            # if we can't use the voucher but max_total and
            # max_per_user are not exceeded, it must be an invalid
            # event type
            if not (max_total_exceeded or max_per_user_exceeded):
                invalid_event_types.append(
                    booking.event.event_type.subtype
                )
        
        # add the cost to the total; 
        # cost_with_voucher returns the event cost if there's no voucher applied
        total_booking_cost += booking.cost_with_voucher

    voucher_msg = []
    if invalid_event_types:
        voucher_msg.append(
            'Voucher cannot be used for some bookings '
            '({})'.format(', '.join(set(invalid_event_types)))
        )

    # only return one of these messages; the most relevant to the user is max_per_user
    # if voucher is invalid for that reason
    if max_per_user_exceeded:
        voucher_msg.append(
            'Voucher not applied to some bookings; you can '
            'only use this voucher a total of {} times.'.format(
                voucher.max_per_user
            )
        )
    elif max_total_exceeded:
        voucher_msg.append(
            'Voucher not applied to some bookings; voucher '
            'has limited number of total uses.'
        )

    return {
        'voucher_applied_bookings': voucher_applied_bookings,
        'total_unpaid_booking_cost': total_booking_cost,
        'booking_voucher_msg': voucher_msg
    }


def apply_voucher_to_unpaid_blocks(voucher, blocks, times_used):
    check_max_per_user = False
    check_max_total = False
    max_per_user_exceeded = False
    max_total_exceeded = False

    total_block_cost = 0
    voucher_applied_blocks = []
    invalid_block_types = []

    if voucher.max_per_user:
        check_max_per_user = True
        uses_per_user_left = voucher.max_per_user - times_used

    if voucher.max_vouchers:
        check_max_total = True
        max_voucher_uses_left = (
            voucher.max_vouchers -
            UsedBlockVoucher.objects.filter(voucher=voucher).count()
        )
    for block in blocks:
        can_use = voucher.check_block_type(block.block_type)
        if check_max_per_user and uses_per_user_left <= 0:
            can_use = False
            max_per_user_exceeded = True
        if check_max_total and max_voucher_uses_left <= 0:
            can_use = False
            max_total_exceeded = True

        if can_use:
            block.voucher_code = voucher.code
            block.save()
            voucher_applied_blocks.append(block.id)
            if check_max_per_user:
                uses_per_user_left -= 1
            if check_max_total:
                max_voucher_uses_left -= 1
        else:
            # voucher can't be used; make sure it's unset on the block
            block.reset_voucher_code()

            # if we can't use the voucher but max_total and
            # max_per_user are not exceeded, it must be an invalid
            # event type
            if not (max_total_exceeded or max_per_user_exceeded):
                invalid_block_types.append(str(block.block_type))

        # add the cost to the total; 
        # cost_with_voucher returns the event cost if there's no voucher applied
        total_block_cost += block.cost_with_voucher

    voucher_msg = []
    if invalid_block_types:
        voucher_msg.append(
            'Voucher cannot be used for some block types '
            '({})'.format(', '.join(set(invalid_block_types)))
        )
    # only return one of these messages; the most relevant to the user is max_per_user
    # if voucher is invalid for that reason
    if max_per_user_exceeded:
        voucher_msg.append(
            'Voucher not applied to some blocks; you can '
            'only use this voucher a total of {} times.'.format(
                voucher.max_per_user
            )
        )
    elif max_total_exceeded:
        voucher_msg.append(
            'Voucher not applied to some blocks; voucher '
            'has limited number of total uses.'
        )

    return {
        'voucher_applied_blocks': voucher_applied_blocks,
        'total_unpaid_block_cost': total_block_cost,
        'block_voucher_msg': voucher_msg
    }


@login_required
def update_block_bookings(request):
    unpaid_bookings = Booking.objects.filter(
        user=request.user, event__payment_open=True, paid=False, status='OPEN',
        event__date__gte=timezone.now(),
        no_show=False, paypal_pending=False
    )

    block_booked = []
    for booking in unpaid_bookings:
        active_block = booking.get_next_active_block()
        if active_block:
            booking.block = active_block
            booking.paid = True
            booking.payment_confirmed = True

            # check for existence of free child block on pre-saved booking
            has_free_block_pre_save = False
            if booking.block and booking.block.children.exists():
                has_free_block_pre_save = True

            booking.save()
            block_booked.append(booking)
            _get_block_status(booking, request)

            if not booking.block.active_block():
                if booking.block.children.exists() \
                        and not has_free_block_pre_save:
                    messages.info(
                        request,
                        mark_safe(
                            'You have just used the last space in your block and '
                            'have qualified for a extra free class'
                        )
                    )
                elif not booking.has_available_block:
                    messages.info(
                        request,
                        mark_safe(
                            'You have just used the last space in your block. '
                           '<a href="/blocks/new">Buy a new one</a>.'
                        )
                    )

    if block_booked:
        messages.info(request, "Blocks used for {} bookings".format(len(block_booked)))

        # send email to user
        host = 'http://{}'.format(request.META.get('HTTP_HOST'))
        ctx = {
            'host': host,
            'bookings': block_booked,
        }
        send_mail(
            '{} Blocks used for {} bookings'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, len(block_booked)
            ),
            get_template('booking/email/multi_block_booking_updated.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            html_message=get_template(
                'booking/email/multi_block_booking_updated.html'
            ).render(ctx),
            fail_silently=True
        )

    else:
        messages.info(
            request,
            mark_safe('No blocks available to use for these bookings. Go to '
            '<a href="/blocks/new"> to buy a block.')
        )

    url = reverse('booking:shopping_basket')
    params = {}
    if 'booking_code' in request.POST:
        params['booking_code'] = request.POST['booking_code']
    if 'block_code' in request.POST:
        params['block_code'] = request.POST['block_code']

    if params:
        url += '?{}'.format(urlencode(params))
    return HttpResponseRedirect(url)


@login_required
def submit_zero_booking_payment(request):
    # 100% gift voucher used for booking(s); this doesn't go through paypal, we
    # just mark as paid here and create a UsedEventVoucher
    unpaid_booking_ids = json.loads(request.POST.get('unpaid_booking_ids'))
    booking_code = request.POST['booking_code']
    voucher = get_object_or_404(EventVoucher, code=booking_code)

    unpaid_bookings = Booking.objects.filter(id__in=unpaid_booking_ids)
    for booking in unpaid_bookings:
        booking.paid = True
        booking.payment_confirmed = True
        booking.save()
        UsedEventVoucher.objects.create(
            voucher=voucher, user=booking.user, booking_id=booking.id
        )

    # Return to shopping basket if there are unpaid blocks (including with a
    # total of 0, as that still needs to be processed, else return to bookings pag
    total_unpaid_block_cost = request.POST.get('total_unpaid_block_cost')
    if total_unpaid_block_cost:
        url = reverse('booking:shopping_basket')
        # don't include the used booking gift voucher code in return params
        params = {}
        if 'block_code' in request.POST:
            params['block_code'] = request.POST['block_code']

        if params:
            url += '?{}'.format(urlencode(params))
    else:
        url = reverse('booking:bookings')
    return HttpResponseRedirect(url)


@login_required
def submit_zero_block_payment(request):
    # 100% gift voucher used for block(s); this doesn't go through paypal, we
    # just mark as paid here and create a UsedBlockVoucher
    unpaid_block_ids = json.loads(request.POST.get('unpaid_block_ids'))
    block_code = request.POST['block_code']
    voucher = get_object_or_404(BlockVoucher, code=block_code)

    unpaid_blocks = Block.objects.filter(id__in=unpaid_block_ids)
    for block in unpaid_blocks:
        block.paid = True
        block.save()
        UsedBlockVoucher.objects.create(
            voucher=voucher, user=block.user, block_id=block.id
        )

    # Return to shopping basket if there are unpaid bookings, else return to blocks page
    total_unpaid_booking_cost = request.POST.get('total_unpaid_booking_cost')
    if total_unpaid_booking_cost:
        url = reverse('booking:shopping_basket')
        # don't include the used block gift voucher code in return params
        params = {}
        if 'booking_code' in request.POST:
            params['booking_code'] = request.POST['booking_code']

        if params:
            url += '?{}'.format(urlencode(params))
    else:
        url = reverse('booking:block_list')
    return HttpResponseRedirect(url)


def shopping_basket_bookings_total_context(request):
    # context requires total_unpaid_booking_cost and paypal booking form
    booking_code = request.GET.get('code', '').strip()
    context = get_unpaid_bookings_context(request.user)
    context.update(get_unpaid_block_context(request.user))
    if booking_code:
        context = add_booking_voucher_context(booking_code, request.user, context)
    context = add_total_bookings_and_payment_context(request, context)
    if not context.get("unpaid_bookings"):
        # If we've removed all unpaid bookings, also update the blocks context, to update the session cart items with
        # any unpaid bookings
        context = add_total_blocks_and_payment_context(request, context)
    return context


def shopping_basket_blocks_total_context(request):
    block_code = request.GET.get('code', '').strip()
    context = get_unpaid_block_context(request.user)
    context.update(get_unpaid_bookings_context(request.user))
    if block_code:
        context = add_block_voucher_context(block_code, request.user, context)
    context = add_total_blocks_and_payment_context(request, context)
    if not context.get("unpaid_blocks"):
        # If we've removed all unpaid blocks, also update the bookings context, to update the session cart items with
        # any unpaid blocks
        context = add_total_bookings_and_payment_context(request, context)
    return context
