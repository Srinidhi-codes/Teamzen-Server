from django.db import migrations, models


LEGACY_TO_CURRENT = {
    "gemini-1.5-flash": "gemini-3.5-flash-lite",
    "gemini-1.5-pro": "gemini-3.5-flash",
    "gemini-2.0-flash": "gemini-3.5-flash-lite",
    "gemini-2.5-flash": "gemini-3.5-flash",
    "gemini-2.5-pro": "gemini-3.5-flash",
}


def remap_legacy_models(apps, schema_editor):
    AIConfiguration = apps.get_model("ai_engine", "AIConfiguration")
    for legacy, current in LEGACY_TO_CURRENT.items():
        AIConfiguration.objects.filter(model_name=legacy).update(model_name=current)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ai_engine", "0007_update_ai_model_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiconfiguration",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("gpt-4o", "GPT-4o (OpenAI Premium)"),
                    ("gpt-4o-mini", "GPT-4o Mini (OpenAI Fast)"),
                    ("gemini-3.5-flash", "Gemini 3.5 Flash (Google Fast)"),
                    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite (Google Efficient)"),
                    ("llama-3.3-70b-versatile", "Llama 3.3 70B (Groq Smart)"),
                    ("llama-3.1-8b-instant", "Llama 3.1 8B (Groq Fast)"),
                ],
                default="gpt-4o",
                max_length=50,
            ),
        ),
        migrations.RunPython(remap_legacy_models, noop_reverse),
    ]
