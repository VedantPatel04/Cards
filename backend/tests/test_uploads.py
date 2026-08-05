"""
HTTP tests for upload ingest, list, and reassign.

Pipeline behavior lives in tests/services/test_upload_pipeline.py. These cover
the view: auth, validation, wallet scoping, idempotent status codes,
card-mismatch 409, and upload-level reassign.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from apps.transactions.models import Transactions
from apps.uploads.models import Uploads


def _chase_csv(*lines: str) -> bytes:
    header = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo"
    return ("\n".join((header, *lines)) + "\n").encode("utf-8")


SAMPLE_CSV = _chase_csv(
    "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
    "07/08/2026,07/10/2026,MTA*NYCT PAYGO,Travel,Sale,-3.00,",
)


class UploadEndpointTests(APITestCase):
    def setUp(self):
        self.url = reverse("upload_transactions")
        self.list_url = reverse("upload_list")
        self.user_card = seeds.make_user_card()
        self.user = self.user_card.user
        self.client.force_authenticate(user=self.user)

    def _post(self, content: bytes = SAMPLE_CSV, user_card_id=None, filename="stmt.csv"):
        if user_card_id is None:
            user_card_id = self.user_card.pk
        upload = SimpleUploadedFile(filename, content, content_type="text/csv")
        return self.client.post(
            self.url,
            {"file": upload, "user_card_id": user_card_id},
            format="multipart",
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_missing_file(self):
        resp = self.client.post(
            self.url,
            {"user_card_id": self.user_card.pk},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", resp.data["detail"].lower())

    def test_rejects_missing_user_card_id(self):
        upload = SimpleUploadedFile("stmt.csv", SAMPLE_CSV, content_type="text/csv")
        resp = self.client.post(self.url, {"file": upload}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_card_id", resp.data["detail"])

    def test_rejects_foreign_or_unknown_user_card(self):
        stranger = seeds.make_user_card()
        resp = self._post(user_card_id=stranger.pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Uploads.objects.filter(user=self.user).exists())

    def test_rejects_inactive_wallet_card(self):
        self.user_card.is_active = False
        self.user_card.save(update_fields=["is_active"])
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_first_upload_creates_201_and_transactions(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "processed")
        self.assertEqual(resp.data["user_card_id"], self.user_card.pk)
        self.assertEqual(resp.data["summary"]["created"], 2)
        self.assertEqual(resp.data["summary"]["updated"], 0)
        self.assertEqual(Uploads.objects.filter(user=self.user).count(), 1)

    def test_same_bytes_same_card_returns_200_and_updates(self):
        first = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        upload_id = first.data["upload_id"]

        second = self._post()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["upload_id"], upload_id)
        self.assertEqual(second.data["summary"]["created"], 0)
        self.assertEqual(second.data["summary"]["updated"], 2)
        self.assertEqual(Uploads.objects.filter(user=self.user).count(), 1)

    def test_same_bytes_different_card_returns_409(self):
        first = self._post()
        other_card = seeds.make_user_card(user=self.user)

        conflict = self._post(user_card_id=other_card.pk)
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data["upload_id"], first.data["upload_id"])
        self.assertEqual(conflict.data["requested_user_card_id"], other_card.pk)
        self.assertIn(self.user_card.pk, conflict.data["current_user_card_ids"])
        self.assertEqual(
            Transactions.objects.filter(
                upload_id=first.data["upload_id"], user_card=self.user_card
            ).count(),
            2,
        )

    def test_bad_csv_returns_400_and_marks_failed(self):
        bad = b"not,a,chase,file\n1,2,3,4\n"
        resp = self._post(content=bad, filename="bad.csv")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        upload = Uploads.objects.get(user=self.user)
        self.assertEqual(upload.status, "failed")

    def test_list_uploads(self):
        created = self._post()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        item = resp.data["uploads"][0]
        self.assertEqual(item["upload_id"], created.data["upload_id"])
        self.assertEqual(item["user_card_id"], self.user_card.pk)
        self.assertEqual(item["transaction_count"], 2)
        self.assertEqual(item["card_name"], self.user_card.card.name)

    def test_reassign_moves_all_transactions_on_upload(self):
        created = self._post()
        upload_id = created.data["upload_id"]
        other_card = seeds.make_user_card(user=self.user)

        resp = self.client.post(
            reverse("upload_reassign", kwargs={"upload_id": upload_id}),
            {"user_card_id": other_card.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["transactions_updated"], 2)
        self.assertEqual(resp.data["user_card_id"], other_card.pk)
        self.assertEqual(
            Transactions.objects.filter(upload_id=upload_id, user_card=other_card).count(),
            2,
        )
        self.assertFalse(
            Transactions.objects.filter(upload_id=upload_id, user_card=self.user_card).exists()
        )

    def test_reassign_rejects_foreign_upload(self):
        stranger_card = seeds.make_user_card()
        upload = seeds.make_upload(user=stranger_card.user)
        seeds.make_transaction(upload=upload, user_card=stranger_card, row_index=0)

        resp = self.client.post(
            reverse("upload_reassign", kwargs={"upload_id": upload.pk}),
            {"user_card_id": self.user_card.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
