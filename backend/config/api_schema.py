"""
Request/response shapes for OpenAPI only.

These serializers document existing view contracts for Swagger Try it out.
They are not used for runtime validation — the views keep their own parsing.
"""

from rest_framework import serializers


class UploadCreateSerializer(serializers.Serializer):
    user_card_id = serializers.IntegerField(
        help_text="Active wallet entry id to attach the statement(s) to.",
    )
    file = serializers.FileField(
        required=False,
        help_text="Single Chase CSV. Prefer this for one file.",
    )
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        help_text="One or more Chase CSVs (batch). Use instead of or with file.",
    )


class UploadReassignSerializer(serializers.Serializer):
    user_card_id = serializers.IntegerField(
        help_text="Active wallet entry id to move this upload's transactions onto.",
    )


class WalletCreateSerializer(serializers.Serializer):
    """Either catalog id OR custom name/issuer/network (not both required)."""

    card_product_id = serializers.IntegerField(
        required=False,
        help_text="Catalog product id. Alternative to name/issuer/network.",
    )
    name = serializers.CharField(required=False)
    issuer = serializers.CharField(required=False)
    network = serializers.CharField(required=False)


class ReviewAnswerSerializer(serializers.Serializer):
    merchant_key = serializers.CharField()
    category = serializers.CharField(
        help_text="dining | groceries | travel | gas | entertainment | shopping | other",
    )


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    confirm = serializers.CharField(
        help_text='Must be the literal string "DELETE".',
    )
