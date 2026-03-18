from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender="tenant_grants.Grant")
def deactivate_grant_bank_account_on_close(sender, instance, using=None, **kwargs):
    """
    When a project/grant becomes inactive/ended, make its linked bank account inactive
    so it is not selectable for receipt transactions.
    """
    if not getattr(instance, "bank_account_id", None):
        return

    # Ended if status is not active OR end_date is in the past.
    ended_by_date = bool(getattr(instance, "end_date", None) and instance.end_date < timezone.localdate())
    is_inactive = getattr(instance, "status", None) != instance.Status.ACTIVE
    if not (ended_by_date or is_inactive):
        return

    from tenant_finance.models import BankAccount

    BankAccount.objects.using(using or "default").filter(
        pk=instance.bank_account_id, is_active=True
    ).update(is_active=False)

