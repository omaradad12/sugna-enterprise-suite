from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="tenant_grants.Grant")
def deactivate_grant_bank_account_on_close(sender, instance, using=None, **kwargs):
    """
    Intentionally no-op: BankAccount.is_active is manual-only (Cash & Bank / edit).
    Grant close, project end, or missing project link must not change bank status.
    """
    return

