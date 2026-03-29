from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from tenant_finance.models import (
    BudgetControlRule,
    BudgetEvent,
    BudgetOverrideRequest,
    ChartAccount,
    JournalEntry,
    JournalLine,
    get_grant_posted_expense_total,
)
from tenant_grants.models import BudgetLine, Grant


@dataclass
class BudgetCheckResult:
    status: str  # "ok", "warn", "critical", "block", "no_budget"
    message: str = ""
    utilization_percent: Optional[Decimal] = None
    over_amount: Optional[Decimal] = None
    details: dict | None = None


class BudgetControlEngine:
    """
    Central place for grant/project budget validation.

    Budget validation engine:
    - Budget line level enforcement using BudgetLine.account (preferred)
    - Available budget = budget - actuals - optionally commitments
    - Threshold bands: warn / critical / block
    - Override requests with approval & audit logging
    """

    def __init__(self, tenant_db: str):
        self.tenant_db = tenant_db

    # ---- Rules -------------------------------------------------------------

    def _get_rules(self) -> BudgetControlRule:
        rule = (
            BudgetControlRule.objects.using(self.tenant_db)
            .filter(is_active=True)
            .order_by("id")
            .first()
        )
        if not rule:
            rule = BudgetControlRule(
                name="Default budget control",
                warn_at_percent=Decimal("80"),
                critical_at_percent=Decimal("90"),
                block_at_percent=Decimal("100"),
            )
        return rule

    def _override_role_set(self, rule: BudgetControlRule) -> set[str]:
        raw = (rule.override_roles or "").strip()
        if not raw:
            return set()
        return {r.strip().lower() for r in raw.split(",") if r.strip()}

    def _user_has_override_role(self, user, rule: BudgetControlRule) -> bool:
        if not user or not rule.allow_override:
            return False
        # Best-effort: match by tenant role name (if present) or user's role_name field if exists.
        role_name = (getattr(user, "role_name", "") or "").strip().lower()
        if role_name and role_name in self._override_role_set(rule):
            return True
        # Some deployments expose a list of roles on tenant_user
        roles = getattr(user, "roles", None)
        if roles:
            try:
                for r in roles:
                    nm = (getattr(r, "name", "") or str(r) or "").strip().lower()
                    if nm and nm in self._override_role_set(rule):
                        return True
            except Exception:
                pass
        return False

    def _get_commitments_by_budget_line(self, grant: Grant) -> dict[str, Decimal]:
        """
        Commitments are sourced from PRs (Purchase Requisitions) not in terminal states.
        They are grouped by PR line 'budget_line' text (should match BudgetLine.budget_code).
        """
        from tenant_grants.models import PurchaseRequisition

        qs = PurchaseRequisition.objects.using(self.tenant_db).filter(grant=grant).exclude(
            status__in=[
                PurchaseRequisition.Status.REJECTED,
                PurchaseRequisition.Status.CANCELLED,
                PurchaseRequisition.Status.FULFILLED,
            ]
        )

        totals: dict[str, Decimal] = {}
        for pr in qs.prefetch_related("lines"):
            # Prefer lines (multi-line PR); else fallback to header budget_line
            if pr.lines.exists():
                for line in pr.lines.all():
                    key = (line.budget_line or "").strip()
                    if not key:
                        continue
                    totals[key] = totals.get(key, Decimal("0")) + (line.estimated_total_cost or Decimal("0"))
            else:
                key = (pr.budget_line or "").strip()
                if not key:
                    continue
                totals[key] = totals.get(key, Decimal("0")) + (pr.effective_total() or Decimal("0"))
        return totals

    def _budget_lines_for_grant(self, grant: Grant) -> list[BudgetLine]:
        return list(
            BudgetLine.objects.using(self.tenant_db)
            .select_related("account")
            .filter(grant=grant)
            .order_by("id")
        )

    def _actuals_by_account_for_grant(self, grant: Grant) -> dict[int, Decimal]:
        rows = (
            JournalLine.objects.using(self.tenant_db)
            .filter(
                entry__grant_id=grant.id,
                entry__status=JournalEntry.Status.POSTED,
                account__type=ChartAccount.Type.EXPENSE,
            )
            .values("account_id")
            .annotate(total=Sum("debit") - Sum("credit"))
        )
        return {r["account_id"]: (r["total"] or Decimal("0")) for r in rows}

    def _entry_expense_by_account(self, entry: JournalEntry) -> dict[int, Decimal]:
        rows = (
            JournalLine.objects.using(self.tenant_db)
            .filter(entry=entry, account__type=ChartAccount.Type.EXPENSE)
            .values("account_id")
            .annotate(total=Sum("debit") - Sum("credit"))
        )
        return {r["account_id"]: (r["total"] or Decimal("0")) for r in rows}

    def _entry_expense_by_account_for_grant(self, entry: JournalEntry, grant_id: int) -> dict[int, Decimal]:
        rows = (
            JournalLine.objects.using(self.tenant_db)
            .filter(
                entry=entry,
                account__type=ChartAccount.Type.EXPENSE,
                grant_id=grant_id,
            )
            .values("account_id")
            .annotate(total=Sum("debit") - Sum("credit"))
        )
        return {r["account_id"]: (r["total"] or Decimal("0")) for r in rows}

    def _grants_to_check_for_entry(self, entry: JournalEntry) -> list[Grant]:
        """Grants whose budget lines must be checked (header grant and/or expense line grants)."""
        gids = list(
            JournalLine.objects.using(self.tenant_db)
            .filter(
                entry=entry,
                account__type=ChartAccount.Type.EXPENSE,
                debit__gt=0,
            )
            .exclude(grant_id__isnull=True)
            .values_list("grant_id", flat=True)
            .distinct()
        )
        if entry.grant_id and entry.grant_id not in gids:
            gids.append(entry.grant_id)
        if not gids:
            if entry.grant_id:
                g = getattr(entry, "grant", None)
                return [g] if g else []
            return []
        return list(Grant.objects.using(self.tenant_db).filter(pk__in=gids).select_related("project"))

    # ---- Core check --------------------------------------------------------

    def check_entry(self, entry: JournalEntry) -> BudgetCheckResult:
        """
        Validate a journal entry against grant budget lines.
        Supports multiple grants (e.g. co-funded payment voucher lines with different grants).
        """
        grants = self._grants_to_check_for_entry(entry)
        if not grants:
            return BudgetCheckResult(status="ok")

        rules = self._get_rules()
        worst = BudgetCheckResult(status="ok", details={})
        worst_rank = {"ok": 0, "warn": 1, "no_budget": 2, "critical": 3, "block": 4}

        merged_details: dict = {
            "include_commitments": bool(rules.include_commitments),
            "lines": [],
            "grants_checked": [],
        }

        for grant in grants:
            budget_lines = self._budget_lines_for_grant(grant)
            if not budget_lines:
                merged_details["grants_checked"].append(grant.code)
                no_budget = BudgetCheckResult(
                    status="no_budget",
                    message=f"No approved budget defined for grant {grant.code}.",
                    details={"lines": [], "grant": grant.code},
                )
                if worst_rank["no_budget"] > worst_rank.get(worst.status, 0):
                    worst = no_budget
                continue

            merged_details["grants_checked"].append(grant.code)

            actuals_by_account = self._actuals_by_account_for_grant(grant)
            entry_by_account = self._entry_expense_by_account_for_grant(entry, grant.id)
            commitments_by_category = (
                self._get_commitments_by_budget_line(grant) if rules.include_commitments else {}
            )

            grant_details = {
                "grant": grant.code,
                "include_commitments": bool(rules.include_commitments),
                "lines": [],
            }

            for bl in budget_lines:
                budget_amt = bl.amount or Decimal("0")
                acct_id = bl.account_id
                line_code = (getattr(bl, "budget_code", "") or "").strip()
                line_name = (bl.category or "").strip()
                if not acct_id:
                    grant_details["lines"].append(
                        {
                            "grant_code": grant.code,
                            "budget_line_id": bl.id,
                            "budget_code": line_code,
                            "category": bl.category,
                            "budget": str(budget_amt),
                            "note": "No account mapped on budget line; skipped.",
                        }
                    )
                    continue

                actual = actuals_by_account.get(acct_id, Decimal("0"))
                new = entry_by_account.get(acct_id, Decimal("0"))
                commit = commitments_by_category.get(line_code, Decimal("0"))
                projected = actual + new + (commit if rules.include_commitments else Decimal("0"))

                util = (projected / budget_amt * Decimal("100")) if budget_amt > 0 else None
                over = projected - budget_amt if budget_amt > 0 and projected > budget_amt else Decimal("0")

                line_status = "ok"
                if budget_amt <= 0 and new > 0:
                    line_status = "block"
                    msg = f"Budget control: no budget amount for line '{line_code or line_name}' but entry posts {new}."
                elif util is not None:
                    if util >= rules.block_at_percent:
                        line_status = "block"
                        msg = (
                            f"Budget line '{line_code or line_name}' will exceed budget {budget_amt} "
                            f"(projected {projected}, utilization {util:.2f}%)."
                        )
                    elif util >= rules.critical_at_percent:
                        line_status = "critical"
                        msg = (
                            f"Budget line '{line_code or line_name}' will reach critical utilization {util:.2f}% "
                            f"of budget {budget_amt} (projected {projected})."
                        )
                    elif util >= rules.warn_at_percent:
                        line_status = "warn"
                        msg = (
                            f"Budget line '{line_code or line_name}' will reach warning utilization {util:.2f}% "
                            f"of budget {budget_amt} (projected {projected})."
                        )
                    else:
                        msg = ""
                else:
                    msg = ""

                grant_details["lines"].append(
                    {
                        "grant_code": grant.code,
                        "budget_line_id": bl.id,
                        "budget_code": line_code,
                        "category": bl.category,
                        "account_id": acct_id,
                        "budget": str(budget_amt),
                        "actual": str(actual),
                        "commitments": str(commit),
                        "new": str(new),
                        "projected": str(projected),
                        "utilization_percent": str(util) if util is not None else None,
                        "status": line_status,
                        "over_amount": str(over),
                    }
                )

                if worst_rank[line_status] > worst_rank[worst.status]:
                    worst = BudgetCheckResult(
                        status=line_status,
                        message=msg,
                        utilization_percent=util if util is not None else None,
                        over_amount=over if over else None,
                        details=merged_details,
                    )

            merged_details["lines"].extend(grant_details["lines"])

        worst.details = merged_details
        return worst

    def budget_comparison_rows_from_check_result(self, result: BudgetCheckResult) -> list[dict]:
        """Build approval table rows from a BudgetCheckResult produced by check_entry."""
        details = (result.details or {}).get("lines") or []
        rows: list[dict] = []
        for raw in details:
            if "projected" not in raw:
                continue
            budget_amt = Decimal(str(raw.get("budget") or "0"))
            used = Decimal(str(raw.get("actual") or "0"))
            this_v = Decimal(str(raw.get("new") or "0"))
            total_after = Decimal(str(raw.get("projected") or "0"))
            variance = total_after - budget_amt
            remaining = budget_amt - total_after
            code = (raw.get("budget_code") or "").strip()
            bl_id = raw.get("budget_line_id")
            line_label = (raw.get("category") or "").strip()
            if bl_id:
                bl = (
                    BudgetLine.objects.using(self.tenant_db)
                    .filter(pk=bl_id)
                    .only("description", "category", "budget_code")
                    .first()
                )
                if bl:
                    line_label = (bl.description or "").strip() or (bl.category or "").strip() or line_label
                    if not code:
                        code = (bl.budget_code or "").strip()
            code_display = code or "—"
            name_display = line_label or "—"
            rows.append(
                {
                    "budget_code": code_display,
                    "line_name": name_display,
                    "approved_budget": budget_amt,
                    "used_before": used,
                    "this_voucher": this_v,
                    "total_after_posting": total_after,
                    "remaining_balance": remaining,
                    "variance": variance,
                    "over_budget": variance > 0,
                }
            )
        return rows

    def budget_comparison_rows_for_entry(self, entry: JournalEntry) -> tuple[BudgetCheckResult, list[dict]]:
        """Single check_entry call; returns (result, rows) for PV approval screen."""
        result = self.check_entry(entry)
        return result, self.budget_comparison_rows_from_check_result(result)

    def check_budget_line_new_expense(
        self,
        grant: Grant,
        budget_line: BudgetLine,
        new_amount: Decimal,
    ) -> BudgetCheckResult:
        """
        Validate one budget line before creating a payment voucher (no journal entry yet).
        Mirrors per-line logic in check_entry for projected utilization vs budget line amount.
        """
        rules = self._get_rules()
        budget_amt = budget_line.amount or Decimal("0")
        acct_id = budget_line.account_id
        line_code = (getattr(budget_line, "budget_code", "") or "").strip()
        line_name = (budget_line.category or "").strip()

        if not acct_id:
            return BudgetCheckResult(
                status="block",
                message="Budget line has no expense account mapped; cannot validate availability.",
            )

        actuals_by_account = self._actuals_by_account_for_grant(grant)
        commitments_by_category = (
            self._get_commitments_by_budget_line(grant) if rules.include_commitments else {}
        )
        actual = actuals_by_account.get(acct_id, Decimal("0"))
        commit = commitments_by_category.get(line_code, Decimal("0"))
        projected = actual + new_amount + (commit if rules.include_commitments else Decimal("0"))

        util = (projected / budget_amt * Decimal("100")) if budget_amt > 0 else None
        over = projected - budget_amt if budget_amt > 0 and projected > budget_amt else Decimal("0")

        if budget_amt <= 0 and new_amount > 0:
            return BudgetCheckResult(
                status="block",
                message=(
                    f"Budget control: no budget amount for line '{line_code or line_name}' "
                    f"but payment posts {new_amount}."
                ),
                over_amount=over,
            )

        if util is None:
            return BudgetCheckResult(status="ok", message="")

        if util >= rules.block_at_percent:
            return BudgetCheckResult(
                status="block",
                message=(
                    f"Budget line '{line_code or line_name}' would exceed budget {budget_amt} "
                    f"(projected {projected}, utilization {util:.2f}%)."
                ),
                utilization_percent=util,
                over_amount=over if over else None,
            )
        if util >= rules.critical_at_percent:
            return BudgetCheckResult(
                status="critical",
                message=(
                    f"Budget line '{line_code or line_name}' would reach critical utilization "
                    f"{util:.2f}% of budget {budget_amt}."
                ),
                utilization_percent=util,
            )
        if util >= rules.warn_at_percent:
            return BudgetCheckResult(
                status="warn",
                message=(
                    f"Budget line '{line_code or line_name}' would reach warning utilization "
                    f"{util:.2f}% of budget {budget_amt}."
                ),
                utilization_percent=util,
            )
        return BudgetCheckResult(status="ok", message="")

    # ---- Audit logging -----------------------------------------------------

    def log_event(
        self,
        *,
        entry: JournalEntry,
        result: BudgetCheckResult,
        event_type: BudgetEvent.EventType,
        user,
        override_reason: str = "",
    ) -> None:
        BudgetEvent.objects.using(self.tenant_db).create(
            event_type=event_type,
            entry=entry,
            grant=entry.grant,
            project=getattr(entry.grant, "project", None) if entry.grant_id else None,
            budget_line_code="",
            account_code="",
            utilization_percent=result.utilization_percent,
            over_amount=result.over_amount,
            message=result.message,
            override_reason=override_reason,
            user=user,
        )

    # ---- Override workflow -------------------------------------------------

    def get_approved_override_for_entry(self, entry: JournalEntry) -> Optional[BudgetOverrideRequest]:
        return (
            BudgetOverrideRequest.objects.using(self.tenant_db)
            .filter(entry=entry, status=BudgetOverrideRequest.Status.APPROVED)
            .order_by("-requested_at")
            .first()
        )

    def get_pending_override_for_entry(self, entry: JournalEntry) -> Optional[BudgetOverrideRequest]:
        return (
            BudgetOverrideRequest.objects.using(self.tenant_db)
            .filter(entry=entry, status=BudgetOverrideRequest.Status.PENDING)
            .select_related("requested_by")
            .order_by("-requested_at")
            .first()
        )

    def create_pending_budget_override_request(
        self,
        *,
        entry: JournalEntry,
        user,
        reason: str,
        check_result: BudgetCheckResult,
        extra_snapshot: dict | None = None,
    ) -> BudgetOverrideRequest | None:
        """
        Maker submitted a payment voucher that exceeds budget. Creates a pending override for
        Finance Manager approval (does not require allow_override on the rule or special roles on the maker).
        """
        if BudgetOverrideRequest.objects.using(self.tenant_db).filter(
            entry=entry, status=BudgetOverrideRequest.Status.PENDING
        ).exists():
            return None
        rule = self._get_rules()
        snap: dict = dict(check_result.details or {})
        if extra_snapshot:
            snap["maker_context"] = extra_snapshot
        if check_result.message:
            snap["control_message"] = check_result.message
        if check_result.utilization_percent is not None:
            snap["utilization_percent"] = str(check_result.utilization_percent)
        if check_result.over_amount is not None:
            snap["over_amount"] = str(check_result.over_amount)

        return BudgetOverrideRequest.objects.using(self.tenant_db).create(
            entry=entry,
            rule=rule if getattr(rule, "pk", None) else None,
            status=BudgetOverrideRequest.Status.PENDING,
            requested_by=user,
            reason=(reason or "").strip()
            or str(_("Payment exceeds available budget; pending Finance Manager approval.")),
            check_snapshot=snap,
        )

    def approve_pending_override_for_entry(
        self,
        *,
        entry: JournalEntry,
        decided_by,
        decision_note: str = "",
    ) -> Optional[BudgetOverrideRequest]:
        """Mark the pending budget override as approved (call before posting the journal)."""
        req = self.get_pending_override_for_entry(entry)
        if not req:
            return None
        from django.utils import timezone

        req.status = BudgetOverrideRequest.Status.APPROVED
        req.decided_by = decided_by
        req.decided_at = timezone.now()
        req.decision_note = (decision_note or "").strip() or str(_("Approved for posting."))
        req.save(
            using=self.tenant_db,
            update_fields=["status", "decided_by", "decided_at", "decision_note"],
        )
        return req

    def cancel_pending_override_for_entry(
        self,
        *,
        entry: JournalEntry,
        decided_by,
        note: str = "",
    ) -> None:
        """Cancel pending override when voucher is returned/rejected."""
        qs = BudgetOverrideRequest.objects.using(self.tenant_db).filter(
            entry=entry, status=BudgetOverrideRequest.Status.PENDING
        )
        from django.utils import timezone

        now = timezone.now()
        for req in qs:
            req.status = BudgetOverrideRequest.Status.CANCELLED
            req.decided_by = decided_by
            req.decided_at = now
            req.decision_note = (note or "").strip()[:500]
            req.save(
                using=self.tenant_db,
                update_fields=["status", "decided_by", "decided_at", "decision_note"],
            )

    def request_override(
        self,
        *,
        entry: JournalEntry,
        user,
        reason: str,
        check_result: BudgetCheckResult,
    ) -> BudgetOverrideRequest:
        rule = self._get_rules()
        if not rule.allow_override:
            raise ValueError("Budget overrides are not enabled.")
        if not self._user_has_override_role(user, rule):
            raise ValueError("You are not authorized to request a budget override.")
        if not (reason or "").strip():
            raise ValueError("Override reason is required.")
        req = BudgetOverrideRequest.objects.using(self.tenant_db).create(
            entry=entry,
            rule=rule if rule and rule.pk else None,
            status=BudgetOverrideRequest.Status.PENDING,
            requested_by=user,
            reason=reason.strip(),
            check_snapshot=check_result.details or {},
        )
        return req

