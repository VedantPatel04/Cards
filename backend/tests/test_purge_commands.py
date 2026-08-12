"""Management command tests for purge_users / purge_failed_uploads."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

import seeds
from apps.uploads.models import Uploads
from apps.users.models import CustomUser


class PurgeFailedUploadsCommandTests(TestCase):
    def test_deletes_empty_failed_shells_only(self):
        user = seeds.make_user()
        failed = seeds.make_upload(user=user, status="failed", filename="evil.csv")
        kept = seeds.make_upload(user=user, status="processed")
        entry = seeds.make_user_card(user=user)
        seeds.make_transaction(upload=kept, user_card=entry, row_index=0)

        out = StringIO()
        call_command("purge_failed_uploads", stdout=out)
        self.assertFalse(Uploads.objects.filter(pk=failed.pk).exists())
        self.assertTrue(Uploads.objects.filter(pk=kept.pk).exists())


class PurgeUsersCommandTests(TestCase):
    def test_dry_run_and_yes_delete_probe_users(self):
        probe = seeds.make_user(username="probe_abc123")
        keeper = seeds.make_user(username="vedlo")
        seeds.make_upload(user=probe, status="failed")

        out = StringIO()
        call_command("purge_users", "--dry-run", stdout=out)
        self.assertTrue(CustomUser.objects.filter(pk=probe.pk).exists())

        call_command("purge_users", "--yes", stdout=out)
        self.assertFalse(CustomUser.objects.filter(pk=probe.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=keeper.pk).exists())
        self.assertFalse(Uploads.objects.filter(user_id=probe.pk).exists())

    def test_never_deletes_superuser(self):
        admin = seeds.make_user(username="probe_admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

        call_command("purge_users", "--yes", stdout=StringIO())
        self.assertTrue(CustomUser.objects.filter(pk=admin.pk).exists())
