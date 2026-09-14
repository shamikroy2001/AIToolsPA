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

### Website monitor (`website_monitor`)

Catalog cost is 3 credits (min 1, max 15). The Arq worker charges after a successful HTTP GET. Unchanged pages still consume credits. If the customer has fewer credits than the cost, that monitor is skipped for the tick (fail soft; no fetch, no notification) and is retried when credits are available. Fetch errors are not charged.

### Gmail analyze (`gmail_analyze`)

Catalog cost is 8 credits (min 2, max 40). The Arq worker charges after a successful read-only Gmail list. Missing/disconnected Gmail, insufficient credits, or Google errors skip that schedule (no charge, `next_run_at` unchanged).

### Telegram notify (`telegram_notify`)

Catalog cost is 1 credit (min 1, max 5). Charged after a successful bot `sendMessage` to the stored chat id. Same fail-soft skip rules as Gmail.

## Reservation (expensive tasks)

Estimate → reserve (row lock) → execute → charge actual → release unused. Concurrent tests are required in D1 for the assistant-ask path.
