# Credits

Customers see **assistant credits**, not tokens. The backend decides task cost via `task_costs`.

## Lots and ledger

Never change `remaining_amount` without a `credit_transactions` row. Balance is reconstructable from the ledger. No negative remaining.

Consumption order:

1. Expiring rollover (soonest `expires_at`)
2. Older rollover
3. Current monthly allocation
4. Purchased top-up (D2; separate expiry policy)

## Monthly allocation

`available = monthly_allowance + min(eligible unused rollover, plan.rollover_cap)`

Rollover lots expire after 90 days (configurable).

## D1 vs D2

- **D1:** monthly grant, rollover, reservation + charge on the simple assistant-ask task.
- **D2:** top-up lots, costs for Gmail/monitor/research/agent tasks, 75/90/100% warnings.

## Reservation (expensive tasks)

Estimate → reserve (row lock) → execute → charge actual → release unused. Concurrent tests are required in D1 for the assistant-ask path.
