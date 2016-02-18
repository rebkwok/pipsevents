from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp

class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Configuring facebook social app for test site")

        site = Site.objects.get(id=1)
        site.name = "pipsevents"
        site.save()

        sapp, _ = SocialApp.objects.get_or_create(name="pipsevents",
                                        provider="facebook",
                                        client_id="1533696243550249",
                                        secret="996856479afb90aa366265c7e7c9858f")
        sapp.save()
        sapp.sites.add(1)
