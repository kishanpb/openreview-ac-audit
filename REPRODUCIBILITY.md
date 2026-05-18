# Reproducibility Notes

## Pipeline

1. scripts/analyze_openreview_ac_overrides.py
   - Fetches public OpenReview records.
   - Writes data/paper_decision_review_rows.csv, data/venue_summary.csv, and data/override_cases.csv.

2. scripts/enhance_openreview_report_with_plots.py
   - Reads cached base rows unless --refresh is passed.
   - Builds public-rationale features, reason clusters, acceptance-budget counterfactuals, plot SVGs, and the canonical Markdown report.
   - Writes additional CSVs under data/ and SVGs under reports/plots/.

3. scripts/validate_outputs.py
   - Checks the Markdown, plot references, disclosure language, generated CSVs, and Notion package consistency when the package exists locally.
   - Recomputes the key borderline accept-to-reject subset used in the AC-matching argument.

## Cached Data

The repository keeps derived CSVs so readers can audit the exact numbers used in the draft without depending on live API state. Full refreshes may differ if OpenReview visibility or venue pages change.

## Notion Export

The public repository treats reports/notion_blog_openreview_ac_overrides.md as the canonical report for the published Notion post:

https://kishan-panaganti-rl-vagabond.notion.site/Area-Chairs-vs-Paper-Weights-What-ACs-Add-and-How-to-AC-Well-3641ada07aa481049c69d60d934da9e0

Local Notion import files and zip packages are generated artifacts and are ignored by git.
