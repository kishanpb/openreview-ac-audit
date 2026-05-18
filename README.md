# OpenReview AC Override Audit

This repository contains the analysis code, cached public-data tables, plots, and published blog post for Area Chairs vs Paper Weights: What ACs Add, and How to AC Well.

The audit asks how far public OpenReview final decisions move away from simple reviewer-score aggregation, then reads the visible override cases as a process-quality surface for area-chair work.

## Published Post

Read the published essay on Notion: [Area Chairs vs Paper Weights: What ACs Add, and How to AC Well](https://kishan-panaganti-rl-vagabond.notion.site/Area-Chairs-vs-Paper-Weights-What-ACs-Add-and-How-to-AC-Well-3641ada07aa481049c69d60d934da9e0).

## Citation

Use [CITATION.bib](CITATION.bib) to cite the essay and accompanying reproducibility package.

```bibtex
@misc{panaganti2026areaChairsPaperWeights,
  author = {Kishan Panaganti Badrinath},
  title = {Area Chairs vs Paper Weights: What ACs Add, and How to AC Well},
  year = {2026},
  month = may,
  url = {https://kishan-panaganti-rl-vagabond.notion.site/Area-Chairs-vs-Paper-Weights-What-ACs-Add-and-How-to-AC-Well-3641ada07aa481049c69d60d934da9e0},
  note = {Public blog post; source repository: \url{https://github.com/kishanpb/openreview-ac-audit}},
  urldate = {2026-05-18}
}
```

## What Is Included

- scripts/analyze_openreview_ac_overrides.py: fetches public OpenReview submissions, reviews, decisions, meta-reviews, and non-administrative nested public discussion notes, then writes base CSVs.
- scripts/enhance_openreview_report_with_plots.py: builds the meta-review/rationale and public-discussion analysis, plot SVGs, and final Markdown report from cached rows.
- scripts/validate_outputs.py: checks that the regenerated local Markdown, CSV summaries, plots, and optional packaged artifacts are internally consistent.
- data/: cached derived CSVs from public OpenReview records and public source metadata.
- reports/plots/: generated SVG plots used by the analysis and published post.
- reports/experiment_history.md: short summary of the current analysis pass and cleanup history.

## Reproduce

Install dependencies:

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt

Regenerate the local report, SVG plots, and derived CSV summaries from cached public-data rows, then validate them:

    python3 scripts/enhance_openreview_report_with_plots.py
    python3 scripts/validate_outputs.py

Refresh from the current public OpenReview API surface:

    python3 scripts/analyze_openreview_ac_overrides.py
    python3 scripts/enhance_openreview_report_with_plots.py --refresh
    python3 scripts/validate_outputs.py

The refresh path requests both directReplies and replies from the OpenReview API so nested public forum notes are captured separately from direct review/decision/meta-review records. Administrative acknowledgements and withdrawals are excluded from the discussion counts. The cached CSVs capture the public-data snapshot used by the published post. Full Markdown reports, PNG exports, and Notion import bundles are local generated artifacts and are not tracked.

## Scope And Caveats

This is a public-record audit, not a private-process audit. Missing public rationale does not prove missing private AC work, and named examples are not claims that individual decisions were wrong.

The qualitative reading is intentionally bounded: paper-level cases are used because their OpenReview records are public and illustrate process patterns. The author is not affiliated with, advising, collaborating with, or writing on behalf of any author of the papers named or qualitatively discussed, and the author's own ML papers do not appear in the qualitative case analysis.

## Data License Notes

The scripts and local documentation in this repository are released under the MIT License. The CSVs are derived from public OpenReview records and public source pages; downstream users should respect the terms and norms of those source platforms.
