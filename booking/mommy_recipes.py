from datetime import timedelta, datetime
from django.contrib.auth.models import User

from django.utils import timezone

from model_mommy.recipe import Recipe, foreign_key, seq

from allauth.socialaccount.models import SocialApp
from booking.models import Event, EventType, Block, Booking, \
    BlockType, WaitingListUser
from timetable.models import Session

now = timezone.now()
past = now - timedelta(30)
future = now + timedelta(30)

user = Recipe(User,
              username=seq("test_user"),
              password="password",
              email="test_user@test.com",
              )

# events; use defaults apart from dates
# override when using recipes, eg. mommy.make_recipe('future_event', cost=10)

event_type_PC = Recipe(EventType, event_type="CL", subtype=seq("Pole level class"))
event_type_WS = Recipe(EventType, event_type="EV", subtype=seq("Workshop"))
event_type_OE = Recipe(EventType, event_type="EV", subtype=seq("Other event"))
event_type_OC = Recipe(EventType, event_type="CL", subtype=seq("Other class"))

future_EV = Recipe(Event,
                      date=future,
                      event_type=foreign_key(event_type_OE))

future_WS = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_WS))

future_PC = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_PC))

future_CL = Recipe(Event,
                   date=future,
                   event_type=foreign_key(event_type_OC))

# past event
past_event = Recipe(Event,
                    date=past,
                    event_type=foreign_key(event_type_WS),
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10)
                    )

blocktype = Recipe(BlockType)

blocktype5 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                    size=5, duration=2)
blocktype10 = Recipe(BlockType, event_type=foreign_key(event_type_PC),
                     size=10, duration=4)
blocktype_other = Recipe(BlockType, event_type=foreign_key(event_type_OC))

block = Recipe(Block)

block_5 = Recipe(Block,
                 user=foreign_key(user),
                 block_type=foreign_key(blocktype5),
                 start_date=datetime(2015, 1, 1, tzinfo=timezone.utc))

block_10 = Recipe(Block,
                  user=foreign_key(user),
                  block_type=foreign_key(blocktype10),
                  start_date=datetime(2015, 1, 1, tzinfo=timezone.utc))

booking = Recipe(Booking)

past_booking = Recipe(Booking,
                      event=foreign_key(past_event)
                      )

fb_app = Recipe(SocialApp,
                provider='facebook')

mon_session = Recipe(Session, event_type=foreign_key(event_type_PC), day=Session.MON)
tue_session = Recipe(Session, event_type=foreign_key(event_type_PC), day=Session.TUE)
wed_session = Recipe(Session, event_type=foreign_key(event_type_PC), day=Session.WED)

waiting_list_user = Recipe(WaitingListUser)
