"""
Django signals for automatic policy processing
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from ai_engine.models import PolicyFile
from ai_engine.services import PolicyProcessingService


@receiver(post_save, sender=PolicyFile)
def process_policy_file_on_upload(sender, instance, created, **kwargs):
    """
    Automatically process policy file after it's uploaded
    """
    # Only process if it's a new file or if it's been updated and not yet processed
    if created or (not instance.is_processed and instance.is_active):
        # Use transaction.on_commit to ensure the file is saved before processing
        transaction.on_commit(lambda: _process_policy_async(instance.id))


def _process_policy_async(policy_file_id):
    """
    Process policy file asynchronously
    This could be moved to Celery task for better performance
    """
    try:
        policy_file = PolicyFile.objects.get(id=policy_file_id)
        service = PolicyProcessingService()
        chunks_count = service.process_policy_file(policy_file)
        print(f"✅ Successfully processed {policy_file.title}: {chunks_count} chunks created")
    except PolicyFile.DoesNotExist:
        print(f"❌ PolicyFile {policy_file_id} not found")
    except Exception as e:
        print(f"❌ Error processing policy file {policy_file_id}: {str(e)}")
