from django.contrib.auth.models import Group, User
from django.utils import timezone

from accounts.models import AccountBan


def subscribed(self):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in self.groups.all()


def is_instructor(self):
    group, _ = Group.objects.get_or_create(name='instructors')
    return group in self.groups.all()


def currently_banned(self):
    return AccountBan.objects.filter(user=self, end_date__gt=timezone.now()).exists()


def has_membership(self):
    return any(mem.is_active() for mem in self.memberships.all())


User.add_to_class("subscribed", subscribed)
User.add_to_class("is_instructor", is_instructor)
User.add_to_class("currently_banned", currently_banned)
User.add_to_class("has_membership", has_membership)
