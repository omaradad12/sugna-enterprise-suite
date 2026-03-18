from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from tenant_finance.models import InterFundTransfer, InterFundTransferRule


@dataclass
class InterFundCheckResult:
    status: str  # "ok", "block"
    message: str = ""


class InterFundTransferEngine:
    """
    Engine for validating and executing inter-fund transfers.

    This module focuses on rule/date/status checks and defers detailed
    balance validation and posting logic to the surrounding cash/bank modules.
    """

    def __init__(self, tenant_db: str):
        self.tenant_db = tenant_db

    def _select_rule(
        self,
        *,
        from_fund_type: str,
        to_fund_type: str,
        from_fund_code: str,
        to_fund_code: str,
        transfer_date: date,
    ) -> Optional[InterFundTransferRule]:
        qs = (
            InterFundTransferRule.objects.using(self.tenant_db)
            .filter(status=InterFundTransferRule.Status.ACTIVE)
            .filter(effective_from__lte=transfer_date, effective_to__gte=transfer_date)
            .filter(from_fund_type=from_fund_type, to_fund_type=to_fund_type)
        )

        # Prefer specific fund match, then generic rule.
        specific = qs.filter(
            specific_from_fund_code__iexact=from_fund_code,
            specific_to_fund_code__iexact=to_fund_code,
        ).first()
        if specific:
            return specific
        return qs.filter(
            specific_from_fund_code__exact="",
            specific_to_fund_code__exact="",
        ).first()

    def check_transfer(
        self,
        *,
        from_fund_type: str,
        to_fund_type: str,
        from_fund_code: str,
        to_fund_code: str,
        amount: Decimal,
        transfer_date: date,
    ) -> InterFundCheckResult:
        """Validate transfer against configured rules (excluding balances)."""
        if from_fund_type == to_fund_type and from_fund_code == to_fund_code:
            return InterFundCheckResult(
                status="block", message="From fund and To fund cannot be the same."
            )

        rule = self._select_rule(
            from_fund_type=from_fund_type,
            to_fund_type=to_fund_type,
            from_fund_code=from_fund_code,
            to_fund_code=to_fund_code,
            transfer_date=transfer_date,
        )
        if not rule or not rule.allow_transfer:
            return InterFundCheckResult(
                status="block",
                message=(
                    "Inter-fund transfer is not allowed by configuration for this "
                    "combination of funds."
                ),
            )

        if amount <= 0:
            return InterFundCheckResult(
                status="block", message="Transfer amount must be greater than zero."
            )

        if rule.maximum_transfer_amount and amount > rule.maximum_transfer_amount:
            return InterFundCheckResult(
                status="block",
                message=(
                    f"Transfer amount {amount} exceeds maximum allowed "
                    f"{rule.maximum_transfer_amount} for this rule."
                ),
            )

        return InterFundCheckResult(status="ok")

    def create_transfer(
        self,
        *,
        rule: InterFundTransferRule,
        from_fund_type: str,
        to_fund_type: str,
        from_fund_code: str,
        to_fund_code: str,
        amount: Decimal,
        transfer_date: date,
        reason: str,
        user,
    ) -> InterFundTransfer:
        """Create an InterFundTransfer record in draft/pending state."""
        status = (
            InterFundTransfer.Status.PENDING_APPROVAL
            if rule.require_approval
            else InterFundTransfer.Status.DRAFT
        )
        transfer = InterFundTransfer.objects.using(self.tenant_db).create(
            rule=rule,
            transfer_date=transfer_date,
            from_fund_type=from_fund_type,
            to_fund_type=to_fund_type,
            from_fund_code=from_fund_code,
            to_fund_code=to_fund_code,
            amount=amount,
            reason=reason,
            status=status,
            created_by=user,
        )
        return transfer

