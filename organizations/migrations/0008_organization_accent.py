# Generated manually for organization accent theme

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0007_organization_llm_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='accent',
            field=models.CharField(
                choices=[
                    ('teal', 'Teal'),
                    ('slate', 'Slate'),
                    ('blue', 'Blue'),
                    ('green', 'Green'),
                    ('indigo', 'Indigo'),
                    ('orange', 'Orange'),
                    ('red', 'Red'),
                    ('purple', 'Purple'),
                ],
                default='teal',
                help_text='Company color theme applied to the employee portal',
                max_length=20,
            ),
        ),
    ]
