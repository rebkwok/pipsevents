from django.contrib.auth.models import Group, User
from django.utils import timezone

from accounts.models import has_active_print_disclaimer, AccountBan


def is_regular_student(self):
    return self.has_perm('booking.is_regular_student')


def has_print_disclaimer(self):
    return has_active_print_disclaimer(self)


def subscribed(self):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in self.groups.all()


def is_instructor(self):
    group, _ = Group.objects.get_or_create(name='instructors')
    return group in self.groups.all()


def currently_banned(self):
    return AccountBan.objects.filter(user=self, end_date__gt=timezone.now()).exists()


User.add_to_class("is_regular_student", is_regular_student)
User.add_to_class("has_print_disclaimer", has_print_disclaimer)
User.add_to_class("subscribed", subscribed)
User.add_to_class("is_instructor", is_instructor)
User.add_to_class("currently_banned", currently_banned)
