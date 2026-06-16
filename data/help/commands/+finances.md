---
key: +finances
title: +Finances — Credit Flow Ledger
category: "Commands: Economy"
summary: Review your recent credit income and spending, grouped by source.
aliases: [finances, +ledger]
see_also: [+sheet, +inv, +shop, +commissary]
tags: [credits, economy, ledger, finances, command]
access_level: 0
examples:
  - cmd: "+finances"
    description: "Show credit flow for the last 24 hours (default)."
  - cmd: "+finances hour"
    description: "Show the last hour of transactions."
  - cmd: "+finances week"
    description: "Show the last 7 days."
---

Review your credit income and spending — what you earned and where
it went — grouped by source over a recent time window.

SYNTAX

  +finances           Last 24 hours (default)
  +finances hour      Last hour
  +finances week      Last 7 days

  Aliases: finances, +ledger

OUTPUT

  Your finances — the last 24 hours
  Balance:           12,450 cr
  Earned (faucets):  +3,200 cr
  Spent (sinks):     -1,750 cr
  Net:               +1,450 cr   (8 transactions)
  Top sources:
       +1,500  Mission Reward
       +1,200  Salvage
         +500  Item Sale
  Top spending:
       -1,200  Repair
         -550  Shop Purchase

FIELDS

  Balance     Your current credit balance as of right now.
  Faucets     Sum of all credits received in the window.
  Sinks       Sum of all credits spent (shown as negative).
  Net         Faucets + Sinks — your overall gain or loss.
  Top sources Top 5 credit sources by volume.
  Top spending Top 5 ways you spent credits.

SEE ALSO

  +inv         Show current credit balance alongside inventory.
  +shop        Buy and sell at NPC vendors.
  +commissary  Browse faction supply stock.

EXAMPLES

  +finances
  → Summary of the last 24 hours of credit activity.

  +finances week
  → Broader picture — full week earnings and spending.

  +finances hour
  → Quick check after a recent run.

CHEAT SHEET
  +finances / +finances hour / +finances week
