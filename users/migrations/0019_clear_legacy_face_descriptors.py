from django.db import migrations


def clear_legacy_face_enrollments(apps, schema_editor):
    """Old block-histogram descriptors are not identity-safe — force re-enroll with FaceNet 128-d."""
    CustomUser = apps.get_model("users", "CustomUser")
    CustomUser.objects.exclude(face_descriptor=None).update(
        face_descriptor=None,
        face_enrolled_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0018_imagefield_max_length_1024"),
    ]

    operations = [
        migrations.RunPython(clear_legacy_face_enrollments, migrations.RunPython.noop),
    ]
