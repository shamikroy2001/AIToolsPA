"""Credit lots + immutable ledger. Never change remaining_amount without a transaction row."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import (
    SOURCE_MONTHLY,
    SOURCE_ROLLOVER,
    SOURCE_TOPUP,
    TX_AI_USAGE,
    TX_EXPIRATION,
    TX_MONTHLY_ALLOCATION,
    TX_RELEASE,
    TX_RESERVATION,
    TX_ROLLOVER,
    CreditAccount,
    CreditLot,
    CreditTransaction,
)
from app.models.plan import Plan
from app.models.user import User


class InsufficientCredits(Exception):
    def __init__(self, needed: int, available: int) -> None:
        super().__init__(f"Need {needed} credits; {available} available")
        self.needed = needed
        self.available = available


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def period_key(period_start: datetime, period_end: datetime) -> str:
    return f"{period_start.date().isoformat()}:{period_end.date().isoformat()}"


class CreditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_account(self, user_id: UUID) -> CreditAccount:
        account = await self._session.scalar(
            select(CreditAccount).where(CreditAccount.user_id == user_id)
        )
        if account is None:
            account = CreditAccount(user_id=user_id)
            self._session.add(account)
            await self._session.flush()
        return account

    async def available(self, user_id: UUID, *, now: datetime | None = None) -> int:
        now = now or _utcnow()
        total = await self._session.scalar(
            select(func.coalesce(func.sum(CreditLot.remaining_amount), 0)).where(
                CreditLot.user_id == user_id,
                CreditLot.remaining_amount > 0,
                or_(CreditLot.expires_at.is_(None), CreditLot.expires_at > now),
            )
        )
        return int(total or 0)

    async def rollover_available(self, user_id: UUID, *, now: datetime | None = None) -> int:
        now = now or _utcnow()
        total = await self._session.scalar(
            select(func.coalesce(func.sum(CreditLot.remaining_amount), 0)).where(
                CreditLot.user_id == user_id,
                CreditLot.source == SOURCE_ROLLOVER,
                CreditLot.remaining_amount > 0,
                or_(CreditLot.expires_at.is_(None), CreditLot.expires_at > now),
            )
        )
        return int(total or 0)

    async def used_this_period(self, user_id: UUID, period_start: datetime | None) -> int:
        if period_start is None:
            return 0
        total = await self._session.scalar(
            select(func.coalesce(func.sum(-CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type.in_([TX_AI_USAGE, TX_RESERVATION]),
                CreditTransaction.created_at >= period_start,
                CreditTransaction.amount < 0,
            )
        )
        releases = await self._session.scalar(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == TX_RELEASE,
                CreditTransaction.created_at >= period_start,
                CreditTransaction.amount > 0,
            )
        )
        return max(0, int(total or 0) - int(releases or 0))

    def _spendable_lots_stmt(self, user_id: UUID, now: datetime) -> Select[tuple[CreditLot]]:
        priority = case(
            (CreditLot.source == SOURCE_ROLLOVER, 0),
            (CreditLot.source == SOURCE_MONTHLY, 1),
            (CreditLot.source == SOURCE_TOPUP, 2),
            else_=3,
        )
        return (
            select(CreditLot)
            .where(
                CreditLot.user_id == user_id,
                CreditLot.remaining_amount > 0,
                or_(CreditLot.expires_at.is_(None), CreditLot.expires_at > now),
            )
            .order_by(priority, CreditLot.expires_at.is_(None), CreditLot.expires_at, CreditLot.created_at)
            .with_for_update()
        )

    async def _add_tx(
        self,
        *,
        user_id: UUID,
        lot: CreditLot | None,
        tx_type: str,
        amount: int,
        description: str = "",
        stripe_event_id: str | None = None,
        task_id: UUID | None = None,
    ) -> CreditTransaction:
        row = CreditTransaction(
            user_id=user_id,
            credit_lot_id=None if lot is None else lot.id,
            transaction_type=tx_type,
            amount=amount,
            description=description,
            stripe_event_id=stripe_event_id,
            task_id=task_id,
        )
        self._session.add(row)
        return row

    async def expire_due_lots(self, user_id: UUID | None = None, *, now: datetime | None = None) -> int:
        now = now or _utcnow()
        stmt = select(CreditLot).where(
            CreditLot.remaining_amount > 0,
            CreditLot.expires_at.is_not(None),
            CreditLot.expires_at <= now,
        )
        if user_id is not None:
            stmt = stmt.where(CreditLot.user_id == user_id)
        lots = list((await self._session.scalars(stmt)).all())
        expired = 0
        for lot in lots:
            amount = lot.remaining_amount
            lot.remaining_amount = 0
            await self._add_tx(
                user_id=lot.user_id,
                lot=lot,
                tx_type=TX_EXPIRATION,
                amount=-amount,
                description="Credit lot expired",
            )
            expired += amount
        await self._session.flush()
        return expired

    async def _monthly_allocated(self, user_id: UUID, billing_period: str) -> bool:
        existing = await self._session.scalar(
            select(CreditTransaction.id).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == TX_MONTHLY_ALLOCATION,
                CreditTransaction.description == billing_period,
            )
        )
        return existing is not None

    async def allocate_period(
        self,
        user: User,
        plan: Plan,
        period_start: datetime,
        period_end: datetime,
        *,
        stripe_event_id: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Grant monthly credits and capped rollover. Returns False if already allocated."""
        now = now or _utcnow()
        billing_period = period_key(period_start, period_end)
        if await self._monthly_allocated(user.id, billing_period):
            return False

        await self.expire_due_lots(user.id, now=now)

        monthly_lots = list(
            (
                await self._session.scalars(
                    select(CreditLot).where(
                        CreditLot.user_id == user.id,
                        CreditLot.source == SOURCE_MONTHLY,
                        CreditLot.remaining_amount > 0,
                    )
                )
            ).all()
        )
        unused = sum(lot.remaining_amount for lot in monthly_lots)
        rollover_grant = min(unused, plan.rollover_cap)
        leftover = unused - rollover_grant

        remaining_to_move = rollover_grant
        remaining_to_expire = leftover
        for lot in monthly_lots:
            take_roll = min(lot.remaining_amount, remaining_to_move)
            if take_roll:
                lot.remaining_amount -= take_roll
                remaining_to_move -= take_roll
                await self._add_tx(
                    user_id=user.id,
                    lot=lot,
                    tx_type=TX_ROLLOVER,
                    amount=-take_roll,
                    description="Moved unused monthly credits to rollover",
                    stripe_event_id=stripe_event_id,
                )
            take_exp = min(lot.remaining_amount, remaining_to_expire)
            if take_exp:
                lot.remaining_amount -= take_exp
                remaining_to_expire -= take_exp
                await self._add_tx(
                    user_id=user.id,
                    lot=lot,
                    tx_type=TX_EXPIRATION,
                    amount=-take_exp,
                    description="Unused monthly credits above rollover cap",
                    stripe_event_id=stripe_event_id,
                )

        if rollover_grant:
            rollover_lot = CreditLot(
                user_id=user.id,
                source=SOURCE_ROLLOVER,
                original_amount=rollover_grant,
                remaining_amount=rollover_grant,
                billing_period=billing_period,
                expires_at=now + timedelta(days=plan.rollover_expiry_days),
            )
            self._session.add(rollover_lot)
            await self._session.flush()
            await self._add_tx(
                user_id=user.id,
                lot=rollover_lot,
                tx_type=TX_ROLLOVER,
                amount=rollover_grant,
                description="Rollover grant",
                stripe_event_id=stripe_event_id,
            )

        monthly_lot = CreditLot(
            user_id=user.id,
            source=SOURCE_MONTHLY,
            original_amount=plan.monthly_credits,
            remaining_amount=plan.monthly_credits,
            billing_period=billing_period,
            expires_at=None,
        )
        self._session.add(monthly_lot)
        await self._session.flush()
        await self._add_tx(
            user_id=user.id,
            lot=monthly_lot,
            tx_type=TX_MONTHLY_ALLOCATION,
            amount=plan.monthly_credits,
            description=billing_period,
            stripe_event_id=stripe_event_id,
        )

        account = await self.ensure_account(user.id)
        account.current_period_start = period_start
        account.current_period_end = period_end
        account.monthly_allowance = plan.monthly_credits
        account.rollover_cap = plan.rollover_cap
        user.plan = plan.slug
        await self._session.flush()
        return True

    async def consume(
        self,
        user_id: UUID,
        amount: int,
        *,
        tx_type: str = TX_AI_USAGE,
        description: str = "",
        task_id: UUID | None = None,
        now: datetime | None = None,
    ) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        now = now or _utcnow()
        await self.expire_due_lots(user_id, now=now)
        remaining = amount
        lots = list((await self._session.scalars(self._spendable_lots_stmt(user_id, now))).all())
        available = sum(lot.remaining_amount for lot in lots)
        if available < amount:
            raise InsufficientCredits(amount, available)
        for lot in lots:
            if remaining <= 0:
                break
            take = min(lot.remaining_amount, remaining)
            lot.remaining_amount -= take
            remaining -= take
            await self._add_tx(
                user_id=user_id,
                lot=lot,
                tx_type=tx_type,
                amount=-take,
                description=description,
                task_id=task_id,
            )
        if remaining != 0:
            raise InsufficientCredits(amount, available - remaining)
        await self._session.flush()

    async def reserve(self, user_id: UUID, amount: int, *, task_id: UUID | None = None) -> None:
        await self.consume(
            user_id,
            amount,
            tx_type=TX_RESERVATION,
            description="Reserved for task",
            task_id=task_id,
        )

    async def settle(
        self,
        user_id: UUID,
        *,
        reserved: int,
        actual: int,
        task_id: UUID | None = None,
    ) -> None:
        if actual < 0 or reserved < 0:
            raise ValueError("credits must be non-negative")
        if actual < reserved:
            await self.release(user_id, reserved - actual, task_id=task_id)
        elif actual > reserved:
            await self.consume(
                user_id,
                actual - reserved,
                tx_type=TX_AI_USAGE,
                description="Additional credits after reservation",
                task_id=task_id,
            )

    async def release(self, user_id: UUID, amount: int, *, task_id: UUID | None = None) -> None:
        """Return unused reservation onto the newest monthly lot (or create one)."""
        if amount <= 0:
            return
        now = _utcnow()
        lot = await self._session.scalar(
            select(CreditLot)
            .where(CreditLot.user_id == user_id, CreditLot.source == SOURCE_MONTHLY)
            .order_by(CreditLot.created_at.desc())
        )
        if lot is None:
            lot = CreditLot(
                user_id=user_id,
                source=SOURCE_MONTHLY,
                original_amount=amount,
                remaining_amount=0,
                billing_period=None,
                expires_at=None,
            )
            self._session.add(lot)
            await self._session.flush()
        lot.remaining_amount += amount
        await self._add_tx(
            user_id=user_id,
            lot=lot,
            tx_type=TX_RELEASE,
            amount=amount,
            description="Released unused reservation",
            task_id=task_id,
        )
        await self._session.flush()
        del now
