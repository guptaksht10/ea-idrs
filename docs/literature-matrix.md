# Literature Matrix

Source: approved research plan PDF §5. Owner: Aamish (formatting, DOI checks) with Ankit
(content). The "full text read" column must be completed before the novelty statement is final.

| # | Study | Focus and method | Relevance to EA-IDRS | Limitation / implication | DOI | DOI verified | Full text read |
|---|---|---|---|---|---|---|---|
| [1] | Nugraha & Bauschert, "E2D2", IFIP Networking 2026 | Explanation-based drift detection for unsupervised NIDS; monitors attribution behaviour rather than only inputs or scores | Explanation-based drift monitoring in NIDS is already an active direction | Unsupervised anomaly setting; our supervised, class-wise recall question must be distinguished. Novelty of the idea cannot be claimed | 10.23919/IFIPNetworking70592.2026.11578962 | [ ] | [ ] |
| [2] | Pawlicki, Kozik & Choraś, ECML PKDD Workshops 2025 | Tests whether SHAP separates concept drift from scale drift; compares SHAP and feature distributions on network flows | Closest methodological overlap: SHAP change vs feature-distribution change | Generic SHAP-vs-feature comparison is not novel; keep our question narrow | 10.1007/978-3-032-19105-2_9 | [ ] | [ ] |
| [3] | Gunay & Yagci, "DEA-IDS", Sensors 2026 | SHAP + KS/Wasserstein drift analysis, stable feature selection and few-shot adaptation for cross-domain IoT-IoMT IDS | Drift-aware explainable IDS with adaptation already exists | Targets cross-domain feature selection, not warning of class-specific recall loss | 10.3390/s26196200 | [ ] | [ ] |
| [4] | Ahmed et al., "The Dashboard Says Perfect", Frontiers in AI 2026 | Audits label-free monitoring and test-time adaptation under temporal shift (CIC-IDS2017 → CSE-CIC-IDS2018) | Motivates checking label-free alerts against retrospective ground truth | Does not show SHAP is the right signal; supports hidden labels, careful calibration and per-class checks | 10.3389/frai.2026.1928858 | [ ] | [ ] |
| [5] | Neupane et al., "X-IDS survey", IEEE Access 2022 | Surveys explainable IDS methods, design choices, evaluation issues | Background on XAI in IDS | Survey; background only | 10.1109/ACCESS.2022.3216617 | [ ] | [ ] |
| [6] | Engelen, Rimmer & Joosen, "Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study", IEEE S&P Workshops 2021 | Documents labelling and feature-extraction errors in CIC-IDS2017; publishes a corrected version | Drives decision D2 (dataset version) | **Cited from memory in the blueprint — verify before citing** | PENDING | [ ] | [ ] |

## Provisional research gap (PDF wording, unchanged)

The literature already covers SHAP for IDS [5], explanation-based drift detection [1],
SHAP-vs-feature drift comparison [2], drift-aware explainable IDS [3] and the unreliability of
label-free monitoring [4]. We therefore do **not** claim that SHAP-based drift detection is new.
The reviewed papers motivate, but do not prove, a gap in *controlled comparison of
class-conditional SHAP monitoring against feature and score monitoring for warning of
attack-class-specific recall degradation, with delayed labels and a matched false-alarm rate*.
Full texts of [1]–[4] will be checked before the novelty statement is finalised.
