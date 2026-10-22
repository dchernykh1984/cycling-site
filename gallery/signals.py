"""Remove a photo's files with its row: an orphaned original is a public file nobody can find."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from gallery.models import Photo


@receiver(post_delete, sender=Photo)
def delete_photo_files(sender, instance, **kwargs):
    for field in (instance.image, instance.thumbnail):
        if field and field.name:
            field.storage.delete(field.name)
