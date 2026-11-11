---
name: user-language-and-gates
description: Owner wants interview questions and previews in Vietnamese, reports in English with a short Vietnamese summary; decides strategy go/no-go by a backtest gate, with paper only as reconciliation
metadata:
  type: user
---

Conversation-facing text (interview questions, option labels, reframing, preview brief) in Vietnamese; report files under `plans/reports` in English with a short Vietnamese summary at the top (project rule: plans and docs are English).

Decision style seen 2026-11-09: when asked for a strategy pass/fail rule the owner chose "backtest decides (net PF >= 1.2, >= 100 trades over 12 months), paper 2 weeks only reconciles (trades, fees, errors), no profit threshold" over a two-gate rule. The owner also picks "both" when offered a quick no-code path and a code path in parallel, and keeps go-live as a separate decision outside an evidence plan.

**How to apply:** write questions in Vietnamese and keep options concrete with numbers; when proposing gates, offer a backtest-decides variant; do not fold go-live into a research plan unless the owner asks. See [[feedback-no-waiting-no-fake-data]] for the owner's dislike of calendar waits (they accepted a 2-week paper window here knowingly).
