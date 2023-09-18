from datetime import timedelta, datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.models import User

from django.utils import timezone

from model_bakery.recipe import Recipe, foreign_key, seq

from allauth.socialaccount.models import SocialApp

from accounts.models import DisclaimerContent, OnlineDisclaimer
from booking.models import Event, EventType, Block, Booking, \
    BlockType, WaitingListUser, TicketBooking, TicketedEvent, \
    EventVoucher, BlockVoucher
from timetable.models import Session

now = timezone.now()
past = now - timedelta(30)
future = now + timedelta(30)

user = Recipe(User,
              username=seq("test_user"),
              password="password",
              email=seq("test_user@test.com"),
              )

# events; use defaults apart from dates
# override when using recipes, eg. baker.make_recipe('future_event', cost=10)

event_type_PC = Recipe(EventType, event_type="CL", subtype=seq("Pole level class"))
event_type_PP = Recipe(EventType, event_type="CL", subtype=seq("Pole practice"))
event_type_WS = Recipe(EventType, event_type="EV", subtype=seq("Workshop"))
event_type_OE = Recipe(EventType, event_type="EV", subtype=seq("Other event"))
event_type_OC = Recipe(EventType, event_type="CL", subtype=seq("Other class"))
event_type_RH = Recipe(EventType, event_type="RH", subtype=seq("Room hire"))
event_type_OT = Recipe(EventType, event_type="OT", subtype=seq("Online tutorial"))

future_EV = Recipe(Event,
                      date=future,
                      event_type=foreign_key(event_type_OE),
                      paypal_email=settings.DEFAULT_PAYPAL_EMAIL)

future_WS = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_WS),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)

future_PC = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_PC),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)
future_PP = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_PP),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)
future_CL = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_OC),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)
future_RH = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_RH),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)
future_OT = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_OT),
                   paypal_email=settings.DEFAULT_PAYPAL_EMAIL)

# past event
past_event = Recipe(Event,
                    date=past,
                    event_type=foreign_key(event_type_WS),
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10),
                    paypal_email=settings.DEFAULT_PAYPAL_EMAIL
                    )

# past_class
past_class = Recipe(Event,
                    date=past,
                    event_type=foreign_key(event_type_PC),
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10),
                    paypal_email=settings.DEFAULT_PAYPAL_EMAIL
                    )

blocktype = Recipe(BlockType, active=True, duration=4)

blocktype5 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                    size=5, duration=2, active=True)
blocktype10 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                     size=10, duration=4, active=True)
blocktypePP10 = Recipe(BlockType, event_type=foreign_key(event_type_PP),
                     size=10, duration=4, active=True)
blocktype_other = Recipe(
    BlockType, event_type=foreign_key(event_type_OC), active=True, duration=4,
)

free_blocktype = Recipe(
    BlockType, event_type=foreign_key(event_type_PC), size=1, duration=1,
    identifier='free class', cost=0
)

block = Recipe(Block, block_type=foreign_key(blocktype))

block_5 = Recipe(Block,
                 user=foreign_key(user),
                 block_type=foreign_key(blocktype5),
                 start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc))

block_10 = Recipe(Block,
                  user=foreign_key(user),
                  block_type=foreign_key(blocktype10),
                  start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc))

booking = Recipe(
    Booking, user__email=seq("test_user@test.com"), 
    event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)
booking_with_user = Recipe(
    Booking, user=foreign_key(user),
    event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)

past_booking = Recipe(
    Booking,
    event=foreign_key(past_event),
    user=foreign_key(user),
    event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)

fb_app = Recipe(SocialApp,
                provider='facebook')

mon_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.MON,
    payment_time_allowed=None, paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)
tue_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.TUE,
    payment_time_allowed=None, paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)
wed_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.WED,
    payment_time_allowed=None, paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)

waiting_list_user = Recipe(WaitingListUser, user=foreign_key(user))

ticketed_event_max10 = Recipe(
    TicketedEvent, max_tickets=10, ticket_cost=10, date=future,
    paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)
ticketed_event_past_max10 = Recipe(
    TicketedEvent, max_tickets=10, ticket_cost=10, date=past,
    paypal_email=settings.DEFAULT_PAYPAL_EMAIL
)
ticket_booking = Recipe(TicketBooking, user=foreign_key(user))

online_disclaimer = Recipe(
    OnlineDisclaimer, dob=now - timedelta(20*365),
    medical_treatment_permission=True, terms_accepted=True,
    age_over_18_confirmed=True,
    version=DisclaimerContent.current_version()
)

event_gift_voucher = Recipe(
    EventVoucher, code="abc1234", activated=False, discount=100, max_per_user=1, max_vouchers=1,
    is_gift_voucher=True
)
block_gift_voucher = Recipe(
    BlockVoucher, 
    code="def1234", activated=False, discount=100, max_per_user=1, max_vouchers=1,
    is_gift_voucher=True
)
