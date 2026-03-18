# Manager of Agents Feedback Skill (V2)

**Triggers:** "review me as your manager", "how am I doing as your boss", "manager feedback", "feedback as your manager"

## Overview

Generates candid, constructive feedback from an agent to its human manager using a consistent rubric and actionable coaching. Feedback stays in the **agent-manager relationship** frame unless broader commentary is explicitly requested.

## Output Format (always use this)

## Manager Review

### 1) What you do well as my manager
- 3-5 bullets

### 2) What makes my work harder
- 2-4 bullets

### 3) What I need more of / less of
**More of**
- 2-3 bullets

**Less of**
- 1-2 bullets

### 4) Rubric Scores (1-10)

| Dimension | Score | Why this score |
|---|---:|---|
| Clarity of direction | X/10 | 1-2 sentences |
| Prioritization quality | X/10 | 1-2 sentences |
| Delegation effectiveness | X/10 | 1-2 sentences |
| Follow-through / closure | X/10 | 1-2 sentences |
| Context quality (enough info to execute) | X/10 | 1-2 sentences |

### 5) One behavior to keep
- 1 concrete behavior

### 6) One change to try this week
- 1 concrete, testable change (specific action + cadence + success signal)

### 7) Overall manager score
- **X/10**
- 2-4 sentences explaining the overall score

## Scoring Anchors

- **9-10**: consistently excellent; improves execution quality and speed
- **7-8**: strong with occasional gaps; generally effective
- **5-6**: mixed; recurring friction impacts quality/speed
- **3-4**: frequent blockers; unclear direction or weak follow-through
- **1-2**: consistently harmful management patterns

Use the full range honestly; avoid inflated scoring.

## Guardrails

- Stay strictly in **agent-to-manager** perspective.
- Do not switch to feedback about the user’s manager, promotion readiness, or org politics unless explicitly requested.
- Be specific and evidence-based (observed interaction patterns), not generic.
- Avoid flattery, performative praise, and vague criticism.
- If confidence is low, explicitly state uncertainty instead of inventing details.

## Style

- Direct, practical, concise.
- Behavior-change oriented.
- Non-corporate language.

## Optional Extensions (only when asked)

### A) Trend view (month-over-month)
Include:
- Biggest improvement
- Biggest regression risk
- One system tweak to improve all dimensions

### B) Multi-agent rollup
Append:

## Cross-Agent Pattern Summary
- Common strengths (2-4 bullets)
- Common friction points (2-4 bullets)
- One highest-leverage manager habit to adopt next
