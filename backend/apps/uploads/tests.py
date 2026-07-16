from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.uploads.models import Uploads

import seeds


class UploadsConstraintTests(TestCase):
    def test_unique_user_file_hash_pair(self):
        user = seeds.make_user()
        seeds.make_upload(user=user, file_hash="abc123")
        # re-uploading the same file (same hash) by the same user is a duplicate
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_upload(user=user, file_hash="abc123")

    def test_same_hash_different_user_allowed(self):
        seeds.make_upload(user=seeds.make_user(), file_hash="shared")
        seeds.make_upload(user=seeds.make_user(), file_hash="shared")
        self.assertEqual(Uploads.objects.filter(file_hash="shared").count(), 2)
