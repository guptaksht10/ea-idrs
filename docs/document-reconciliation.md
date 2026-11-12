# Document Reconciliation (source of truth)

Last reviewed: 2026-11-06 by Ankit Raj.

## Priority order

1. **Approved research plan PDF** (`EA-IDRS_Research_Plan_Summary.pdf`): research questions,
   methodology, scope, experiments, deliverables.
2. **Engineering blueprint** (`EA-IDRS_Engineering_Blueprint.md`, 2026-10-31): implementation
   guidance, subject to (1).
3. **Older documents** (synopsis GP050, `PROJECT_REFERENCE.md`, `detailed_research_plan.md`):
   background only.
4. **This repository**: authoritative for what is actually implemented, never for changing (1).

The planning documents are kept outside git (`local-dev/`, gitignored), because they contain
roll numbers and drafts, and the repository is currently public.

## Conflicts found and how they are resolved

| # | Topic | Older documents / repo said | Approved PDF says | Resolution |
|---|---|---|---|---|
| C1 | Name | "XAI-IDS" (`PROJECT_REFERENCE.md`) | EA-IDRS | EA-IDRS everywhere; Python package `eaidrs` |
| C2 | Backend | Express.js gateway + FastAPI; repo has `backend/` (Express) | FastAPI | FastAPI only, from Phase 3. `backend/` is legacy (ADR-0002) |
| C3 | Frontend | React (repo has a Vite React template in `frontend/`) | Streamlit analyst dashboard | Streamlit (ADR-0009). `frontend/` is legacy (ADR-0002) |
| C4 | Database | PostgreSQL, optional Redis | SQLite logging | SQLite in Phase 3 (ADR-0003); not needed for Nov 17 |
| C5 | Task framing | Binary benign/malicious (`detailed_research_plan.md` §9.2, §11.1) | Per-class P/R/F1, "predicted class mix", SHAP "grouped by predicted class" | Multi-class + derived attack probability, **proposed**, guide to confirm (ADR-0006, D1) |
| C6 | Split | Mon–Wed train / Thu val / Fri test (`detailed_research_plan.md` §9.4) | "Chronological train / validation / test"; audit class distribution first | Split strategy is **pending the class-by-time audit** (ADR-0008). Day split kept as a comparison config |
| C7 | SHAP drift | Kendall's τ on the global SHAP ranking | Class-conditional SHAP attribution grouped by predicted class (M4) | Class-conditional; Kendall τ is one candidate distance (Phase 3) |
| C8 | Comparison | KS vs PSI vs SHAP latency | M3 vs M4 at a matched false-alarm budget, delayed labels | M1–M4 + separate evaluator (ADR-0004) |
| C9 | Experiments | Experiments 1–11 (incl. random-vs-temporal split, cross-dataset) | Experiments A–G only | A–G only. No random-split experiment |
| C10 | UNSW-NB15 | Complementary cross-dataset evaluation | Optional, separately processed replication, never merged | Deferred, optional, separate pipeline |
| C11 | Response demo | Attacker container (hping3/scapy), automatic actions implied | Public datasets only; no live/private traffic; analyst-triggered blocking in isolated Docker network | No live capture, no attack tooling, no automatic blocking. Deferred past Nov 17 |
| C12 | Team | 3 members (older docs); 4 incl. Jatin Garg (PDF, blueprint) | 4 listed | **Active sprint team is 3** (Akshat, Ankit, Aamish) per team decision of 2026-11-06. Jatin Garg gets no tasks this sprint. Confirm whether the guide must be told |
| C13 | Member name spelling | "Aamish" (older docs); prompt used "Amish Hussein" | "Aamish Hussain", 23/CS/006 | Docs use the PDF spelling. **Confirm with the member** |
| C14 | Python version | Blueprint: 3.11; repo `ml-service/`: 3.12 | Not specified | 3.12 (already pinned in repo); package supports 3.11–3.13 (ADR-0001) |
| C15 | Major-evaluation date | Blueprint/PDF Gantt: Mar/Apr 2027 | PDF: Mar/Apr 2027 | Team brief says final work runs to Apr/May 2027. **Confirm with guide**; plan assumes the earlier date for safety |
| C16 | `AGENTS.md` | Described Express + React + FastAPI | — | Rewritten on 2026-11-06 to match the approved architecture |

## Actions

- [x] Rewrite `AGENTS.md` to the approved architecture (this PR).
- [ ] Add a "superseded where it conflicts with the PDF" note to the top of
      `PROJECT_REFERENCE.md` and `detailed_research_plan.md` (owner: Ankit; files live outside git).
- [ ] Team decision on deleting `frontend/`, `backend/`, `ml-service/` (owner: Akshat, ADR-0002).
- [ ] Guide confirmation of D1, D2, split strategy, team change and evaluation date (owner: Ankit).
