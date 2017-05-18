
# TEST UTILS


def _add_user_email_addresses(model):
    # populate foreign key user email addresses for model instances which have
    # FK to user
    for i, instance in enumerate(model.objects.all()):
        if not instance.user.email:
            instance.user.email = 'auto{}.test@test.com'.format(i)
            instance.user.save()
