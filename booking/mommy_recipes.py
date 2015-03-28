from datetime import timedelta, datetime
from django.contrib.auth.models import User

from django.utils import timezone

from model_mommy.recipe import Recipe, foreign_key, seq

from allauth.socialaccount.models import SocialApp
from booking.models import Event, Block, Booking, BlockType
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

future_EV = Recipe(Event,
                      date=future,
                      type='EV')

future_WS = Recipe(Event,
                   date=future,
                   type='WS')

future_PC = Recipe(Event,
                   date=future,
                   type='PC',
                   )

future_CL = Recipe(Event,
                   date=future,
                   type='CL',
                   )

# past event
past_event = Recipe(Event,
                    date=past,
                    type='WS',
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10)
                    )

blocktype5 = Recipe(BlockType, size=5, duration=2)
blocktype10 = Recipe(BlockType, size=10, duration=4)

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

mon_session = Recipe(Session, day=Session.MON)