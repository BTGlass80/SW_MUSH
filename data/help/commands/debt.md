---
key: debt
title: "debt — Hutt Cartel Debt"
category: "Commands: Quests"
summary: View and manage your Hutt Cartel debt acquired at the end of the From Dust to Stars quest chain. Weekly payments auto-deduct; you can pay ahead or pay it off in full.
aliases: [+debt]
see_also: [+spacerquest, +finances, +credits, travel]
tags: [quests, credits, economy, command]
access_level: 0
examples:
  - cmd: "debt"
    description: "Show your current debt balance, weekly payment, and next due date."
  - cmd: "debt pay 2000"
    description: "Pay 2,000 credits toward the principal ahead of schedule."
  - cmd: "debt payoff"
    description: "Pay off the entire remaining balance in one lump sum."
---

Shows and manages your Hutt Cartel debt — acquired at Phase 5 of
the **From Dust to Stars** quest chain when Grek arranges your
ship purchase on behalf of Drago the Hutt.

HOW DEBT WORKS

When you buy your Ghtroc 720 in Phase 5, the Hutts front 10,000
credits. The debt then:

  - Auto-deducts a weekly payment from your credits.
  - Tracks missed payments (too many and Grek gets persistent).
  - Clears completely once the principal hits zero.

Paying it off removes the weekly deduction and unlocks the final
quest completion event.

FORMS

  debt                  Show balance, weekly rate, next due, and total paid.
  debt pay <amount>     Pay <amount> credits toward the principal now.
  debt payoff           Pay off everything remaining in one lump sum.

DETAILS

  - Payments are deducted automatically on the weekly schedule. You
    don't need to type anything for the regular payment.
  - `debt pay <amount>` lets you pay ahead — any amount you like.
    Caps at the remaining principal so you can't overpay.
  - `debt payoff` pays the full remaining balance instantly.
  - Partial payments reduce the principal and the number of weekly
    payments remaining. Paying ahead does not change the due date
    for the next auto-deduction — it just reduces the balance
    the auto-deduction applies to.

IF YOU HAVE NO DEBT

`debt` returns: "You don't owe anyone anything. Enjoy your freedom."

Debt is only granted during Phase 5 of the spacer quest chain.
If you haven't reached Phase 5, this command has nothing to show.

CHEAT SHEET
  debt              = show balance and schedule
  debt pay <cr>     = pay <cr> credits toward principal
  debt payoff       = clear the full balance
  +spacerquest      = see overall quest progress
  +finances         = see your complete credit ledger
