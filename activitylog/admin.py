from django.contrib import admin
from activitylog.models import ActivityLog

class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp_formatted', 'log')

    def timestamp_formatted(self, obj):
        return obj.timestamp.strftime('%d-%b-%Y %H:%M:%S (%Z)')


admin.site.register(ActivityLog, ActivityLogAdmin)
