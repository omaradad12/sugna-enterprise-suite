from django.db import models

class Donor(models.Model):
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Grant(models.Model):
    """
    Minimal grant record. Financial postings can be linked via reference/memo in finance module.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="grants")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    award_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class BudgetLine(models.Model):
    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="budget_lines")
    category = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.grant.code}: {self.category}"


class GrantApproval(models.Model):
    """
    Lightweight approval workflow for grants (tenant DB).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="approvals")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey("tenant_users.TenantUser", on_delete=models.PROTECT, related_name="grant_approval_requests")
    decided_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="grant_approval_decisions",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.grant.code} {self.status}"
