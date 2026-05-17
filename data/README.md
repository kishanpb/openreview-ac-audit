# Data

These CSVs are derived from public OpenReview records and public source pages. They are cached so the report can be audited against the same public-data snapshot used during drafting.

- paper_decision_review_rows.csv: base paper-level review score, confidence, decision, and meta-review fields.
- venue_summary.csv: venue-level predictive metrics and override counts.
- override_cases.csv: representative override cases from the base analysis.
- meta_decision_text_rows.csv: expanded paper-level public rationale and feature rows used by the qualitative analysis.
- meta_reason_clusters.csv: unsupervised clusters over public ICLR override meta-reviews.
- meta_reason_cluster_assignments.csv: paper-level cluster assignments for clustered public meta-reviews.
- meta_reason_theme_summary.csv: theme counts across override groups.
- guideline_public_evidence_summary.csv: public evidence of guideline-like meta-review behavior.
- acceptance_budget_analysis.csv: acceptance-rate and 3+ accept-vote counterfactuals.
- tweet.json: cached public tweet metadata used by the original prompt framing.

