from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blockchain', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TokenPurchaseSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_price_usd', models.DecimalField(decimal_places=8, default=Decimal('0'), help_text='Token price in USD.', max_digits=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'blockchain_token_purchase_settings',
                'verbose_name': 'Token Purchase Settings',
                'verbose_name_plural': 'Token Purchase Settings',
            },
        ),
        migrations.CreateModel(
            name='TokenPurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.PositiveIntegerField(db_index=True)),
                ('wallet_address', models.CharField(max_length=64)),
                ('token_amount', models.DecimalField(decimal_places=18, max_digits=30)),
                ('usd_price_per_token', models.DecimalField(decimal_places=8, max_digits=20)),
                ('usd_amount', models.DecimalField(decimal_places=2, max_digits=20)),
                ('charge_amount', models.DecimalField(decimal_places=2, max_digits=20)),
                ('currency', models.CharField(default='USD', max_length=10)),
                ('tx_ref', models.CharField(max_length=120, unique=True)),
                ('flw_ref', models.CharField(blank=True, max_length=120, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('review', 'Review'), ('successful', 'Successful'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('payment_link', models.URLField(blank=True, null=True)),
                ('init_payload', models.JSONField(blank=True, default=dict)),
                ('last_webhook_payload', models.JSONField(blank=True, default=dict)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('transfer_status', models.CharField(choices=[('not_started', 'Not Started'), ('processing', 'Processing'), ('successful', 'Successful'), ('failed', 'Failed')], default='not_started', max_length=20)),
                ('transfer_tx_hash', models.CharField(blank=True, max_length=120, null=True)),
                ('transfer_error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'blockchain_token_purchase',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='tokenpurchase',
            index=models.Index(fields=['user_id', 'status'], name='blockchain_user_id_1a3309_idx'),
        ),
        migrations.AddIndex(
            model_name='tokenpurchase',
            index=models.Index(fields=['tx_ref'], name='blockchain_tx_ref_5a5d37_idx'),
        ),
    ]
