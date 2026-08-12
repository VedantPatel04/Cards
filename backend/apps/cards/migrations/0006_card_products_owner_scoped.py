"""Add owner FK for user-scoped custom cards; split shared customs."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _clone_product_for_owner(Card_Products, source, owner_id):
    """Duplicate a custom Card_Products row for another wallet owner."""
    data = {
        f.name: getattr(source, f.name)
        for f in source._meta.fields
        if f.name not in ("id", "owner")
    }
    data["owner_id"] = owner_id
    data["is_catalog"] = False
    return Card_Products.objects.create(**data)


def assign_custom_owners(apps, schema_editor):
    Card_Products = apps.get_model("cards", "Card_Products")
    User_cards = apps.get_model("users", "User_cards")

    customs = list(Card_Products.objects.filter(is_catalog=False))
    for card in customs:
        owner_ids = list(
            User_cards.objects.filter(card_id=card.pk)
            .values_list("user_id", flat=True)
            .distinct()
            .order_by("user_id")
        )
        if not owner_ids:
            card.delete()
            continue

        primary_id = owner_ids[0]
        card.owner_id = primary_id
        card.save(update_fields=["owner_id"])

        for extra_id in owner_ids[1:]:
            clone = _clone_product_for_owner(Card_Products, card, extra_id)
            User_cards.objects.filter(card_id=card.pk, user_id=extra_id).update(
                card_id=clone.pk
            )


def noop_reverse(apps, schema_editor):
    # Owner nulling is irreversible without knowing prior sharing; leave rows.
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cards", "0005_card_products_reward_currency"),
        ("users", "0002_user_cards"),
    ]

    operations = [
        migrations.AddField(
            model_name="card_products",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="owned_card_products",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_custom_owners, noop_reverse),
        migrations.AlterUniqueTogether(
            name="card_products",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="card_products",
            constraint=models.UniqueConstraint(
                condition=models.Q(("owner__isnull", True)),
                fields=("name", "issuer"),
                name="cards_catalog_name_issuer_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="card_products",
            constraint=models.UniqueConstraint(
                condition=models.Q(("owner__isnull", False)),
                fields=("name", "issuer", "owner"),
                name="cards_custom_name_issuer_owner_uniq",
            ),
        ),
    ]
