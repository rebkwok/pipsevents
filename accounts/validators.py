from django.core.exceptions import ValidationError


def validate_confirm(value):
    if not value:
        raise ValidationError(
            'You must confirm that you accept the disclaimer terms'
        )
