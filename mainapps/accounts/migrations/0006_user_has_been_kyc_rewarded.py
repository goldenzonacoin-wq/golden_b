from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_organisation_physical_address_user_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="has_been_kyc_rewarded",
            field=models.BooleanField(default=False),
        ),
    ]
