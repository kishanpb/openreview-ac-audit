#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "notion_blog_openreview_ac_overrides.md"
IMPORT_REPORT = ROOT / "reports" / "notion_import" / "notion_blog_openreview_ac_overrides.md"
ZIP_REPORT = ROOT / "reports" / "notion_blog_openreview_ac_overrides.zip"
DATA = ROOT / "data"
ANALYZABLE_VENUES = ["ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"]
DISCUSSION_FIELDS = [
    "public_discussion_count",
    "public_discussion_word_count",
    "public_author_response_count",
    "public_reviewer_followup_count",
    "public_ac_pc_comment_count",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str) -> float | None:
    if value in {"", "None", "nan"}:
        return None
    return float(value)


def as_int(value: str) -> int:
    return int(float(value or 0))


def fail(message: str) -> None:
    raise AssertionError(message)


def check_report_basics(text: str) -> None:
    required = [
        "Area Chairs vs Paper Weights: What ACs Add, and How to AC Well",
        "## TLDR: Scores Predict, ACs Explain",
        "<details open>",
        "Expand/collapse the short version",
        "Scores predict. They do not explain.",
        "That split is where ACs earn trust or lose it.",
        "The fix is to score service, not taste:",
        "I am not affiliated with, advising, collaborating with, or writing on behalf of any author",
        "None of my own ML papers appears in the qualitative case analysis",
        "I am not associated with any of the authors corresponding to papers discussed in this blog.",
        "My own ML papers do not appear in the qualitative analysis.",
        "## Reproducibility Package",
        "Nested forum comments, rebuttals, and follow-ups are counted as public engagement evidence after excluding administrative acknowledgements and withdrawals.",
        "author-controlled revision carry-forward",
        "The next AC should see the update, not the old verdict.",
        "score-weight transfer playground",
        "fun transfer sanity check rather than a validation claim",
        "Official rates in the sources here run roughly 24-32%",
        "chance at cleaner conversion, not a promise of acceptance",
        "The separately labeled RLC anecdote is my own process experience",
        "## A Personal Story: Thin Meta-Review as Decision Debt",
        "low-confidence, non-expert meta-review",
        "does not show any rebuttal delta",
        "Confidence: 2: The area chair is not sure.",
        "SAC/domain co-AC repair before release",
    ]
    for phrase in required:
        if phrase not in text:
            fail(f"missing required phrase: {phrase}")
    forbidden = [
        "AISTATS 2026 | 0",
        "RLC 2025 | 0",
        "AAAI 2025 | 0",
        "09_acceptance_budget_pressure",
        "14_neurips_2026_ac_playbook",
        "15_how_to_ac_lifecycle",
        "16_ac_incentive_mechanism",
        "Public rationale themes:",
        "Advisor",
    ]
    for phrase in forbidden:
        if phrase in text:
            fail(f"forbidden stale phrase present: {phrase}")


def check_plot_refs(text: str) -> None:
    refs = re.findall(r"\]\((plots/png/[^)]+\.png)\)", text)
    if len(refs) != 12:
        fail(f"expected 12 plot refs, found {len(refs)}")
    missing = [ref for ref in refs if not (ROOT / "reports" / ref).exists()]
    if missing:
        fail(f"missing plot files: {missing}")
    pngs = sorted((ROOT / "reports" / "plots" / "png").glob("*.png"))
    if len(pngs) != 12:
        fail(f"expected 12 exported PNGs, found {len(pngs)}")


def check_quant_table(text: str) -> None:
    rows = {row["venue"]: row for row in read_csv(DATA / "venue_summary.csv")}
    for venue in ANALYZABLE_VENUES:
        row = rows[venue]
        expected = (
            f"| {venue} | {int(row['public_papers'])} | {int(row['papers_with_reviews'])} | "
            f"{int(row['analyzable_accept_reject'])} | {int(row['accepts'])}/{int(row['rejects'])} | "
            f"{float(row['weighted_score_pointbiserial_r']):.3f} | {float(row['weighted_score_auc']):.3f} | "
            f"{float(row['threshold_accuracy']):.3f} | {int(row['majority_accept_to_reject'])}/{int(row['majority_reject_to_accept'])} | "
            f"{int(row['all_accept_to_reject'])}/{int(row['all_reject_to_accept'])} |"
        )
        if expected not in text:
            fail(f"quantitative table row mismatch for {venue}")


def check_acceptance_claims(text: str) -> None:
    rows = {row["venue"]: row for row in read_csv(DATA / "acceptance_budget_analysis.csv")}
    for venue in ANALYZABLE_VENUES:
        row = rows[venue]
        rejected = int(float(row["three_plus_accept_vote_rejected"]))
        total = int(float(row["three_plus_accept_vote_papers"]))
        forced = int(float(row["capacity_shortfall_if_all_three_plus_accepted"] or 0))
        rationale = int(float(row["three_plus_rejections_not_forced_by_capacity"] or 0))
        load = float(row["three_plus_slot_load"]) * 100
        if f"{venue}: {rejected}/{total} public papers with 3+ accept-leaning reviews were rejected" not in text:
            fail(f"missing 3+ accept-vote fate claim for {venue}")
        if f"{venue}: capacity arithmetic can explain at most {min(forced, rejected)} of those {rejected} rejections; at least {rationale} require" not in text:
            fail(f"missing capacity decomposition claim for {venue}")
        if f"{load:.0f}% of official accept slots" not in text:
            fail(f"missing slot-load claim for {venue}")


def check_score_transfer_playground(text: str) -> None:
    rows = read_csv(DATA / "weighted_score_transfer_playground.csv")
    if not rows:
        fail("missing weighted-score transfer rows")
    required = {
        "source_venue",
        "target_venue",
        "learned_cutoff",
        "source_balanced_accuracy",
        "target_accuracy",
        "target_accept_recall",
        "target_reject_recall",
        "target_borderline_accept_to_reject",
    }
    if missing := required.difference(rows[0]):
        fail(f"weighted-score transfer CSV missing fields: {sorted(missing)}")
    for source, target in [("ICLR 2024", "ICLR 2025"), ("ICLR 2025", "ICLR 2026")]:
        row = next((item for item in rows if item["source_venue"] == source and item["target_venue"] == target), None)
        if not row:
            fail(f"missing score-transfer row for {source} to {target}")
        expected = (
            f"| {source} | {target} | {float(row['learned_cutoff']):.2f} | "
            f"{float(row['source_balanced_accuracy']):.3f} | {float(row['target_accuracy']):.3f} | "
            f"{float(row['target_accept_recall']):.3f} | {float(row['target_reject_recall']):.3f} | "
            f"{int(float(row['target_borderline_accept_to_reject']))} |"
        )
        if expected not in text:
            fail(f"missing score-transfer table row for {source} to {target}")


def check_borderline_matching_claim(text: str) -> None:
    rows = read_csv(DATA / "meta_decision_text_rows.csv")
    borderline = []
    for row in rows:
        threshold = as_float(row["threshold"])
        weighted = as_float(row["weighted_mean"])
        if threshold is None or weighted is None:
            continue
        if (
            row["override_type"] == "accept_to_reject"
            and row["decision"] == "reject"
            and threshold <= weighted < threshold + 0.75
            and int(row["n_scored_reviews"]) >= 3
        ):
            borderline.append(row)
    short = [row for row in borderline if int(row["public_rationale_word_count"]) < 120]
    no_rebuttal = [row for row in borderline if row["feature_mentions_rebuttal"] != "True"]
    no_reviews = [row for row in borderline if row["feature_mentions_reviews"] != "True"]
    discussion = [row for row in borderline if as_int(row["public_discussion_count"]) > 0]
    reviewer_discussion = [row for row in borderline if as_int(row["public_reviewer_followup_count"]) > 0]
    author_discussion = [row for row in borderline if as_int(row["public_author_response_count"]) > 0]
    ac_pc_discussion = [row for row in borderline if as_int(row["public_ac_pc_comment_count"]) > 0]
    claim = (
        f"{len(borderline):,} accept-to-reject cases sit within 0.75 points of the venue accept threshold "
        f"with at least three scored reviews. Of those, {len(short):,} have fewer than 120 public rationale words, "
        f"{len(no_rebuttal):,} have no rebuttal/discussion marker in the meta-review or decision text, "
        f"and {len(no_reviews):,} have no public review-synthesis marker."
    )
    if claim not in text:
        fail("borderline AC-matching subset claim mismatch")
    discussion_claim = (
        f"Within the same borderline set, {len(discussion):,} cases have at least one public discussion note, "
        f"{len(reviewer_discussion):,} have reviewer follow-up, {len(author_discussion):,} have author responses, "
        f"and {len(ac_pc_discussion):,} have AC/PC-authored public discussion comments."
    )
    if discussion_claim not in text:
        fail("borderline public-discussion claim mismatch")


def check_public_discussion_fields(text: str) -> None:
    rows = read_csv(DATA / "meta_decision_text_rows.csv")
    for field in DISCUSSION_FIELDS:
        if field not in rows[0]:
            fail(f"meta decision rows missing {field}")
    summary_rows = read_csv(DATA / "guideline_public_evidence_summary.csv")
    for field in [
        "public_discussion_share",
        "public_reviewer_followup_share",
        "public_author_response_share",
        "public_ac_pc_comment_share",
        "median_public_discussion_words",
    ]:
        if field not in summary_rows[0]:
            fail(f"guideline summary missing {field}")
    by_id = {row["paper_id"]: row for row in rows}
    for paper_id in ["feFlfuOse1", "iJ4i5HE5ER"]:
        row = by_id.get(paper_id)
        if not row or as_int(row["public_discussion_count"]) == 0:
            fail(f"{paper_id} should expose nested public discussion notes")
    if "after excluding administrative acknowledgements and withdrawals" not in text:
        fail("report missing nested public forum discussion readout")


def check_representative_rationale_consistency(text: str) -> None:
    rows = {row["paper_id"]: row for row in read_csv(DATA / "meta_decision_text_rows.csv")}
    bullets = re.findall(
        r"^- \[[^\]]+\]\(https://openreview\.net/forum\?id=([^)]+)\).*?Public rationale: ([^\n]+)$",
        text,
        flags=re.M,
    )
    if not bullets:
        fail("no representative-case rationale bullets found")
    for paper_id, rationale in bullets:
        row = rows.get(paper_id)
        if not row:
            fail(f"representative case {paper_id} is missing from meta decision rows")
        has_meta = row["has_public_meta_review"] == "True"
        has_decision = row["has_public_decision_comment"] == "True"
        if has_meta and "public meta-review" not in rationale:
            fail(f"representative case {paper_id} omits public meta-review source")
        if has_decision and not has_meta and "decision comment" not in rationale:
            fail(f"representative case {paper_id} omits decision-comment source")
        if (has_meta or has_decision) and "no public rationale" in rationale.lower():
            fail(f"representative case {paper_id} falsely says no public rationale")
    gym = [rationale for paper_id, rationale in bullets if paper_id == "feFlfuOse1"]
    if not gym:
        fail("Gymnasium feFlfuOse1 representative case is missing")
    if "public meta-review" not in gym[0] or "Scope / significance" not in gym[0]:
        fail("Gymnasium feFlfuOse1 representative case does not reflect its public meta-review themes")


def check_optional_package(text: str) -> None:
    if IMPORT_REPORT.exists() and IMPORT_REPORT.read_text(encoding="utf-8") != text:
        fail("Notion import Markdown is out of sync with canonical report")
    if ZIP_REPORT.exists():
        with zipfile.ZipFile(ZIP_REPORT) as archive:
            names = archive.namelist()
            if "notion_blog_openreview_ac_overrides.md" not in names:
                fail("zip is missing Notion Markdown")
            zipped = archive.read("notion_blog_openreview_ac_overrides.md").decode("utf-8")
            if zipped != text:
                fail("zip Markdown is out of sync with canonical report")
            if sum(name.endswith(".png") for name in names) != 12:
                fail("zip should contain 12 PNG plots")


def main() -> int:
    if not REPORT.exists():
        fail(f"missing report: {REPORT}")
    text = REPORT.read_text(encoding="utf-8")
    check_report_basics(text)
    check_plot_refs(text)
    check_quant_table(text)
    check_acceptance_claims(text)
    check_score_transfer_playground(text)
    check_borderline_matching_claim(text)
    check_public_discussion_fields(text)
    check_representative_rationale_consistency(text)
    check_optional_package(text)
    print("validated report, CSV claims, plot refs, disclosures, and optional Notion package")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
