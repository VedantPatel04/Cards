from django.db import migrations, models


def backfill_chase_payment_thank_you(apps, schema_editor):
    """
    Existing rows never stored Chase Type. Mark the common Chase bill-payment
    label so summaries stop treating those credits as spend without a re-upload.

    Statement credits / adjustments are NOT guessed here — re-upload those files
    so the adapter can read Type=Adjustment.
    """
    Transactions = apps.get_model("transactions", "Transactions")
    Transactions.objects.filter(description__icontains="Payment Thank You").update(
        entry_type="payment"
    )


def noop_reverse(apps, schema_editor):
    # Irreversible data fix; schema reverse still drops the column.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0009_globalmerchantalias_transactions_confidence_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transactions",
            name="entry_type",
            field=models.CharField(
                choices=[
                    ("spend", "Spend"),
                    ("refund", "Refund"),
                    ("payment", "Payment"),
                    ("adjustment", "Adjustment"),
                ],
                db_index=True,
                default="spend",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_chase_payment_thank_you, noop_reverse),
    ]
