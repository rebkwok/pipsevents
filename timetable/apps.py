from django.apps import AppConfig

class TimetableConfig(AppConfig):
    name = 'timetable'

    def ready(self):
        import timetable.signals
