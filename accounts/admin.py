from django.contrib import admin

from accounts.models import OnlineDisclaimer, PrintDisclaimer

admin.site.register(OnlineDisclaimer)
admin.site.register(PrintDisclaimer)
