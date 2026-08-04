"""
Drops the Plaid item store and the Uploads.source discriminator.

With Plaid gone there is exactly one ingestion source, so `source` would be a
column with a single possible value. PlaidItem held access tokens in plaintext,
which is one more reason not to leave the table sitting there unused.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('uploads', '0002_plaid_and_external_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='uploads',
            name='source',
        ),
        migrations.RemoveField(
            model_name='plaiditem',
            name='user',
        ),
        migrations.DeleteModel(
            name='PlaidItem',
        ),
    ]
