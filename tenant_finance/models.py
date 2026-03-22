from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def _tenant_check_constraint(*, q, name: str) -> models.CheckConstraint:
    """
    Compatibility helper for mixed Django versions.
    Some versions use `condition=`, others use `check=`.
    """
    try:
        return models.CheckConstraint(condition=q, name=name)
    except TypeError:
        return models.CheckConstraint(check=q, name=name)


def ensure_default_currencies(using: str | None = None) -> None:
    """
    Ensure that a minimal set of base currencies exist for a tenant.

    Called from tenant-facing setup views to guarantee that common currencies
    are available without requiring manual seeding or fixtures.
    """
    db = using or "default"
    from tenant_finance.models import Currency  # local import to avoid circulars

    defaults = [
        ("USD", "US Dollar", "$", 2),
        ("EUR", "Euro", "€", 2),
        ("KSH", "Kenyan Shilling", "KSh", 2),
    ]
    for code, name, symbol, decimal_places in defaults:
        Currency.objects.using(db).get_or_create(
            code=code,
            defaults={
                "name": name,
                "symbol": symbol,
                "decimal_places": decimal_places,
                "status": Currency.Status.ACTIVE,
            },
        )


class Currency(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50, blank=True)
    symbol = models.CharField(max_length=10, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "Currencies"

    def __str__(self) -> str:
        return self.code

    def clean(self) -> None:
        errors = {}
        if self.code:
            if len(self.code) != 3 or not self.code.isalpha():
                errors["code"] = _("Currency code should be a 3-letter ISO code (e.g. USD, EUR).")
        else:
            errors["code"] = _("Currency code is required.")
        if self.decimal_places < 0 or self.decimal_places > 6:
            errors["decimal_places"] = _("Decimal places must be between 0 and 6.")
        if errors:
            raise ValidationError(errors)


class AccountCategory(models.Model):
    """Account groups for financial statement presentation (enterprise chart-of-accounts grouping)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class StatementType(models.TextChoices):
        BALANCE_SHEET = "balance_sheet", "Balance Sheet"
        INCOME_EXPENDITURE = "income_expenditure", "Income & Expenditure"
        CASH_FLOW = "cash_flow", "Cash Flow"

    class CategoryType(models.TextChoices):
        ASSET = "asset", _("Asset")
        LIABILITY = "liability", _("Liability")
        EQUITY = "equity", _("Equity")
        INCOME = "income", _("Income")
        EXPENSE = "expense", _("Expense")

    class NormalBalance(models.TextChoices):
        DEBIT = "debit", _("Debit")
        CREDIT = "credit", _("Credit")

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    statement_type = models.CharField(max_length=30, choices=StatementType.choices, blank=True)
    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        help_text=_("Account class; must align with statement type (Balance Sheet vs Income & Expenditure)."),
    )
    normal_balance = models.CharField(
        max_length=10,
        choices=NormalBalance.choices,
        help_text=_("Debit for Assets & Expenses; Credit for Liabilities, Equity, and Income."),
    )
    parent_category = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_categories",
    )
    is_system = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Protected NGO default categories; critical fields cannot be edited."),
    )
    description = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        blank=True,
    )

    class Meta:
        ordering = ["display_order", "code"]
        verbose_name_plural = "Account categories"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def _default_normal_balance_for_type(self) -> str:
        if self.category_type in (self.CategoryType.ASSET, self.CategoryType.EXPENSE):
            return self.NormalBalance.DEBIT
        return self.NormalBalance.CREDIT

    def get_usage_count(self, using: str | None = None) -> int:
        db = using or getattr(self._state, "db", None) or "default"
        return self.accounts.using(db).count()

    def clean(self) -> None:
        errors: dict = {}
        db = getattr(self._state, "db", None) or "default"

        if not (self.code or "").strip():
            errors["code"] = _("Code is required.")
        if not (self.name or "").strip():
            errors["name"] = _("Name is required.")
        if not self.statement_type:
            errors["statement_type"] = _("Statement type is required.")
        if not self.category_type:
            errors["category_type"] = _("Category class is required.")

        # Normal balance must match accounting convention for the class
        if self.category_type:
            expected_nb = self._default_normal_balance_for_type()
            if not self.normal_balance:
                self.normal_balance = expected_nb
            elif self.normal_balance != expected_nb:
                errors["normal_balance"] = _(
                    "Normal balance must be Debit for Assets and Expenses, and Credit for Liabilities, Equity, and Income."
                )

        # category_type <-> statement_type
        st = self.statement_type or ""
        ct = self.category_type or ""
        if st and ct:
            if st == self.StatementType.BALANCE_SHEET:
                if ct not in (self.CategoryType.ASSET, self.CategoryType.LIABILITY, self.CategoryType.EQUITY):
                    errors["category_type"] = _(
                        "Balance Sheet categories must be Asset, Liability, or Equity."
                    )
            elif st == self.StatementType.INCOME_EXPENDITURE:
                if ct not in (self.CategoryType.INCOME, self.CategoryType.EXPENSE):
                    errors["category_type"] = _(
                        "Income & Expenditure categories must be Income or Expense."
                    )
            elif st == self.StatementType.CASH_FLOW:
                if ct != self.CategoryType.ASSET:
                    errors["category_type"] = _("Cash Flow categories must use the Asset class (e.g. cash).")

        # Parent: same statement section; no self-reference; no cycles
        if self.parent_category_id:
            if self.parent_category_id == self.pk:
                errors["parent_category"] = _("A category cannot be its own parent.")
            else:
                parent = self.parent_category
                if parent and (parent.statement_type or "") != (self.statement_type or ""):
                    errors["parent_category"] = _("Parent must use the same statement type.")
                walk_id = self.parent_category_id
                seen = set()
                while walk_id:
                    if self.pk and walk_id == self.pk:
                        errors["parent_category"] = _("Circular parent hierarchy is not allowed.")
                        break
                    if walk_id in seen:
                        errors["parent_category"] = _("Circular parent hierarchy is not allowed.")
                        break
                    seen.add(walk_id)
                    walk_id = (
                        AccountCategory.objects.using(db)
                        .filter(pk=walk_id)
                        .values_list("parent_category_id", flat=True)
                        .first()
                    )

        old = None
        if self.pk:
            old = (
                AccountCategory.objects.using(db)
                .filter(pk=self.pk)
                .only(
                    "code",
                    "category_type",
                    "statement_type",
                    "normal_balance",
                    "is_system",
                    "parent_category_id",
                )
                .first()
            )

        if old and old.accounts.exists():
            if self.category_type != old.category_type:
                errors["category_type"] = _("Cannot change category class while accounts reference this category.")
            if (self.code or "").strip() != (old.code or "").strip():
                errors["code"] = _("Cannot change code while accounts reference this category.")
            if (self.statement_type or "") != (old.statement_type or ""):
                errors["statement_type"] = _("Cannot change statement type while accounts reference this category.")
            if self.normal_balance != old.normal_balance:
                errors["normal_balance"] = _("Cannot change normal balance while accounts reference this category.")
            if self.parent_category_id != old.parent_category_id:
                errors["parent_category"] = _("Cannot change parent while accounts reference this category.")

        if old and old.is_system:
            for fname in ("code", "category_type", "statement_type", "normal_balance"):
                if getattr(self, fname) != getattr(old, fname):
                    errors[fname] = _("System categories cannot change this field.")
            if not self.is_system:
                errors["is_system"] = _("Cannot remove protection from a system category.")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        skip_validation = kwargs.pop("skip_validation", False)
        if not skip_validation:
            self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError(_("System categories cannot be deleted."))
        db = kwargs.get("using") or getattr(self._state, "db", None) or "default"
        if self.accounts.using(db).exists():
            raise ValidationError(_("Cannot delete a category that is assigned to one or more accounts."))
        return super().delete(*args, **kwargs)


class ChartAccount(models.Model):
    """
    Chart of Accounts for tenant accounting with optional parent and category.
    Only leaf accounts (no children) allow posting; parent/summary accounts are for grouping only.
    """

    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    class StatementType(models.TextChoices):
        BALANCE_SHEET = "balance_sheet", "Balance Sheet"
        INCOME_EXPENDITURE = "income_expenditure", "Income & Expenditure"
        CASH_FLOW = "cash_flow", "Cash Flow"

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=Type.choices)
    statement_type = models.CharField(
        max_length=30,
        choices=StatementType.choices,
        blank=True,
        help_text="Must match account type: Asset/Liability/Equity → Balance Sheet; Income/Expense → Income & Expenditure.",
    )
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    category = models.ForeignKey(
        AccountCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="accounts"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_chartaccount_code"),
        ]
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def is_leaf(self, using: str | None = None) -> bool:
        """True if this account has no children (posting allowed). Parent/summary accounts cannot post."""
        db = using or getattr(self._state, "db", None) or "default"
        return not ChartAccount.objects.using(db).filter(parent_id=self.pk).exists()

    def is_used(self, using: str | None = None) -> bool:
        """True if account is referenced in any transaction or setup (cannot delete; restrict code/type changes)."""
        db = using or "default"
        from tenant_finance.models import (
            BankAccount,
            DefaultAccountMapping,
            JournalLine,
            OpeningBalance,
            PostingRule,
        )

        if JournalLine.objects.using(db).filter(account_id=self.pk).exists():
            return True
        if OpeningBalance.objects.using(db).filter(account_id=self.pk).exists():
            return True
        if BankAccount.objects.using(db).filter(account_id=self.pk).exists():
            return True
        if DefaultAccountMapping.objects.using(db).filter(account_id=self.pk).exists():
            return True
        if PostingRule.objects.using(db).filter(debit_account_id=self.pk).exists():
            return True
        if PostingRule.objects.using(db).filter(credit_account_id=self.pk).exists():
            return True
        return False

    def _statement_type_for_type(self) -> str:
        if self.type in (self.Type.ASSET, self.Type.LIABILITY, self.Type.EQUITY):
            return self.StatementType.BALANCE_SHEET
        if self.type in (self.Type.INCOME, self.Type.EXPENSE):
            return self.StatementType.INCOME_EXPENDITURE
        return ""

    def clean(self) -> None:
        errors = {}

        if not (self.code or "").strip():
            errors["code"] = _("Account code is required.")
        if not (self.name or "").strip():
            errors["name"] = _("Account name is required.")
        if not self.type:
            errors["type"] = _("Account type must be selected.")

        # Statement type must match account type
        expected_st = self._statement_type_for_type()
        if expected_st:
            if self.statement_type and self.statement_type != expected_st:
                errors["statement_type"] = _(
                    "Statement type must match account type: Asset/Liability/Equity use Balance Sheet; "
                    "Income/Expense use Income & Expenditure."
                )
            if not self.statement_type:
                self.statement_type = expected_st

        if self.category and self.category.statement_type:
            cat_ok = (
                self.type in (self.Type.ASSET, self.Type.LIABILITY, self.Type.EQUITY)
                and self.category.statement_type == AccountCategory.StatementType.BALANCE_SHEET
            ) or (
                self.type in (self.Type.INCOME, self.Type.EXPENSE)
                and self.category.statement_type == AccountCategory.StatementType.INCOME_EXPENDITURE
            )
            if not cat_ok:
                errors["category"] = _(
                    "Category statement type must match account type (Balance Sheet vs Income & Expenditure)."
                )

        if self.category and getattr(self.category, "category_type", None):
            if self.type != self.category.category_type:
                errors["category"] = _("Account type must match the category's account class (Asset, Liability, Equity, Income, or Expense).")

        if self.category and self.category.status == AccountCategory.Status.INACTIVE:
            errors["category"] = _("Account category is inactive.")

        if self.parent_id and self.pk and self.parent_id == self.pk:
            errors["parent"] = _("An account cannot be its own parent.")

        if self.parent and self.parent.type != self.type:
            errors["parent"] = _(
                "Parent account must have the same type as the child (e.g. Asset with Asset)."
            )

        # Circular parent hierarchy: walk up parent chain
        _db = getattr(self._state, "db", None) or "default"
        if self.parent_id:
            seen = set()
            if self.pk:
                seen.add(self.pk)
            pk = self.parent_id
            while pk:
                if pk in seen:
                    errors["parent"] = _("Circular parent hierarchy is not allowed.")
                    break
                seen.add(pk)
                next_parent = (
                    ChartAccount.objects.using(_db)
                    .filter(pk=pk)
                    .values_list("parent_id", flat=True)
                    .first()
                )
                pk = next_parent

        if errors:
            raise ValidationError(errors)


class JournalEntry(models.Model):
    """
    General ledger journal entry header with approval workflow.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    reference = models.CharField(max_length=60, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    entry_date = models.DateField()
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True)
    grant = models.ForeignKey("tenant_grants.Grant", on_delete=models.PROTECT, null=True, blank=True)
    dimension = models.ForeignKey(
        "FinancialDimension", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cost_center = models.ForeignKey(
        "CostCenter", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the journal was approved (pending approval → approved)."),
    )
    submitted_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_entries_submitted",
        help_text=_("User who submitted the journal for approval."),
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the journal was submitted for approval (draft → pending approval)."),
    )
    # Disbursement: paid/unpaid and audit
    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"

    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
        blank=True,
    )
    payee_name = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(
        max_length=40,
        blank=True,
        help_text="Payment method for this voucher (e.g. cheque, bank_transfer, cash).",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals",
    )

    # Source / type metadata for manual vs automatic journals
    source = models.CharField(
        max_length=30,
        blank=True,
        help_text="Origin of journal (manual, transaction, reversal, opening_balance, etc.)",
    )
    journal_type = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Manual: adjustment, accrual, correction, opening_balance, reversal. "
        "System: payment_voucher, receipt_voucher, cash_transfer, bank_transfer, fund_transfer, transaction.",
    )

    class AdjustmentType(models.TextChoices):
        """NGO adjusting journal classification (manual adjusting entries)."""

        ACCRUAL = "accrual", _("Accrual")
        PREPAYMENT_ADJUSTMENT = "prepayment_adjustment", _("Prepayment adjustment")
        RECLASSIFICATION = "reclassification", _("Reclassification")
        CORRECTION = "correction", _("Correction")
        DEPRECIATION = "depreciation", _("Depreciation")
        PROVISION = "provision", _("Provision")
        YEAR_END_ADJUSTMENT = "year_end_adjustment", _("Year-end adjustment")
        AUDIT_ADJUSTMENT = "audit_adjustment", _("Audit adjustment")
        OTHER = "other", _("Other")

    posting_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("GL posting date (determines fiscal year and accounting period for posting). Defaults to journal date when omitted."),
    )
    adjustment_type = models.CharField(
        max_length=40,
        choices=AdjustmentType.choices,
        blank=True,
        db_index=True,
    )
    donor = models.ForeignKey(
        "tenant_grants.Donor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_entries",
    )

    class SourceType(models.TextChoices):
        """Master document / posting origin for GL journals (ERP register)."""

        MANUAL = "manual", _("Manual journal")
        PAYMENT_VOUCHER = "payment_voucher", _("Payment voucher")
        RECEIPT_VOUCHER = "receipt_voucher", _("Receipt voucher")
        CASH_TRANSFER = "cash_transfer", _("Cash transfer")
        BANK_TRANSFER = "bank_transfer", _("Bank transfer")
        FUND_TRANSFER = "fund_transfer", _("Fund transfer")
        INTER_FUND_TRANSFER = "inter_fund_transfer", _("Inter-fund transfer")
        POSTING_ENGINE = "posting_engine", _("Posting rule / engine")
        REVERSAL = "reversal", _("Reversal")
        OPENING_BALANCE = "opening_balance", _("Opening balance")
        OTHER = "other", _("Other")

    source_type = models.CharField(
        max_length=40,
        choices=SourceType.choices,
        blank=True,
        db_index=True,
        help_text=_("Type of source transaction that generated this journal."),
    )
    source_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Primary key of the source document (voucher header, transfer record, etc.)."),
    )
    source_document_no = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text=_("Business document number (PV-…, RV-…, transfer ref, etc.)."),
    )
    is_system_generated = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("True when created from vouchers, transfers, or posting engine (not manual JE UI)."),
    )
    posted_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_entries_posted",
        help_text=_("User who posted the journal to the general ledger."),
    )

    class Meta:
        ordering = ["-entry_date", "-id"]

    def __str__(self) -> str:
        return f"JE#{self.id} {self.entry_date}"

    def delete(self, using=None, keep_parents: bool = False):
        """
        Enforce stricter accounting controls:
        - Posted or approved journals must never be hard-deleted.
        - Corrections should be made via reversal entries referencing the original voucher.
        - System-generated posted journals follow the same rule.
        """
        if self.status in (
            self.Status.APPROVED,
            self.Status.POSTED,
            self.Status.REVERSED,
        ):
            raise ValidationError(
                {
                    "status": _(
                        "Approved or posted journal entries cannot be deleted. "
                        "Use a reversal journal to correct mistakes."
                    )
                }
            )
        return super().delete(using=using, keep_parents=keep_parents)

    def save(self, *args, **kwargs) -> None:
        """
        Enforce strict editing rules:
        - Journals can only be edited while in Draft or Pending Approval.
        - Posted journals are locked and cannot be edited, except for a status transition
          from POSTED to REVERSED as part of an authorized reversal workflow.
        - Approved or reversed journals cannot be edited at all; use a reversal instead.
        """
        db = kwargs.get("using") or getattr(self._state, "db", None) or "default"
        if self.pk:
            db = kwargs.get("using") or getattr(self._state, "db", None) or "default"
            original = (
                JournalEntry.objects.using(db)
                .only(
                    "status",
                    "is_system_generated",
                    "entry_date",
                    "memo",
                    "reference",
                    "grant_id",
                    "currency_id",
                    "dimension_id",
                    "cost_center_id",
                    "payment_status",
                    "payee_name",
                    "payment_method",
                    "source",
                    "journal_type",
                    "source_type",
                    "source_id",
                    "source_document_no",
                    "posting_date",
                    "adjustment_type",
                    "donor_id",
                    "submitted_by_id",
                    "submitted_at",
                    "approved_at",
                )
                .filter(pk=self.pk)
                .first()
            )
            if original:
                # Only allow edits when the original journal is in a mutable status
                if original.status not in (
                    self.Status.DRAFT,
                    self.Status.PENDING_APPROVAL,
                    self.Status.POSTED,
                ):
                    raise ValidationError(
                        {
                            "status": _(
                                "Approved or reversed journal entries cannot be edited. "
                                "Use a reversal journal to correct mistakes."
                            )
                        }
                    )

                # Posted journals are locked except for a controlled POSTED -> REVERSED transition
                if original.status == self.Status.POSTED and self.status != self.Status.REVERSED:
                    raise ValidationError(
                        {
                            "status": _(
                                "Posted journal entries are locked and cannot be edited. "
                                "Create a reversal journal instead."
                            )
                        }
                    )
                # System-generated journals: no header edits after posting (same as posted lock above)
                if (
                    original.is_system_generated
                    and original.status == self.Status.POSTED
                    and self.status == self.Status.POSTED
                ):
                    frozen = {
                        "entry_date",
                        "memo",
                        "reference",
                        "grant_id",
                        "currency_id",
                        "dimension_id",
                        "cost_center_id",
                        "payment_status",
                        "payee_name",
                        "payment_method",
                        "source",
                        "journal_type",
                        "source_type",
                        "source_id",
                        "source_document_no",
                        "is_system_generated",
                        "posting_date",
                        "adjustment_type",
                        "donor_id",
                        "submitted_by_id",
                        "submitted_at",
                        "approved_at",
                    }
                    for fname in frozen:
                        if getattr(self, fname) != getattr(original, fname):
                            raise ValidationError(
                                {
                                    "__all__": _(
                                        "This journal was generated from a source transaction and cannot be edited."
                                    )
                                }
                            )
                # Enforce posting controls on POSTED transition
                if original.status != self.Status.POSTED and self.status == self.Status.POSTED:
                    from tenant_finance.services.period_control import assert_can_post_journal

                    gl_date = self.posting_date or self.entry_date
                    try:
                        assert_can_post_journal(using=db, entry_date=gl_date, grant=self.grant, user=self.created_by)
                    except ValueError as exc:
                        raise ValidationError({"posting_date": _(str(exc)), "entry_date": _(str(exc))})
                    # Budget control check (line-level) before posting
                    from tenant_finance.services.budget_control import BudgetControlEngine

                    engine = BudgetControlEngine(db)
                    rule = engine._get_rules()
                    if getattr(rule, "check_before_posting", True):
                        result = engine.check_entry(self)
                        if result.status in ("warn", "critical"):
                            engine.log_event(
                                entry=self,
                                result=result,
                                event_type=BudgetEvent.EventType.WARN,
                                user=getattr(self, "created_by", None),
                            )
                        if result.status == "block":
                            # Allow posting only if there's an approved override request
                            if not engine.get_approved_override_for_entry(self):
                                engine.log_event(
                                    entry=self,
                                    result=result,
                                    event_type=BudgetEvent.EventType.BLOCK,
                                    user=getattr(self, "created_by", None),
                                )
                                raise ValidationError({"status": _(result.message or "Budget control blocked posting.")})
        else:
            # New record posted directly (common in posting window) must also pass posting controls.
            if self.status == self.Status.POSTED:
                from tenant_finance.services.period_control import assert_can_post_journal

                gl_date = self.posting_date or self.entry_date
                try:
                    assert_can_post_journal(using=db, entry_date=gl_date, grant=self.grant, user=self.created_by)
                except ValueError as exc:
                    raise ValidationError({"posting_date": _(str(exc)), "entry_date": _(str(exc))})
                from tenant_finance.services.budget_control import BudgetControlEngine

                engine = BudgetControlEngine(db)
                rule = engine._get_rules()
                if getattr(rule, "check_before_posting", True):
                    result = engine.check_entry(self)
                    if result.status in ("warn", "critical"):
                        engine.log_event(
                            entry=self,
                            result=result,
                            event_type=BudgetEvent.EventType.WARN,
                            user=getattr(self, "created_by", None),
                        )
                    if result.status == "block":
                        if not engine.get_approved_override_for_entry(self):
                            engine.log_event(
                                entry=self,
                                result=result,
                                event_type=BudgetEvent.EventType.BLOCK,
                                user=getattr(self, "created_by", None),
                            )
                            raise ValidationError({"status": _(result.message or "Budget control blocked posting.")})
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        """Validate grant/project dates for transactions (baseline validation)."""
        errors = {}
        if self.grant_id and self.donor_id and self.grant.donor_id != self.donor_id:
            errors["donor"] = _("Donor must match the selected grant's donor.")
        if not self.grant_id:
            if errors:
                raise ValidationError(errors)
            return
        grant = self.grant
        # Only active grants can be used in transactions
        if grant.status != "active":
            errors["grant"] = _("Only active grants can be used in transactions.")
        dates_to_check = []
        for d in (self.entry_date, self.posting_date):
            if d and d not in dates_to_check:
                dates_to_check.append(d)
        effective_grant_end = getattr(grant, "effective_end_date", None)
        effective_grant_end = effective_grant_end() if callable(effective_grant_end) else getattr(grant, "end_date", None)
        for d in dates_to_check:
            field_label = "posting_date" if (self.posting_date and d == self.posting_date) else "entry_date"
            if grant.start_date and d and d < grant.start_date:
                errors[field_label] = _("Transaction date must be on or after grant start date (%(start)s).") % {
                    "start": grant.start_date
                }
            if effective_grant_end and d and d > effective_grant_end:
                errors[field_label] = _("Transaction date must be on or before grant end date (%(end)s).") % {
                    "end": effective_grant_end
                }
        if grant.project_id:
            project = grant.project
            if not getattr(project, "is_open_for_transactions", False):
                errors["grant"] = _(
                    "Only grants linked to active projects can be used in transactions."
                )
            effective_project_end = getattr(project, "effective_end_date", None)
            effective_project_end = effective_project_end() if callable(effective_project_end) else getattr(project, "end_date", None)
            for d in dates_to_check:
                field_label = "posting_date" if (self.posting_date and d == self.posting_date) else "entry_date"
                if project.start_date and d and d < project.start_date:
                    errors[field_label] = _("Transaction date must be on or after project start date (%(start)s).") % {
                        "start": project.start_date
                    }
                if effective_project_end and d and d > effective_project_end:
                    errors[field_label] = _("Transaction date must be on or before project end date (%(end)s).") % {
                        "end": effective_project_end
                    }
        else:
            errors["grant"] = _("Grant must belong to a project for transaction posting.")
        if errors:
            raise ValidationError(errors)


def get_grant_posted_expense_total(grant_id, using: str):
    """Total posted expense (debits to expense accounts) for this grant. Used to enforce grant budget."""
    from decimal import Decimal
    from django.db.models import Sum

    return (
        JournalLine.objects.using(using)
        .filter(
            entry__grant_id=grant_id,
            entry__status=JournalEntry.Status.POSTED,
            account__type=ChartAccount.Type.EXPENSE,
        )
        .aggregate(t=Sum("debit"))
        .get("t")
        or Decimal("0")
    )


class JournalEntryAttachment(models.Model):
    """Document attached to a journal entry."""

    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="finance/journal_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_lines",
    )
    project_budget_line = models.ForeignKey(
        "tenant_grants.ProjectBudgetLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_lines",
        help_text="Project budget line for expense tracking (NGO activity-based budgeting).",
    )
    workplan_activity = models.ForeignKey(
        "tenant_grants.WorkplanActivity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_lines",
        help_text="Grant workplan activity for expense tagging.",
    )
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["project_budget_line"]),
            models.Index(fields=["workplan_activity"]),
        ]

    def __str__(self) -> str:
        return f"{self.account.code} D{self.debit} C{self.credit}"


class PaymentRegister(models.Model):
    """
    Record of a payment disbursement: links a paid payment voucher to cheque/transfer
    details and transaction type. Used for payment register reporting and audit.
    """

    class TransactionType(models.TextChoices):
        PAYMENT_VOUCHER = "payment_voucher", "Payment Voucher"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        CASH = "cash", "Cash"

    entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="payment_register_record",
    )
    paid_at = models.DateTimeField()
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
        default=TransactionType.PAYMENT_VOUCHER,
    )
    cheque_number = models.CharField(max_length=60, blank=True)
    transfer_reference = models.CharField(max_length=120, blank=True)
    payment_method = models.CharField(max_length=40, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"Payment {self.entry.reference} @ {self.paid_at}"


class RecurringJournal(models.Model):
    """Template for recurring journal entries (e.g. monthly rent, NGO project allocations)."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=120)
    reference_prefix = models.CharField(max_length=30, blank=True)  # e.g. "RENT"
    description = models.TextField(blank=True)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    start_date = models.DateField(help_text="Schedule start; first run uses this date.")
    end_date = models.DateField(null=True, blank=True, help_text="Optional; template completes after last run in range.")
    next_run_date = models.DateField(null=True, blank=True)
    last_run_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RecurringJournalLine(models.Model):
    """One line of a recurring journal template."""

    recurring_journal = models.ForeignKey(
        RecurringJournal, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recurring_journal_lines",
        help_text="Optional project/grant dimension for NGO reporting.",
    )
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]


class FiscalYear(models.Model):
    """Fiscal year for period management."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=40)  # e.g. "FY2025"
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            _tenant_check_constraint(
                q=models.Q(start_date__lt=models.F("end_date")),
                name="fiscalyear_start_before_end",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        errors = {}
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = _("End date must be after start date.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        """
        If a fiscal year is closed, all periods become hard closed.
        """
        using = kwargs.get("using") or getattr(self._state, "db", None) or "default"
        is_update = bool(self.pk)
        prev = None
        if is_update:
            prev = FiscalYear.objects.using(using).filter(pk=self.pk).values("is_closed", "status").first()
        super().save(*args, **kwargs)
        now_closed = bool(self.is_closed or self.status == self.Status.CLOSED)
        was_closed = bool(prev and (prev.get("is_closed") or prev.get("status") == self.Status.CLOSED))
        if now_closed and not was_closed:
            FiscalPeriod.objects.using(using).filter(fiscal_year=self).update(
                is_closed=True,
                status=FiscalPeriod.Status.HARD_CLOSED,
            )


class FiscalPeriod(models.Model):
    """Accounting period within a fiscal year."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SOFT_CLOSED = "soft_closed", "Soft closed"
        HARD_CLOSED = "hard_closed", "Hard closed"

    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name="periods")
    period_number = models.PositiveSmallIntegerField()  # 1-12 or 1-4 for quarters
    name = models.CharField(max_length=40, blank=True)  # e.g. "Jan 2025"
    period_name = models.CharField(max_length=60, blank=True)  # display name
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    closed_reason = models.TextField(blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reopened_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        ordering = ["fiscal_year", "period_number"]
        unique_together = ("fiscal_year", "period_number")
        constraints = [
    _tenant_check_constraint(
        q=models.Q(start_date__lt=models.F("end_date")),
        name="fiscalperiod_start_before_end",
    ),
]
    def __str__(self) -> str:
        return f"{self.fiscal_year.name} P{self.period_number}"

    def clean(self) -> None:
        errors = {}
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = _("End date must be after start date.")
        # Ensure period dates fall within fiscal year
        if self.fiscal_year_id and self.start_date and self.end_date:
            fy = self.fiscal_year
            if self.start_date < fy.start_date or self.end_date > fy.end_date:
                msg = _("Period dates must fall within the fiscal year dates.")
                errors["start_date"] = msg
                errors["end_date"] = msg
        if errors:
            raise ValidationError(errors)

    def is_posting_allowed(self, *, user=None) -> bool:
        """
        Posting rules:
        - OPEN: allowed
        - HARD_CLOSED: never allowed
        - SOFT_CLOSED: allowed only for authorized roles
        """
        if self.status == self.Status.OPEN and not self.is_closed:
            return True
        if self.status == self.Status.HARD_CLOSED or self.is_closed:
            # Treat legacy is_closed as hard close
            if self.status != self.Status.SOFT_CLOSED:
                return False
        if self.status != self.Status.SOFT_CLOSED:
            return False
        # soft-closed exception check
        setting = PeriodControlSetting.get_solo(using=getattr(self._state, "db", None) or "default")
        return setting.user_can_post_in_soft_closed(user)


class PeriodControlSetting(models.Model):
    """Tenant-scoped settings for period control exceptions and reopening authorization."""

    soft_close_allowed_roles = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated role names allowed to post in soft-closed periods.",
    )
    reopen_allowed_roles = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated role names allowed to reopen periods (requires reason).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls, *, using: str):
        obj = cls.objects.using(using).order_by("id").first()
        if obj:
            # Safety: ensure enterprise defaults are present even on older rows
            obj._ensure_enterprise_defaults(using=using)
            return obj
        return cls.objects.using(using).create(
            soft_close_allowed_roles="finance manager,admin,tenant admin",
            reopen_allowed_roles="finance manager,admin,tenant admin",
        )

    def _norm_role(self, v: str) -> str:
        return (v or "").strip().lower().replace("_", "").replace(" ", "")

    def _role_set(self, raw: str) -> set[str]:
        return {self._norm_role(r) for r in (raw or "").split(",") if r.strip()}

    def _ensure_enterprise_defaults(self, *, using: str) -> None:
        """
        Keep compatibility when earlier deployments created settings rows
        without the newer enterprise default roles.
        """
        desired_soft = {"financemanager", "admin", "tenantadmin"}
        desired_reopen = {"financemanager", "admin", "tenantadmin"}
        soft = self._role_set(self.soft_close_allowed_roles)
        reopen = self._role_set(self.reopen_allowed_roles)
        changed = False
        if not desired_soft.issubset(soft):
            merged = sorted(soft.union(desired_soft))
            self.soft_close_allowed_roles = ", ".join(merged)
            changed = True
        if not desired_reopen.issubset(reopen):
            merged = sorted(reopen.union(desired_reopen))
            self.reopen_allowed_roles = ", ".join(merged)
            changed = True
        if changed:
            self.save(using=using, update_fields=["soft_close_allowed_roles", "reopen_allowed_roles", "updated_at"])

    def user_has_role(self, user, raw: str) -> bool:
        if not user:
            return False
        allowed = self._role_set(raw)
        if not allowed:
            return False
        role_name = self._norm_role(getattr(user, "role_name", "") or "")
        if role_name and role_name in allowed:
            return True
        roles = getattr(user, "roles", None)
        if roles:
            try:
                for r in roles:
                    nm = self._norm_role(getattr(r, "name", "") or str(r) or "")
                    if nm and nm in allowed:
                        return True
            except Exception:
                pass
        # RBAC mapping (common path in this codebase)
        try:
            from rbac.models import UserRole

            ur = UserRole.objects.using(getattr(user._state, "db", None) or "default").filter(user=user).select_related("role").first()
            if ur and ur.role_id:
                nm = self._norm_role(getattr(ur.role, "name", "") or "")
                if nm and nm in allowed:
                    return True
        except Exception:
            pass
        return False

    def user_can_post_in_soft_closed(self, user) -> bool:
        return self.user_has_role(user, self.soft_close_allowed_roles)

    def user_can_reopen(self, user) -> bool:
        return self.user_has_role(user, self.reopen_allowed_roles)


class PeriodActionLog(models.Model):
    """Immutable audit log for period actions (open/soft close/hard close/reopen)."""

    class Action(models.TextChoices):
        OPEN = "open", "Open"
        SOFT_CLOSE = "soft_close", "Soft close"
        HARD_CLOSE = "hard_close", "Hard close"
        REOPEN = "reopen", "Reopen"

    period = models.ForeignKey(FiscalPeriod, on_delete=models.CASCADE, related_name="action_logs")
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name="+")
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    user = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OpeningBalance(models.Model):
    """Opening balance for an account as of a date (e.g. system go-live)."""

    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    as_of_date = models.DateField()
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account", "as_of_date"]
        unique_together = ("account", "as_of_date")

    def __str__(self) -> str:
        return f"{self.account.code} @ {self.as_of_date}"


class BankAccount(models.Model):
    """Master data for organisational bank accounts used for receipts/payments/transfers."""

    bank_name = models.CharField(max_length=120)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=60, unique=True)
    branch = models.CharField(max_length=120, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True)
    office = models.CharField(max_length=120, blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_balance_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bank_name", "account_name"]

    def __str__(self) -> str:
        return f"{self.bank_name} — {self.account_name} ({self.account_number})"


class AuditLog(models.Model):
    """Audit trail for financial transaction changes."""

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    model_name = models.CharField(max_length=80, db_index=True)  # e.g. "journalentry"
    object_id = models.PositiveIntegerField(db_index=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    user_id = models.PositiveIntegerField(null=True, blank=True)  # TenantUser id
    username = models.CharField(max_length=150, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    summary = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.model_name}#{self.object_id}"


# ----- Financial Setup (configuration center) -----


class FinancialDimension(models.Model):
    """Financial dimensions for transaction analysis (Department, Program, Location, Project, etc.)."""

    class DimensionType(models.TextChoices):
        DEPARTMENT = "department", "Department"
        PROJECT = "project", "Project"
        LOCATION = "location", "Location"
        PROGRAM = "program", "Program"
        GRANT = "grant", "Grant"
        ACTIVITY = "activity", "Activity"
        CUSTOM = "custom", "Custom"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    dimension_code = models.CharField(max_length=30, unique=True)
    dimension_name = models.CharField(max_length=120)
    dimension_type = models.CharField(max_length=20, choices=DimensionType.choices)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["dimension_code"]

    def __str__(self) -> str:
        return f"{self.dimension_code} — {self.dimension_name}"

    def clean(self) -> None:
        """
        Backend validation for dimensions:
        - Code unique and non-empty
        - Name non-empty
        - Type selected
        """
        errors = {}
        if not self.dimension_code:
            errors["dimension_code"] = _("Dimension code is required.")
        if not self.dimension_name:
            errors["dimension_name"] = _("Dimension name is required.")
        if not self.dimension_type:
            errors["dimension_type"] = _("Dimension type is required.")
        if errors:
            raise ValidationError(errors)


class CostCenter(models.Model):
    """Cost centers for accounting and allocation; hierarchical via parent."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    manager = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "Cost centers"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def clean(self) -> None:
        """
        Backend validation for cost centers:
        - Code non-empty (uniqueness enforced at DB)
        - Name non-empty
        - Parent cannot be itself
        """
        errors = {}
        if not self.code:
            errors["code"] = _("Cost center code is required.")
        if not self.name:
            errors["name"] = _("Cost center name is required.")
        if self.parent_id and self.pk and self.parent_id == self.pk:
            errors["parent"] = _("Cost center cannot be its own parent.")
        if errors:
            raise ValidationError(errors)


class GrantDimension(models.Model):
    """Grant dimension configuration (links to donor; used for reporting/segmentation)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    grant_code = models.CharField(max_length=50, unique=True)
    grant_name = models.CharField(max_length=200)
    donor = models.ForeignKey(
        "tenant_grants.Donor", on_delete=models.PROTECT, related_name="+"
    )
    project = models.CharField(max_length=120, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["grant_code"]

    def __str__(self) -> str:
        return f"{self.grant_code} — {self.grant_name}"


class ProjectDimensionMapping(models.Model):
    """
    Project posting & default mapping configuration.

    Used by transaction posting validations and defaulting:
    - cost center / bank account / donor / currency defaults
    - optional budget line and default debit/credit accounts
    - active period window for policy changes over time
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    project = models.OneToOneField(
        "tenant_grants.Project",
        on_delete=models.CASCADE,
        related_name="dimension_mapping",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        blank=True,
    )
    active_from = models.DateField(null=True, blank=True)
    active_to = models.DateField(null=True, blank=True)
    budget_line = models.ForeignKey(
        "tenant_grants.BudgetLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional default budget line for postings on this project.",
    )
    default_debit_account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional default debit account (fallback when posting rules are not configured).",
    )
    default_credit_account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional default credit account (fallback when posting rules are not configured).",
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    donor = models.ForeignKey(
        "tenant_grants.Donor", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__code"]
        verbose_name = "Project dimension mapping"
        verbose_name_plural = "Project dimension mappings"

    def __str__(self) -> str:
        return (
            f"{self.project.code} → "
            f"{self.cost_center.code if self.cost_center_id else '—'} → "
            f"{self.bank_account.account_number if self.bank_account_id else '—'} → "
            f"{self.donor.code if self.donor_id else '—'} → "
            f"{self.currency.code if self.currency_id else '—'}"
        )

    def is_active_on(self, dt) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if dt and self.active_from and dt < self.active_from:
            return False
        if dt and self.active_to and dt > self.active_to:
            return False
        return True

    def clean(self) -> None:
        errors = {}
        if (
            self.default_debit_account_id
            and self.default_credit_account_id
            and self.default_debit_account_id == self.default_credit_account_id
        ):
            msg = _("Default debit and credit accounts cannot be the same.")
            errors["default_debit_account"] = msg
            errors["default_credit_account"] = msg
        if self.active_from and self.active_to and self.active_from > self.active_to:
            errors["active_to"] = _("Active to date must be on or after active from date.")
        if errors:
            raise ValidationError(errors)


class ExchangeRate(models.Model):
    """Exchange rate: from currency to base currency, effective date."""

    class RateType(models.TextChoices):
        SPOT = "spot", "Spot"
        MONTHLY = "monthly", "Monthly"
        MANUAL = "manual", "Manual"

    class Source(models.TextChoices):
        BANK = "bank", "Bank"
        MANUAL = "manual", "Manual"
        LIVE_SERVICE = "live_service", "Live FX service"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    currency = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="exchange_rates_from"
    )
    base_currency = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="exchange_rates_to"
    )
    rate = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    effective_date = models.DateField(db_index=True)
    rate_type = models.CharField(
        max_length=20, choices=RateType.choices, default=RateType.SPOT, db_index=True
    )
    source = models.CharField(
        max_length=40, choices=Source.choices, default=Source.MANUAL, blank=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_date", "currency"]
        unique_together = ("currency", "base_currency", "effective_date")

    def __str__(self) -> str:
        return f"{self.currency.code}/{self.base_currency.code} = {self.rate} on {self.effective_date}"

    def clean(self) -> None:
        errors = {}
        if self.currency_id and self.base_currency_id and self.currency_id == self.base_currency_id:
            errors["base_currency"] = _("Base currency must be different from currency.")
        if self.rate is not None and self.rate <= 0:
            errors["rate"] = _("Exchange rate must be greater than zero.")
        if errors:
            raise ValidationError(errors)


def get_effective_exchange_rate(
    *, using: str, from_currency: Currency, base_currency: Currency, as_of_date
) -> ExchangeRate | None:
    """
    Return the latest ACTIVE exchange rate for a currency pair whose effective_date
    is on or before as_of_date. Used when posting transactions.
    """
    return (
        ExchangeRate.objects.using(using)
        .filter(
            currency=from_currency,
            base_currency=base_currency,
            status=ExchangeRate.Status.ACTIVE,
            effective_date__lte=as_of_date,
        )
        .order_by("-effective_date")
        .first()
    )


class DocumentSeries(models.Model):
    """Numbering and document series for financial documents (e.g. PV-2026-00001)."""

    class DocumentType(models.TextChoices):
        PAYMENT_VOUCHER = "payment_voucher", "Payment Voucher"
        RECEIPT_VOUCHER = "receipt_voucher", "Receipt Voucher"
        JOURNAL = "journal", "Journal Entry"
        DISBURSEMENT = "disbursement", "Disbursement"
        VENDOR_PAYMENT = "vendor_payment", "Vendor Payment"
        GRANT_RECEIPT = "grant_receipt", "Grant Receipt"

    class ResetFrequency(models.TextChoices):
        YEARLY = "yearly", "Yearly"
        MONTHLY = "monthly", "Monthly"
        NEVER = "never", "Never"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class Scope(models.TextChoices):
        GLOBAL = "global", "Global"
        PROJECT = "project", "Project"
        GRANT = "grant", "Grant"

    document_type = models.CharField(max_length=40, choices=DocumentType.choices)
    prefix = models.CharField(max_length=20)
    start_number = models.PositiveIntegerField(default=1)
    current_number = models.PositiveIntegerField(default=0)
    number_format = models.CharField(
        max_length=80,
        default="{prefix}{year}-{seq:05d}",
        help_text=(
            "Python-style format string using prefix, year, seq. "
            "Example: 'PV-{year}-{seq:05d}'"
        ),
    )
    fiscal_year = models.ForeignKey(
        "tenant_finance.FiscalYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_series",
        help_text="Optional: limit this series to a specific fiscal year.",
    )
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.GLOBAL,
        db_index=True,
        help_text="Scope of the sequence: global, per project, or per grant.",
    )
    project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Project for project-scoped sequences (optional).",
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Grant for grant-scoped sequences (optional).",
    )
    reset_frequency = models.CharField(
        max_length=20,
        choices=ResetFrequency.choices,
        default=ResetFrequency.YEARLY,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type", "prefix"]
        verbose_name = "Document series"
        verbose_name_plural = "Document series"
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "fiscal_year", "prefix", "scope", "project", "grant"],
                name="uniq_documentseries_type_year_prefix_scope",
            ),
        ]

    def __str__(self) -> str:
        fy = f" ({self.fiscal_year.name})" if self.fiscal_year_id else ""
        return f"{self.get_document_type_display()} — {self.prefix}{fy}"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.scope == self.Scope.PROJECT and not self.project_id:
            errors["project"] = _("Project is required when scope is Project.")
        if self.scope != self.Scope.PROJECT and self.project_id:
            errors["project"] = _("Project must be empty unless scope is Project.")
        if self.scope == self.Scope.GRANT and not self.grant_id:
            errors["grant"] = _("Grant is required when scope is Grant.")
        if self.scope != self.Scope.GRANT and self.grant_id:
            errors["grant"] = _("Grant must be empty unless scope is Grant.")
        if self.start_number < 1:
            errors["start_number"] = _("Start number must be at least 1.")
        if self.current_number < 0:
            errors["current_number"] = _("Current number cannot be negative.")
        if self.current_number and self.current_number < self.start_number - 1:
            errors["current_number"] = _(
                "Current number cannot be less than start number minus one."
            )

        # Validate format tokens
        from tenant_finance.services.numbering import validate_number_format

        fmt_errors = validate_number_format(self.number_format)
        if fmt_errors:
            errors["number_format"] = " ".join(fmt_errors)

        # Enforce at most one active series per document type and fiscal year.
        if self.status == self.Status.ACTIVE:
            qs = DocumentSeries.objects.all()
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            qs = qs.filter(
                document_type=self.document_type,
                fiscal_year_id=self.fiscal_year_id,
                scope=self.scope,
                project_id=self.project_id,
                grant_id=self.grant_id,
                status=DocumentSeries.Status.ACTIVE,
            )
            if qs.exists():
                errors["status"] = _(
                    "There is already an active series for this document type and fiscal year."
                )

        if errors:
            raise ValidationError(errors)

    def _is_used(self, using: str) -> bool:
        from tenant_finance.models import DocumentSequenceCounter

        if self.current_number and self.current_number > 0:
            return True
        return DocumentSequenceCounter.objects.using(using).filter(series=self).exists()

    def save(self, *args, **kwargs) -> None:
        using = kwargs.get("using") or getattr(self._state, "db", None) or "default"
        if self.pk:
            original = (
                DocumentSeries.objects.using(using)
                .filter(pk=self.pk)
                .values(
                    "document_type",
                    "prefix",
                    "number_format",
                    "fiscal_year_id",
                    "scope",
                    "project_id",
                    "grant_id",
                    "reset_frequency",
                    "start_number",
                )
                .first()
            )
            if original and self._is_used(using):
                immutable = (
                    "document_type",
                    "prefix",
                    "number_format",
                    "fiscal_year_id",
                    "scope",
                    "project_id",
                    "grant_id",
                    "reset_frequency",
                    "start_number",
                )
                changed = [k for k in immutable if str(original.get(k)) != str(getattr(self, k))]
                if changed:
                    raise ValidationError(
                        {"__all__": _("Cannot edit document series once it has been used.")}
                    )
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents: bool = False):
        _using = using or getattr(self._state, "db", None) or "default"
        if self.pk and self._is_used(_using):
            raise ValidationError(
                {"__all__": _("Cannot delete document series once it has been used. Deactivate it instead.")}
            )
        return super().delete(using=using, keep_parents=keep_parents)


class DocumentSequenceCounter(models.Model):
    """
    Sequence counter per DocumentSeries and scope (global/project/grant) with reset periods.
    """

    series = models.ForeignKey(DocumentSeries, on_delete=models.CASCADE, related_name="counters")
    period_key = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Reset period key (e.g. 2026, 2026-03, all).",
    )
    project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    current_number = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["series", "period_key", "project", "grant"],
                name="uniq_docseries_counter_series_period_scope",
            )
        ]


class DocumentNumberLog(models.Model):
    """Audit record for each generated document/voucher number."""

    series = models.ForeignKey(DocumentSeries, on_delete=models.PROTECT, related_name="generated_numbers")
    value = models.CharField(max_length=120, unique=True, db_index=True)
    seq = models.PositiveIntegerField()
    period_key = models.CharField(max_length=20, db_index=True)
    document_type = models.CharField(max_length=40, db_index=True)
    scope = models.CharField(max_length=20, db_index=True)
    project = models.ForeignKey("tenant_grants.Project", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    grant = models.ForeignKey("tenant_grants.Grant", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]



class VoucherNumbering(models.Model):
    """Automatic voucher numbering configuration."""

    voucher_type = models.CharField(max_length=40, unique=True)
    prefix = models.CharField(max_length=20)
    sequence_length = models.PositiveSmallIntegerField(default=5)
    reset_yearly = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["voucher_type"]

    def __str__(self) -> str:
        return f"{self.voucher_type} — {self.prefix}"

    def clean(self) -> None:
        errors = {}
        if not self.voucher_type:
            errors["voucher_type"] = _("Voucher type is required.")
        if self.sequence_length < 1 or self.sequence_length > 10:
            errors["sequence_length"] = _("Sequence length must be between 1 and 10.")
        if errors:
            raise ValidationError(errors)


class PostingRule(models.Model):
    """Accounting posting logic (e.g. Receipt -> Debit Bank, Credit Income)."""

    class TransactionType(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        PAYMENT = "payment", "Payment"
        JOURNAL = "journal", "Journal"
        TRANSFER = "transfer", "Transfer"

    class Dimension(models.TextChoices):
        NONE = "none", "None"
        PROJECT = "project", "Project"
        GRANT = "grant", "Grant"
        COST_CENTER = "cost_center", "Cost Center"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=120)
    transaction_type = models.CharField(
        max_length=40,
        choices=TransactionType.choices,
        default=TransactionType.RECEIPT,
    )
    priority = models.PositiveSmallIntegerField(
        default=100,
        help_text="Lower numbers are evaluated first (higher precedence).",
    )
    debit_account = models.ForeignKey(
        ChartAccount, on_delete=models.PROTECT, related_name="+"
    )
    credit_account = models.ForeignKey(
        ChartAccount, on_delete=models.PROTECT, related_name="+"
    )
    conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional conditions for rule matching (e.g. project_id, grant_id, donor_id, min_amount, max_amount).",
    )
    apply_dimension = models.CharField(
        max_length=40, choices=Dimension.choices, default=Dimension.NONE, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["transaction_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="uniq_postingrule_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_type}: {self.name}"

    def clean(self) -> None:
        errors = {}
        if self.debit_account_id and self.credit_account_id and self.debit_account_id == self.credit_account_id:
            msg = _("Debit and credit accounts cannot be the same.")
            errors["debit_account"] = msg
            errors["credit_account"] = msg
        # Enforce active + posting (leaf) accounts
        if self.debit_account and (not self.debit_account.is_active or not self.debit_account.is_leaf()):
            errors["debit_account"] = _("Debit account must be active and a posting (leaf) account.")
        if self.credit_account and (not self.credit_account.is_active or not self.credit_account.is_leaf()):
            errors["credit_account"] = _("Credit account must be active and a posting (leaf) account.")
        if self.priority < 1 or self.priority > 1000:
            errors["priority"] = _("Priority must be between 1 and 1000.")
        # Validate conditions keys
        allowed_keys = {
            "project_id",
            "grant_id",
            "donor_id",
            "cost_center_id",
            "min_amount",
            "max_amount",
            "payment_method",
            "currency",
        }
        if self.conditions is None:
            self.conditions = {}
        if not isinstance(self.conditions, dict):
            errors["conditions"] = _("Conditions must be a JSON object.")
        else:
            unknown = set(self.conditions.keys()) - allowed_keys
            if unknown:
                errors["conditions"] = _("Unknown condition keys: %(keys)s") % {"keys": ", ".join(sorted(unknown))}
        if errors:
            raise ValidationError(errors)

    def _is_used(self, using: str) -> bool:
        # Used if any generated postings have referenced this rule
        return AuditLog.objects.using(using).filter(
            model_name="posting",
            new_data__rule_id=self.id,
        ).exists()

    def save(self, *args, **kwargs) -> None:
        using = kwargs.get("using") or getattr(self._state, "db", None) or "default"
        if self.pk:
            original = (
                PostingRule.objects.using(using)
                .filter(pk=self.pk)
                .values("transaction_type", "debit_account_id", "credit_account_id", "apply_dimension", "priority", "conditions")
                .first()
            )
            if original and self._is_used(using):
                immutable = ("transaction_type", "debit_account_id", "credit_account_id", "apply_dimension", "priority", "conditions")
                changed = [k for k in immutable if str(original.get(k)) != str(getattr(self, k))]
                if changed:
                    raise ValidationError({"__all__": _("Cannot modify a posting rule once it has been used. Deactivate it and create a new rule.")})
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents: bool = False):
        _using = using or getattr(self._state, "db", None) or "default"
        if self.pk and self._is_used(_using):
            raise ValidationError({"__all__": _("Cannot delete a posting rule once it has been used. Deactivate it instead.")})
        return super().delete(using=using, keep_parents=keep_parents)


class DefaultAccountMapping(models.Model):
    """Default debit/credit accounts by transaction type."""

    class TransactionType(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        PAYMENT = "payment", "Payment"
        JOURNAL = "journal", "Journal"
        TRANSFER = "transfer", "Transfer"

    class Dimension(models.TextChoices):
        NONE = "none", "None"
        PROJECT = "project", "Project"
        GRANT = "grant", "Grant"
        COST_CENTER = "cost_center", "Cost Center"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=120)
    transaction_type = models.CharField(max_length=40, choices=TransactionType.choices)
    default_debit_account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    default_credit_account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    apply_dimension = models.CharField(
        max_length=40, choices=Dimension.choices, default=Dimension.NONE, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    description = models.TextField(blank=True)
    # Legacy field kept for backward compatibility; no longer used for new mappings.
    account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["transaction_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="uniq_defaultaccountmapping_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_type}: {self.name}"

    def clean(self) -> None:
        errors = {}
        if not self.transaction_type:
            errors["transaction_type"] = _("Transaction type is required.")

        if self.default_debit_account_id and self.default_credit_account_id:
            if self.default_debit_account_id == self.default_credit_account_id:
                msg = _("Default debit and credit accounts cannot be the same.")
                errors["default_debit_account"] = msg
                errors["default_credit_account"] = msg

        if errors:
            raise ValidationError(errors)


class ApprovalWorkflow(models.Model):
    """Approval workflow configuration (e.g. Finance Officer -> Manager -> ED)."""

    class TransactionType(models.TextChoices):
        PAYMENT_VOUCHER = "payment_voucher", "Payment Voucher"
        RECEIPT_VOUCHER = "receipt_voucher", "Receipt Voucher"
        STAFF_ADVANCE = "staff_advance", "Staff Advance"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        JOURNAL_ENTRY = "journal_entry", "Journal Entry"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=120)
    document_type = models.CharField(
        max_length=60,
        choices=TransactionType.choices,
        help_text="Transaction type this workflow applies to.",
    )
    steps = models.JSONField(default=list)  # [{"role": "Finance Officer", "order": 1}, ...]
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type", "name"]

    def __str__(self) -> str:
        return f"{self.document_type}: {self.name}"

    def clean(self) -> None:
        errors = {}
        if not isinstance(self.steps, list):
            errors["steps"] = _("Steps must be a list of approval steps.")
        else:
            if not self.steps:
                errors["steps"] = _("At least one approval level is required.")
            orders = set()
            for step in self.steps:
                role = (step.get("role") or "").strip()
                order = step.get("order")
                if not role:
                    errors.setdefault("steps", []).append(_("Each step must specify an approver role."))
                if order is None:
                    errors.setdefault("steps", []).append(_("Each step must specify an approval level."))
                elif order in orders:
                    errors.setdefault("steps", []).append(
                        _("Each approval level must be unique within the workflow.")
                    )
                else:
                    orders.add(order)
        if errors:
            raise ValidationError(errors)


class BudgetControlRule(models.Model):
    """Budget control configuration for grants/projects (per tenant DB)."""

    name = models.CharField(max_length=120)
    rule_type = models.CharField(max_length=40, default="project_budget")
    warn_at_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=80, help_text="Warning threshold in percent (e.g. 80)."
    )
    critical_at_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=90, help_text="Critical threshold in percent (e.g. 90)."
    )
    block_at_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=100, help_text="Block threshold in percent (e.g. 100)."
    )
    allow_override = models.BooleanField(
        default=False,
        help_text="Allow authorized roles to override block at threshold.",
    )
    override_roles = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated role or permission codes allowed to override budget blocks (e.g. finance_manager, finance_director).",
    )
    check_before_posting = models.BooleanField(
        default=True,
        help_text="If enabled, budget checks run automatically before posting transactions.",
    )
    include_commitments = models.BooleanField(
        default=True,
        help_text="If enabled, commitments (e.g. POs/PRs) are included when computing available budget.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} (warn {self.warn_at_percent}%, critical {self.critical_at_percent}%, block {self.block_at_percent}%)"

    def clean(self) -> None:
        errors = {}
        if self.warn_at_percent < 0 or self.block_at_percent < 0 or self.critical_at_percent < 0:
            errors["warn_at_percent"] = _("Percent values cannot be negative.")
        # Strict ordering: warning < critical < block
        if not (self.warn_at_percent < self.critical_at_percent < self.block_at_percent):
            errors["block_at_percent"] = _(
                "Percent thresholds must satisfy: warning < critical < block."
            )
        # Block cannot exceed 100%
        if self.block_at_percent > 100:
            errors["block_at_percent"] = _("Block threshold cannot exceed 100%.")
        # If override is allowed, role must be provided
        if self.allow_override and not (self.override_roles or "").strip():
            errors["override_roles"] = _("Override approval role is required when overrides are allowed.")
        if errors:
            raise ValidationError(errors)


class BudgetEvent(models.Model):
    """Audit log for budget control warnings, blocks, and overrides."""

    class EventType(models.TextChoices):
        WARN = "warn", "Warning"
        BLOCK = "block", "Blocked"
        OVERRIDE = "override", "Override"

    event_type = models.CharField(max_length=20, choices=EventType.choices)
    entry = models.ForeignKey(
        "JournalEntry", on_delete=models.CASCADE, related_name="budget_events"
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    project = models.ForeignKey(
        "tenant_grants.Project", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    budget_line_code = models.CharField(max_length=60, blank=True)
    account_code = models.CharField(max_length=50, blank=True)
    utilization_percent = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    over_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    message = models.TextField(blank=True)
    override_reason = models.TextField(blank=True)
    user = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} for JE#{self.entry_id} @ {self.created_at}"


class BudgetOverrideRequest(models.Model):
    """Approval workflow for budget control overrides (per tenant DB)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    entry = models.ForeignKey(
        "JournalEntry",
        on_delete=models.CASCADE,
        related_name="budget_override_requests",
    )
    rule = models.ForeignKey(
        BudgetControlRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    # Snapshot of the failing budget check for auditability
    check_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["entry", "status"]),
        ]

    def __str__(self) -> str:
        return f"Budget override {self.status} for JE#{self.entry_id}"


class PostingPermission(models.Model):
    """Per-role posting permissions and limits."""

    role_name = models.CharField(max_length=120, unique=True)
    can_create_voucher = models.BooleanField(default=True)
    can_approve_voucher = models.BooleanField(default=False)
    can_post_to_ledger = models.BooleanField(default=False)
    max_posting_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0
    )
    require_second_approval_above_amount = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role_name"]
        verbose_name = "Posting permission"
        verbose_name_plural = "Posting permissions"

    def __str__(self) -> str:
        return self.role_name


class TransactionReversalRule(models.Model):
    """Rules for how reversals and corrections are handled."""

    allow_reversal = models.BooleanField(default=True)
    allow_edit_before_posting = models.BooleanField(default=True)
    allow_delete_before_approval = models.BooleanField(default=True)
    require_reason_for_reversal = models.BooleanField(default=True)
    # Editing & deletion controls
    prevent_edit_after_posting = models.BooleanField(
        default=True,
        help_text="If enabled, posted vouchers cannot be edited; they must be corrected via reversal entries.",
    )
    prevent_delete_after_approval = models.BooleanField(
        default=True,
        help_text="If enabled, approved or posted vouchers cannot be deleted.",
    )
    # Reversal authorization & workflow
    require_reversal_approval = models.BooleanField(
        default=True,
        help_text="If enabled, reversal journals must be approved before posting.",
    )
    authorized_roles_for_reversal = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Comma-separated role or permission codes allowed to perform reversals "
            "(e.g. finance_manager,system_admin)."
        ),
    )
    # Period and fiscal-year controls
    prevent_reversal_if_period_closed = models.BooleanField(
        default=True,
        help_text="If enabled, reversals are blocked when the accounting period is closed.",
    )
    prevent_cross_period_reversal = models.BooleanField(
        default=True,
        help_text="If enabled, reversals cannot move amounts across fiscal years unless explicitly authorized.",
    )
    authorized_roles_for_cross_period_reversal = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Comma-separated role or permission codes allowed to perform cross-fiscal-year reversals."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transaction reversal & correction rule"
        verbose_name_plural = "Transaction reversal & correction rules"

    def __str__(self) -> str:
        return "Reversal & correction rules"


class AuditTrailSetting(models.Model):
    """Audit trail logging configuration for financial actions."""

    class RetentionPolicy(models.TextChoices):
        DAYS_30 = "30", "30 days"
        DAYS_90 = "90", "90 days"
        DAYS_180 = "180", "180 days"
        DAYS_365 = "365", "1 year"
        DAYS_730 = "730", "2 years"
        CUSTOM = "custom", "Custom"

    class RiskClassification(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    enable_audit_logging = models.BooleanField(default=True)
    track_voucher_edits = models.BooleanField(default=True)
    track_approvals = models.BooleanField(default=True)
    track_posting_actions = models.BooleanField(default=True)
    retention_days = models.PositiveIntegerField(default=365)
    retention_policy = models.CharField(
        max_length=20,
        choices=RetentionPolicy.choices,
        default=RetentionPolicy.DAYS_365,
        help_text="High-level retention policy; Custom uses the Retention days value.",
    )
    auto_archive = models.BooleanField(
        default=True,
        help_text="If enabled, older audit logs are auto-archived according to the retention policy.",
    )

    # ---- User activity tracking ----
    track_logins = models.BooleanField(
        default=False,
        help_text="Track user logins and logouts.",
    )
    track_failed_logins = models.BooleanField(
        default=False,
        help_text="Track failed login attempts.",
    )
    track_user_changes = models.BooleanField(
        default=False,
        help_text="Track user creation, deactivation and role/permission changes.",
    )

    # ---- Field-level tracking ----
    track_field_level_changes = models.BooleanField(
        default=True,
        help_text="Track field-level before/after changes for key financial and user records.",
    )

    # ---- Transaction protection ----
    prevent_hard_delete_transactions = models.BooleanField(
        default=True,
        help_text="If enabled, posted transactions cannot be hard-deleted; only reversed or voided.",
    )
    strict_posting_protection = models.BooleanField(
        default=True,
        help_text="If enabled, posted journals are locked (no edit/delete) and must be corrected via reversals.",
    )
    require_reason_for_reversal = models.BooleanField(
        default=True,
        help_text="If enabled, a reason is required when reversing or voiding a transaction.",
    )

    # ---- Fraud / high-risk events ----
    track_high_risk_events = models.BooleanField(
        default=False,
        help_text="Track high-risk events such as backdated postings, overrides and unusual patterns.",
    )
    risk_classification = models.CharField(
        max_length=20,
        choices=RiskClassification.choices,
        default=RiskClassification.MEDIUM,
        help_text="Default classification applied to flagged audit events for reporting and escalation.",
    )
    escalate_to_audit_risk = models.BooleanField(
        default=False,
        help_text="Create alerts in the Audit & Risk module when high-risk events are detected.",
    )

    # ---- Access control for audit logs ----
    authorized_roles_for_audit_logs = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Comma-separated role codes allowed to view full audit logs "
            "(e.g. system_admin,finance_director,internal_auditor)."
        ),
    )
    allow_users_see_own_activity = models.BooleanField(
        default=False,
        help_text="If enabled, non-audit users can see only their own activity log entries.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Audit trail setting"
        verbose_name_plural = "Audit trail settings"

    def __str__(self) -> str:
        return "Audit trail settings"


class GrantComplianceRule(models.Model):
    """Grant and donor-specific compliance rules applied before approval/posting."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class Mode(models.TextChoices):
        WARN = "warn", "Warning only"
        BLOCK = "block", "Block on violation"

    name = models.CharField(max_length=160, help_text="Short name for this compliance rule.")
    donor = models.ForeignKey(
        "tenant_grants.Donor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compliance_rules",
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compliance_rules",
    )
    project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compliance_rules",
    )
    effective_from = models.DateField()
    effective_to = models.DateField()
    reporting_period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start date of the donor reporting period for this rule.",
    )
    reporting_period_end = models.DateField(
        null=True,
        blank=True,
        help_text="End date of the donor reporting period for this rule.",
    )
    reminder_days_before_deadline = models.PositiveIntegerField(
        default=5,
        help_text="Days before reporting period end when reminders should be sent.",
    )
    maximum_admin_cost_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional admin cost ceiling as % of total grant.",
    )
    allowed_account_categories = models.ManyToManyField(
        AccountCategory,
        blank=True,
        related_name="grant_compliance_allowed_rules",
    )
    disallowed_account_categories = models.ManyToManyField(
        AccountCategory,
        blank=True,
        related_name="grant_compliance_disallowed_rules",
    )
    require_attachments = models.BooleanField(default=False)
    require_procurement_compliance = models.BooleanField(default=False)
    require_budget_check = models.BooleanField(default=True)
    allow_posting_outside_grant_period = models.BooleanField(default=False)
    require_additional_approval = models.BooleanField(default=False)
    additional_approval_role = models.CharField(max_length=120, blank=True)
    mode = models.CharField(
        max_length=10,
        choices=Mode.choices,
        default=Mode.BLOCK,
        help_text="Warning mode allows posting with warning; Block mode prevents posting.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from", "name"]
        verbose_name = "Grant compliance rule"
        verbose_name_plural = "Grant compliance rules"
        constraints = [
            models.UniqueConstraint(
                fields=["grant", "name"],
                name="uniq_grantcompliancerule_grant_name",
            ),
        ]

    def __str__(self) -> str:
        scope = self.grant.code if self.grant_id else (self.donor.name if self.donor_id else "Global")
        return f"{self.name} ({scope})"

    def clean(self) -> None:
        errors: dict[str, list[str] | str] = {}

        # Scope validation
        if not (self.donor_id or self.grant_id):
            errors["donor"] = _(
                "At least a donor or a specific grant must be selected for a compliance rule."
            )

        # If both donor and grant are provided, they must be consistent
        if self.donor_id and self.grant_id:
            if getattr(self.grant, "donor_id", None) and self.grant.donor_id != self.donor_id:
                errors["grant"] = _(
                    "Selected grant does not belong to the chosen donor."
                )

        # Effective date ordering
        if self.effective_from and self.effective_to:
            if self.effective_from > self.effective_to:
                errors["effective_to"] = _("Effective to date must be on or after effective from date.")

            # If a grant is selected, ensure rule window is inside grant period
            if self.grant_id and getattr(self.grant, "start_date", None) and getattr(
                self.grant, "end_date", None
            ):
                if self.effective_from < self.grant.start_date or self.effective_to > self.grant.end_date:
                    errors["effective_to"] = _(
                        "Effective dates must fall within the grant period %(start)s to %(end)s."
                    ) % {
                        "start": self.grant.start_date,
                        "end": self.grant.end_date,
                    }

        # Admin cost bounds
        if self.maximum_admin_cost_percent is not None:
            if self.maximum_admin_cost_percent < 0 or self.maximum_admin_cost_percent > 100:
                errors["maximum_admin_cost_percent"] = _(
                    "Maximum admin cost percentage must be between 0 and 100."
                )

        # Reporting period validation
        if self.reporting_period_start and self.reporting_period_end:
            if self.reporting_period_start > self.reporting_period_end:
                errors["reporting_period_end"] = _(
                    "Reporting period end must be on or after reporting period start."
                )
            # Reporting window must fall within grant period when grant is set
            if self.grant_id and getattr(self.grant, "start_date", None) and getattr(
                self.grant, "end_date", None
            ):
                if (
                    self.reporting_period_start < self.grant.start_date
                    or self.reporting_period_end > self.grant.end_date
                ):
                    errors["reporting_period_end"] = _(
                        "Reporting period must fall within the grant duration %(start)s to %(end)s."
                    ) % {
                        "start": self.grant.start_date,
                        "end": self.grant.end_date,
                    }

        # Reminder days positive
        if self.reminder_days_before_deadline is not None:
            if self.reminder_days_before_deadline <= 0:
                errors["reminder_days_before_deadline"] = _(
                    "Reminder days before deadline must be a positive number."
                )

        # Additional approval requires a role
        if self.require_additional_approval and not (self.additional_approval_role or "").strip():
            errors["additional_approval_role"] = _(
                "Additional approval role is required when additional approval is required."
            )

        # Category overlap and at least one allowed category
        allowed_ids = set(
            self.allowed_account_categories.values_list("id", flat=True)
        )
        disallowed_ids = set(
            self.disallowed_account_categories.values_list("id", flat=True)
        )
        if allowed_ids & disallowed_ids:
            errors["allowed_account_categories"] = _(
                "Allowed and disallowed account categories cannot overlap."
            )
        if not allowed_ids:
            errors["allowed_account_categories"] = _(
                "At least one allowed account category must be selected."
            )

        if errors:
            raise ValidationError(errors)


class GrantComplianceEvent(models.Model):
    """Log of grant compliance warnings, blocks, and exceptions."""

    class EventType(models.TextChoices):
        WARN = "warn", "Warning"
        BLOCK = "block", "Blocked"

    event_type = models.CharField(max_length=20, choices=EventType.choices)
    rule = models.ForeignKey(
        GrantComplianceRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    entry = models.ForeignKey(
        "JournalEntry",
        on_delete=models.CASCADE,
        related_name="grant_compliance_events",
    )
    donor = models.ForeignKey(
        "tenant_grants.Donor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    message = models.TextField(blank=True)
    missing_documents = models.BooleanField(default=False)
    admin_ceiling_breach = models.BooleanField(default=False)
    ineligible_category = models.BooleanField(default=False)
    outside_grant_period = models.BooleanField(default=False)
    procurement_issue = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Grant compliance event"
        verbose_name_plural = "Grant compliance events"

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} for JE#{self.entry_id}"


class InterFundTransferRule(models.Model):
    """Configuration for allowed inter-fund transfers and required approvals."""

    class FundType(models.TextChoices):
        GRANT = "grant", "Grant"
        PROJECT = "project", "Project"
        DONOR_FUND = "donor_fund", "Donor Fund"
        UNRESTRICTED = "unrestricted", "Unrestricted Fund"
        CO_FUNDING = "co_funding", "Co-funding"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=160)
    from_fund_type = models.CharField(max_length=40, choices=FundType.choices)
    to_fund_type = models.CharField(max_length=40, choices=FundType.choices)
    specific_from_fund_code = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional fund identifier/code for the source fund.",
    )
    specific_to_fund_code = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional fund identifier/code for the destination fund.",
    )
    allow_transfer = models.BooleanField(default=True)
    require_approval = models.BooleanField(default=True)
    approval_role = models.CharField(
        max_length=120,
        blank=True,
        help_text="Role/title required to approve this transfer (e.g. Finance Manager).",
    )
    require_reason = models.BooleanField(default=True)
    maximum_transfer_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional cap per transfer; leave blank for no explicit limit.",
    )
    transfer_account = models.ForeignKey(
        ChartAccount,
        on_delete=models.PROTECT,
        related_name="interfund_rules",
        help_text="Clearing/transfer account to use for inter-fund postings.",
    )
    effective_from = models.DateField()
    effective_to = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from", "name"]
        verbose_name = "Inter-fund transfer rule"
        verbose_name_plural = "Inter-fund transfer rules"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        errors = {}
        if self.from_fund_type == self.to_fund_type and (
            self.specific_from_fund_code
            and self.specific_to_fund_code
            and self.specific_from_fund_code == self.specific_to_fund_code
        ):
            errors["specific_to_fund_code"] = _(
                "From fund and To fund cannot be the same for an inter-fund rule."
            )
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            errors["effective_to"] = _("Effective to date must be on or after effective from date.")
        if self.require_approval and not (self.approval_role or "").strip():
            errors["approval_role"] = _(
                "Approval role is required when transfers under this rule require approval."
            )
        if errors:
            raise ValidationError(errors)


class InterFundTransfer(models.Model):
    """
    Inter-fund transfer header (Dynamics-style workflow: draft → submitted → approved → posted).
    GL posting: debit destination fund account, credit source fund account (fund codes map to chart accounts).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        POSTED = "posted", "Posted"
        REJECTED = "rejected", "Rejected"
        REVERSED = "reversed", "Reversed"

    transfer_no = models.CharField(
        max_length=40,
        unique=True,
        blank=True,
        db_index=True,
        help_text=_("Auto-assigned transfer number (e.g. IFT-2025-000042)."),
    )
    rule = models.ForeignKey(
        InterFundTransferRule,
        on_delete=models.PROTECT,
        related_name="transfers",
    )
    transfer_date = models.DateField()
    posting_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("GL posting date (set when posted)."),
    )
    from_fund_type = models.CharField(max_length=40, choices=InterFundTransferRule.FundType.choices)
    to_fund_type = models.CharField(max_length=40, choices=InterFundTransferRule.FundType.choices)
    from_fund_code = models.CharField(max_length=80)
    to_fund_code = models.CharField(max_length=80)
    from_grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_out",
        help_text=_("Optional: source fund as grant/project (enforces active/closed rules)."),
    )
    to_grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_in",
        help_text=_("Optional: destination fund as grant/project."),
    )
    from_project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_from",
        help_text=_("Source project when using project/bank workflow."),
    )
    to_project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_to",
        help_text=_("Destination project when using project/bank workflow."),
    )
    from_bank_account = models.ForeignKey(
        "BankAccount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_out",
        help_text=_("Source bank; GL account is bank's linked chart account."),
    )
    to_bank_account = models.ForeignKey(
        "BankAccount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_in",
        help_text=_("Destination bank; GL account is bank's linked chart account."),
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers",
    )
    description = models.TextField(blank=True, help_text=_("Business description / memo for the transfer."))
    reason = models.TextField(blank=True, help_text=_("Legacy / extended notes (kept for compatibility)."))
    reference_no = models.CharField(
        max_length=120,
        blank=True,
        help_text=_("External reference (PO, bank ref, etc.)."),
    )
    donor = models.ForeignKey(
        "tenant_grants.Donor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers",
    )
    attachment = models.FileField(
        upload_to="finance/interfund_attachments/%Y/%m/",
        blank=True,
        null=True,
        max_length=255,
    )
    planned_posting_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("Intended GL posting date (validated when posting to the ledger)."),
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="interfund_transfers_created",
    )
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="interfund_transfers_approved",
        null=True,
        blank=True,
    )
    posted_journal = models.ForeignKey(
        "JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interfund_transfers",
    )
    reversal_journal = models.ForeignKey(
        "JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interfund_transfer_reversals",
        help_text=_("Reversal journal when a posted transfer was reversed."),
    )
    reversed_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interfund_transfers_reversed",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-transfer_date", "-id"]
        verbose_name = "Inter-fund transfer"
        verbose_name_plural = "Inter-fund transfers"

    def __str__(self) -> str:
        ref = (self.transfer_no or "").strip() or f"#{self.pk or 'new'}"
        return f"{ref} {self.transfer_date} {self.from_fund_code} → {self.to_fund_code} {self.amount}"

    @property
    def is_locked(self) -> bool:
        """Posted or reversed transfers cannot be edited."""
        return self.status in (self.Status.POSTED, self.Status.REVERSED)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not (self.transfer_no or "").strip():
            no = f"IFT-{self.transfer_date.year}-{self.id:06d}"
            InterFundTransfer.objects.filter(pk=self.pk).update(transfer_no=no)
            self.transfer_no = no

    def display_description(self) -> str:
        return (self.description or self.reason or "").strip()

class OrganizationSettings(models.Model):
    """
    Singleton per tenant: organization info, branding, fiscal and document defaults.
    Only System Admin (tenant admin) can edit. Used by Organization Settings under Account.
    """

    # Organization Information
    organization_name = models.CharField(max_length=255, blank=True)
    organization_logo = models.ImageField(
        upload_to="org_settings/%Y/%m/", null=True, blank=True, max_length=255
    )
    registration_number = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Branding
    primary_color = models.CharField(max_length=20, blank=True, help_text="Hex, e.g. #0078d4")
    secondary_color = models.CharField(max_length=20, blank=True, help_text="Hex, e.g. #106ebe")
    system_logo = models.ImageField(
        upload_to="org_settings/%Y/%m/", null=True, blank=True, max_length=255
    )
    report_logo = models.ImageField(
        upload_to="org_settings/%Y/%m/", null=True, blank=True, max_length=255
    )

    # Fiscal Settings
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=1, help_text="1-12, e.g. 7 for July"
    )
    fiscal_year_end_month = models.PositiveSmallIntegerField(
        default=12, help_text="1-12, e.g. 6 for June (year end)"
    )
    default_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    currency_format = models.CharField(max_length=40, blank=True, default="#,##0.00")
    time_zone = models.CharField(max_length=50, blank=True, default="UTC")

    # Document prefixes (e.g. INV-, PV-, RV-, JV-)
    invoice_prefix = models.CharField(max_length=20, blank=True, default="INV-")
    payment_voucher_prefix = models.CharField(max_length=20, blank=True, default="PV-")
    receipt_voucher_prefix = models.CharField(max_length=20, blank=True, default="RV-")
    journal_prefix = models.CharField(max_length=20, blank=True, default="JV-")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Organization settings"

    def __str__(self) -> str:
        return self.organization_name or "Organization settings"
