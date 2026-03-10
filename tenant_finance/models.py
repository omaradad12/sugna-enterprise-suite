from django.db import models

class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class ChartAccount(models.Model):
    """
    Minimal Chart of Accounts for tenant accounting.
    """

    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=Type.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("code",)
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class JournalEntry(models.Model):
    """
    General ledger journal entry header.
    """

    reference = models.CharField(max_length=60, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    entry_date = models.DateField()
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True)
    grant = models.ForeignKey("tenant_grants.Grant", on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-id"]

    def __str__(self) -> str:
        return f"JE#{self.id} {self.entry_date}"


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.account.code} D{self.debit} C{self.credit}"
