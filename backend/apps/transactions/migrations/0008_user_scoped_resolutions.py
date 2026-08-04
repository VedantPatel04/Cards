"""
Plaid removal + user-scoped merchant overrides.

MerchantResolution is dropped and recreated rather than altered: its primary key
moves from merchant_key to a surrogate id so the same merchant can be labeled
independently by different users. Any existing rows were global, un-owned
labels with no user to attribute them to, so there is nothing to migrate.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0007_category_native_drop_mcc'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transactions',
            name='external_id',
        ),
        migrations.RemoveField(
            model_name='transactions',
            name='is_pending',
        ),
        migrations.AddField(
            model_name='transactions',
            name='merchant_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='transactions',
            name='category',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.DeleteModel(
            name='MerchantResolution',
        ),
        migrations.CreateModel(
            name='MerchantResolution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('merchant_key', models.CharField(max_length=255)),
                ('category', models.CharField(max_length=32)),
                ('source', models.CharField(default='user', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_resolutions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'merchant_key')},
            },
        ),
    ]
