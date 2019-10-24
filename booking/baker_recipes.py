from datetime import timedelta, datetime
from django.contrib.auth.models import User

from django.utils import timezone

from model_bakery.recipe import Recipe, foreign_key, seq

from allauth.socialaccount.models import SocialApp

from accounts.models import OnlineDisclaimer
from booking.models import Event, EventType, Block, Booking, \
    BlockType, WaitingListUser, Ticket, TicketBooking, TicketedEvent
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

future_EV = Recipe(Event,
                      date=future,
                      event_type=foreign_key(event_type_OE))

future_WS = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_WS))

future_PC = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_PC))
future_PP = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_PP))
future_CL = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_OC))
future_RH = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_RH))

# past event
past_event = Recipe(Event,
                    date=past,
                    event_type=foreign_key(event_type_WS),
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10)
                    )

# past_class
past_class = Recipe(Event,
                    date=past,
                    event_type=foreign_key(event_type_PC),
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10)
                    )

blocktype = Recipe(BlockType, active=True)

blocktype5 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                    size=5, duration=2, active=True)
blocktype10 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                     size=10, duration=4, active=True)
blocktypePP10 = Recipe(BlockType, event_type=foreign_key(event_type_PP),
                     size=10, duration=4, active=True)
blocktype_other = Recipe(
    BlockType, event_type=foreign_key(event_type_OC), active=True
)

free_blocktype = Recipe(
    BlockType, event_type=foreign_key(event_type_PC), size=1, duration=1,
    identifier='free class', cost=0
)

block = Recipe(Block)

block_5 = Recipe(Block,
                 user=foreign_key(user),
                 block_type=foreign_key(blocktype5),
                 start_date=datetime(2015, 1, 1, tzinfo=timezone.utc))

block_10 = Recipe(Block,
                  user=foreign_key(user),
                  block_type=foreign_key(blocktype10),
                  start_date=datetime(2015, 1, 1, tzinfo=timezone.utc))

booking = Recipe(Booking, user__email=seq("test_user@test.com"))
booking_with_user = Recipe(Booking, user=foreign_key(user))

past_booking = Recipe(Booking,
                      event=foreign_key(past_event),
                      user=foreign_key(user)
                      )

fb_app = Recipe(SocialApp,
                provider='facebook')

mon_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.MON,
    payment_time_allowed=None
)
tue_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.TUE,
    payment_time_allowed=None
)
wed_session = Recipe(
    Session, event_type=foreign_key(event_type_PC), day=Session.WED,
    payment_time_allowed=None
)

waiting_list_user = Recipe(WaitingListUser, user=foreign_key(user))

ticketed_event_max10 = Recipe(
    TicketedEvent, max_tickets=10, ticket_cost=10, date=future
)
ticketed_event_past_max10 = Recipe(TicketedEvent, max_tickets=10,
                                   ticket_cost=10, date=past)
ticket_booking = Recipe(TicketBooking, user=foreign_key(user))

online_disclaimer = Recipe(
    OnlineDisclaimer, dob=now - timedelta(20*365),
    medical_treatment_permission=True, terms_accepted=True,
    age_over_18_confirmed=True
)