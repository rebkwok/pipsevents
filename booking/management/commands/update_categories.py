from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Event, FilterCategory
from timetable.models import Session


class Command(BaseCommand):

   def handle(self, *args, **options):
        events = Event.objects.filter(event_type__event_type="CL", date__gte=timezone.now())
        ttsessions = Session.objects.all()
        l1, _ = FilterCategory.objects.get_or_create(category="Level 1")
        l2, _ = FilterCategory.objects.get_or_create(category="Level 2")
        l3, _ = FilterCategory.objects.get_or_create(category="Level 3")
        l4, _ = FilterCategory.objects.get_or_create(category="Level 4")
        l5, _ = FilterCategory.objects.get_or_create(category="Level 5")
        l6, _ = FilterCategory.objects.get_or_create(category="Level 6")
        all, _ = FilterCategory.objects.get_or_create(category="All levels")
        private, _ = FilterCategory.objects.get_or_create(category="Pole private")
        practice, _ = FilterCategory.objects.get_or_create(category="Pole practice")
        conditioning, _ = FilterCategory.objects.get_or_create(category="Pole conditioning")
        dance, _ = FilterCategory.objects.get_or_create(category="Pole dance")
        splits, _ = FilterCategory.objects.get_or_create(category="Splits")

        name_to_category = {
            "All levels": [all],
            "Level 1": [l1],
            "Level 2": [l2],
            "Level 2-3": [l2, l3],
            "Level 2-4": [l2, l3, l4],
            "Level 3-6": [l3, l4, l5, l6],
            "Pole conditioning": [conditioning],
            "Pole dance": [dance],
            "Halloween pole dance": [dance],
            "Pole practice": [practice],
            "Pole private": [private],
            "Splits": [splits],
        }

        def add_categories(qs):
            for name, categories in name_to_category.items():
                objs = qs.filter(name__istartswith=name)
                for obj in objs:
                    for category in categories:
                        obj.categories.add(category)
        
        for obj_qs in [events, ttsessions]:
            add_categories(obj_qs)
        