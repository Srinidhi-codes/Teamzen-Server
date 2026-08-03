from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_userdevicesession"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="email_login_alerts",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, receive email alerts for login activity.",
            ),
        ),
    ]
