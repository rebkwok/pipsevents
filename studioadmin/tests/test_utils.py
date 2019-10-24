from model_bakery import baker

from django.test import TestCase

from studioadmin.utils import dechaffify, chaffify, int_str, str_int


class ObscureUserIdTests(TestCase):
    """
    Test methods for obscuring and retrieving user id for/from url
    encoded_id_for_url = int_str(chaffify(user_id))
    user_id = dechaffify(str_int(encoded_id_for_url))
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make_recipe('booking.user')

    def test_encoded_id_with_defaults(self):
        encoded_id = int_str(chaffify(self.user.id))
        self.assertEqual(dechaffify(str_int(encoded_id)), self.user.id)

    def test_encoded_id_with_specified_keyspaces(self):
        encoded_id = int_str(chaffify(self.user.id), 'abcdefghisjkl')
        self.assertEqual(
            dechaffify(str_int(encoded_id, 'abcdefghisjkl')), self.user.id
        )
        # with non-matching keyspaces
        with self.assertRaises(ValueError):
            dechaffify(str_int(encoded_id, 'abcdefghisjk'))

    def test_encoded_id_with_specified_chaff_values(self):
        encoded_id = int_str(chaffify(self.user.id, 12345))
        self.assertEqual(
            dechaffify(str_int(encoded_id), 12345), self.user.id
        )
        # with non-matching chaff
        with self.assertRaises(ValueError):
            dechaffify(str_int(encoded_id), 1234)
