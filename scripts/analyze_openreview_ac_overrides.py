#!/usr/bin/env python3
"""Analyze public OpenReview decisions against simple reviewer-score rules.

The script intentionally keeps dependencies to the Python standard library plus
SciPy/Numpy if present. It fetches public OpenReview notes using the official
API, reduces each paper to review scores, confidence, decision, and meta-review
summary fields, and writes reproducible CSV/Markdown artifacts.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

try:
    import numpy as np
    from scipy import stats
except Exception:  # pragma: no cover - fallback for bare Python installs
    np = None
    stats = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
OPENREVIEW_API2 = "https://api2.openreview.net"
TWEET_URL = "https://x.com/roydanroy/status/2049948895690510736"
TWEET_SYNDICATION_URL = (
    "https://cdn.syndication.twimg.com/tweet-result?"
    "id=2049948895690510736&token=0&lang=en"
)


@dataclass(frozen=True)
class VenueConfig:
    label: str
    domain: str
    year: int
    public_scope: str
    accept_threshold: float | None = None
    analyze_reviews: bool = True


VENUES: list[VenueConfig] = [
    VenueConfig(
        "ICLR 2026",
        "ICLR.cc/2026/Conference",
        2026,
        "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
        6,
    ),
    VenueConfig(
        "ICLR 2025",
        "ICLR.cc/2025/Conference",
        2025,
        "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
        6,
    ),
    VenueConfig(
        "ICLR 2024",
        "ICLR.cc/2024/Conference",
        2024,
        "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
        6,
    ),
    VenueConfig(
        "ICML 2025",
        "ICML.cc/2025/Conference",
        2025,
        "Public OpenReview sample: accepted papers plus public rejected papers; rejected sample is not the full submission pool.",
        3,
    ),
    VenueConfig(
        "NeurIPS 2025",
        "NeurIPS.cc/2025/Conference",
        2025,
        "Public OpenReview sample: accepted papers plus public rejected papers; rejected sample is not the full submission pool.",
        4,
    ),
    VenueConfig(
        "AISTATS 2026",
        "aistats.org/AISTATS/2026/Conference",
        2026,
        "Public accepted papers are listed, but public official reviews/meta-reviews were not exposed in the API sample.",
        None,
        analyze_reviews=False,
    ),
    VenueConfig(
        "RLC 2025",
        "rl-conference.cc/RLC/2025/Conference",
        2025,
        "Public papers expose decision notes, but public official reviews/meta-reviews were not exposed in the API sample.",
        None,
        analyze_reviews=False,
    ),
    VenueConfig(
        "AAAI 2025",
        "AAAI.org/2025/Conference",
        2025,
        "OpenReview venue exists, but public submissions were not exposed through the submissions page/API.",
        None,
        analyze_reviews=False,
    ),
]


def content_value(value: Any) -> Any:
    """OpenReview v2 content fields are usually {'value': ...}."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def clean_text(value: Any) -> str:
    value = content_value(value)
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def first_number(value: Any) -> float | None:
    text = clean_text(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def note_invitation(note: dict[str, Any]) -> str:
    invitations = note.get("invitations")
    if isinstance(invitations, list):
        # The specific per-paper invitation carries the semantic type, while
        # the venue-level "-/Edit" invitation is only a v2 implementation detail.
        for invitation in invitations:
            if "/-/" in invitation and not invitation.endswith("/-/Edit"):
                return invitation
        return invitations[0] if invitations else ""
    return note.get("invitation") or ""


def invitation_kind(note: dict[str, Any]) -> str:
    invitation = note_invitation(note)
    if "/-/" not in invitation:
        return invitation.rsplit("/", 1)[-1]
    return invitation.rsplit("/-/", 1)[-1]


def is_kind(note: dict[str, Any], *kinds: str) -> bool:
    kind = invitation_kind(note).lower()
    return any(k.lower() in kind for k in kinds)


def openreview_get(base_url: str, params: dict[str, Any], tries: int = 6) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{base_url}/notes?{query}"
    ctx = ssl._create_unverified_context()
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "codex-openreview-analysis/1.0"})
            with urllib.request.urlopen(request, context=ctx, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else 3 + attempt * 2
                time.sleep(wait)
                continue
            if 500 <= exc.code < 600:
                time.sleep(2 + attempt * 2)
                continue
            raise
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt * 2)
    raise RuntimeError(f"OpenReview request failed after retries: {url}") from last_error


def fetch_tweet() -> dict[str, Any]:
    ctx = ssl._create_unverified_context()
    try:
        request = urllib.request.Request(TWEET_SYNDICATION_URL, headers={"User-Agent": "codex-openreview-analysis/1.0"})
        with urllib.request.urlopen(request, context=ctx, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def fetch_submissions(config: VenueConfig, limit: int = 1000) -> Iterable[dict[str, Any]]:
    invitation = f"{config.domain}/-/Submission"
    offset = 0
    while True:
        params = {
            "invitation": invitation,
            "limit": limit,
            "offset": offset,
            "details": "directReplies",
        }
        data = openreview_get(OPENREVIEW_API2, params)
        notes = data.get("notes", [])
        if not notes:
            break
        for note in notes:
            yield note
        offset += len(notes)
        count = data.get("count")
        print(f"{config.label}: fetched {offset}/{count or '?'}", file=sys.stderr)
        if count is not None and offset >= int(count):
            break
        if len(notes) < limit:
            break
        time.sleep(0.25)


def classify_decision(domain: str, content: dict[str, Any]) -> tuple[str, str]:
    venueid = clean_text(content.get("venueid"))
    venue = clean_text(content.get("venue"))
    decision_text = clean_text(content.get("decision"))
    combined = f"{venueid} {venue} {decision_text}".lower()

    if "withdrawn" in combined or "withdraw" in combined:
        return "withdrawn", venueid or venue or decision_text
    if "desk reject" in combined or "desk_reject" in combined:
        return "desk_reject", venueid or venue or decision_text
    if "reject" in combined or "rejected" in combined:
        return "reject", venueid or venue or decision_text
    if venueid == domain or any(token in combined for token in ["accept", "accepted", "poster", "spotlight", "oral"]):
        return "accept", venueid or venue or decision_text
    if "submitted to" in combined or "submission" in combined:
        return "submitted_unknown", venueid or venue or decision_text
    return "unknown", venueid or venue or decision_text


def extract_decision_note(replies: list[dict[str, Any]]) -> dict[str, Any] | None:
    decisions = [reply for reply in replies if is_kind(reply, "Decision")]
    if not decisions:
        return None
    return sorted(decisions, key=lambda note: note.get("tcdate") or note.get("cdate") or 0)[-1]


def extract_meta_note(replies: list[dict[str, Any]]) -> dict[str, Any] | None:
    metas = [reply for reply in replies if is_kind(reply, "Meta_Review", "Meta_Review", "Metareview")]
    if not metas:
        return None
    return sorted(metas, key=lambda note: note.get("tcdate") or note.get("cdate") or 0)[-1]


def extract_review_score(content: dict[str, Any]) -> tuple[float | None, str, str]:
    fields = [
        "rating",
        "recommendation",
        "overall_recommendation",
        "Overall_Recommendation",
        "final_rating",
        "final_recommendation",
    ]
    for field in fields:
        if field in content:
            return first_number(content[field]), field, clean_text(content[field])
    # Fallback: scan likely recommendation-ish fields.
    for field, value in content.items():
        if "rating" in field.lower() or "recommend" in field.lower():
            return first_number(value), field, clean_text(value)
    return None, "", ""


def extract_review_confidence(content: dict[str, Any]) -> float | None:
    for field in ["confidence", "reviewer_confidence"]:
        if field in content:
            return first_number(content[field])
    for field, value in content.items():
        if "confidence" in field.lower():
            return first_number(value)
    return None


def meta_text(meta_note: dict[str, Any] | None) -> str:
    if not meta_note:
        return ""
    content = meta_note.get("content") or {}
    preferred = [
        "summary",
        "metareview",
        "metareview:_summary,_strengths_and_weaknesses",
        "reviewer_concerns",
        "comment",
        "justification_for_why_not_higher_score",
        "justification_for_why_not_lower_score",
    ]
    parts: list[str] = []
    for key in preferred:
        text = clean_text(content.get(key))
        if text:
            parts.append(f"{key}: {text}")
    if not parts:
        for key, value in content.items():
            text = clean_text(value)
            if text:
                parts.append(f"{key}: {text}")
    return " | ".join(parts)


def meta_review_themes(meta_note: dict[str, Any] | None) -> str:
    """Return non-verbatim qualitative labels for public meta-review content."""
    text = meta_text(meta_note).lower()
    if not text:
        return "No public meta-review exposed"
    theme_patterns = [
        ("novelty/positioning", r"novel|incremental|prior work|related work|similar|position"),
        ("evidence/baselines", r"experiment|empirical|baseline|comparison|ablation|evaluation|metric"),
        ("correctness/theory", r"correct|proof|assumption|theory|theorem|lemma|math|equation"),
        ("unresolved rebuttal", r"not addressed|unresolved|outstanding|partial|remained|not fully|unconvinc"),
        ("scope/significance", r"significance|contribution|motivation|scope|impact|bar for acceptance"),
        ("presentation/readability", r"readability|unclear|clarity|presentation|writing|hard to follow"),
        ("calibration/process", r"calibration|pc|program chair|inflated|downweight|score"),
        ("reproducibility/implementation", r"implement|code|reproduc|computational|efficiency|practical"),
        ("ethics/safety", r"ethic|safety|harm|privacy|bias"),
    ]
    themes = [label for label, pattern in theme_patterns if re.search(pattern, text)]
    return "; ".join(themes[:5]) if themes else "Meta-review rationale present, no simple keyword theme"


def summarize_decision_content(decision_note: dict[str, Any] | None) -> str:
    if not decision_note:
        return ""
    content = decision_note.get("content") or {}
    parts = []
    for key in ["title", "decision", "comment"]:
        text = clean_text(content.get(key))
        if text:
            parts.append(f"{key}: {text}")
    return " | ".join(parts)[:800]


def reduce_submission(config: VenueConfig, note: dict[str, Any]) -> dict[str, Any]:
    content = note.get("content") or {}
    replies = note.get("details", {}).get("directReplies", []) or []
    decision_note = extract_decision_note(replies)
    decision_source_content = dict(content)
    if decision_note:
        decision_source_content.update(decision_note.get("content") or {})
    decision, decision_label = classify_decision(config.domain, decision_source_content)

    review_rows = []
    for reply in replies:
        if not is_kind(reply, "Official_Review"):
            continue
        review_content = reply.get("content") or {}
        score, score_field, score_text = extract_review_score(review_content)
        confidence = extract_review_confidence(review_content)
        review_rows.append(
            {
                "id": reply.get("id", ""),
                "score": score,
                "confidence": confidence,
                "score_field": score_field,
                "score_text": score_text,
                "signature": ";".join(reply.get("signatures") or []),
            }
        )

    scores = [r["score"] for r in review_rows if r["score"] is not None]
    confidences = [r["confidence"] for r in review_rows if r["score"] is not None]
    weights = [
        (r["confidence"] if r["confidence"] is not None and r["confidence"] > 0 else 1.0)
        for r in review_rows
        if r["score"] is not None
    ]
    weighted_mean = None
    if scores:
        denom = sum(weights)
        weighted_mean = sum(score * weight for score, weight in zip(scores, weights)) / denom if denom else mean(scores)

    accept_threshold = config.accept_threshold
    accept_votes = sum(1 for score in scores if accept_threshold is not None and score >= accept_threshold)
    reject_votes = sum(1 for score in scores if accept_threshold is not None and score < accept_threshold)
    reviewer_majority = "tie"
    if accept_votes > reject_votes:
        reviewer_majority = "accept"
    elif reject_votes > accept_votes:
        reviewer_majority = "reject"

    meta_note = extract_meta_note(replies)
    return {
        "venue": config.label,
        "domain": config.domain,
        "year": config.year,
        "paper_id": note.get("id", ""),
        "paper_number": note.get("number", ""),
        "forum_url": f"https://openreview.net/forum?id={note.get('id', '')}",
        "title": clean_text(content.get("title")),
        "decision": decision,
        "decision_label": decision_label,
        "has_decision_note": bool(decision_note),
        "decision_note": summarize_decision_content(decision_note),
        "n_reviews": len(review_rows),
        "n_scored_reviews": len(scores),
        "scores": " ".join(f"{s:g}" for s in scores),
        "confidences": " ".join("" if c is None else f"{c:g}" for c in confidences),
        "mean_score": mean(scores) if scores else None,
        "median_score": median(scores) if scores else None,
        "confidence_weighted_mean": weighted_mean,
        "accept_threshold": accept_threshold,
        "accept_votes": accept_votes,
        "reject_votes": reject_votes,
        "reviewer_majority": reviewer_majority,
        "meta_review": meta_review_themes(meta_note),
        "has_meta_review": bool(meta_note),
        "meta_signature": ";".join(meta_note.get("signatures") or []) if meta_note else "",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fieldnames})


def auc_score(y: list[int], x: list[float]) -> float | None:
    if len(set(y)) < 2 or not x:
        return None
    pairs = sorted(zip(x, y), key=lambda pair: pair[0])
    ranks: list[float] = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    rank_sum_pos = sum(rank for rank, (_, yy) in zip(ranks, pairs) if yy == 1)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def safe_corr(y: list[int], x: list[float], method: str) -> tuple[float | None, float | None]:
    if len(set(y)) < 2 or len(set(x)) < 2 or len(y) < 3:
        return None, None
    if stats is None:
        return None, None
    if method == "spearman":
        result = stats.spearmanr(x, y)
    else:
        result = stats.pointbiserialr(y, x)
    return float(result.statistic), float(result.pvalue)


def fmt_float(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    try:
        if math.isnan(float(value)):
            return "n/a"
    except Exception:
        pass
    return f"{float(value):.{digits}f}"


def summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    summaries = []
    cases: dict[str, list[dict[str, Any]]] = {}
    for venue in [config.label for config in VENUES]:
        subset = [row for row in rows if row["venue"] == venue]
        analyzable = [
            row
            for row in subset
            if row["decision"] in {"accept", "reject"} and row["n_scored_reviews"] >= 2
        ]
        y = [1 if row["decision"] == "accept" else 0 for row in analyzable]
        x_mean = [float(row["mean_score"]) for row in analyzable]
        x_weight = [float(row["confidence_weighted_mean"]) for row in analyzable]

        threshold_predictions = [
            1 if float(row["confidence_weighted_mean"]) >= float(row["accept_threshold"]) else 0
            for row in analyzable
            if row.get("accept_threshold") is not None
        ]
        threshold_y = [
            yy
            for row, yy in zip(analyzable, y)
            if row.get("accept_threshold") is not None
        ]
        majority_predictions = [
            1 if row["reviewer_majority"] == "accept" else 0 if row["reviewer_majority"] == "reject" else -1
            for row in analyzable
        ]
        maj_eval = [(pred, yy) for pred, yy in zip(majority_predictions, y) if pred != -1]
        pb, pb_p = safe_corr(y, x_weight, "pointbiserial")
        sp, sp_p = safe_corr(y, x_weight, "spearman")

        up_weight = [
            row
            for row in analyzable
            if row.get("accept_threshold") is not None
            and row["decision"] == "accept"
            and float(row["confidence_weighted_mean"]) < float(row["accept_threshold"])
        ]
        down_weight = [
            row
            for row in analyzable
            if row.get("accept_threshold") is not None
            and row["decision"] == "reject"
            and float(row["confidence_weighted_mean"]) >= float(row["accept_threshold"])
        ]
        up_majority = [
            row for row in analyzable if row["decision"] == "accept" and row["reviewer_majority"] == "reject"
        ]
        down_majority = [
            row for row in analyzable if row["decision"] == "reject" and row["reviewer_majority"] == "accept"
        ]
        all_reviewer_accept_to_reject = [
            row
            for row in analyzable
            if row["decision"] == "reject" and row["reject_votes"] == 0 and row["accept_votes"] > 0
        ]
        all_reviewer_reject_to_accept = [
            row
            for row in analyzable
            if row["decision"] == "accept" and row["accept_votes"] == 0 and row["reject_votes"] > 0
        ]

        threshold_accuracy = None
        majority_accuracy = None
        if threshold_predictions:
            threshold_accuracy = sum(int(pred == yy) for pred, yy in zip(threshold_predictions, threshold_y)) / len(threshold_y)
        if maj_eval:
            majority_accuracy = sum(int(pred == yy) for pred, yy in maj_eval) / len(maj_eval)

        decision_counts = {key: sum(1 for row in subset if row["decision"] == key) for key in sorted(set(row["decision"] for row in subset))}
        summaries.append(
            {
                "venue": venue,
                "public_papers": len(subset),
                "papers_with_reviews": sum(1 for row in subset if row["n_scored_reviews"] > 0),
                "analyzable_accept_reject": len(analyzable),
                "accepts": sum(1 for row in analyzable if row["decision"] == "accept"),
                "rejects": sum(1 for row in analyzable if row["decision"] == "reject"),
                "decision_counts": json.dumps(decision_counts, sort_keys=True),
                "mean_reviews": mean([row["n_scored_reviews"] for row in analyzable]) if analyzable else None,
                "weighted_score_pointbiserial_r": pb,
                "weighted_score_pointbiserial_p": pb_p,
                "weighted_score_spearman_r": sp,
                "weighted_score_spearman_p": sp_p,
                "weighted_score_auc": auc_score(y, x_weight),
                "threshold_accuracy": threshold_accuracy,
                "majority_accuracy": majority_accuracy,
                "weighted_accept_to_reject": len(down_weight),
                "weighted_reject_to_accept": len(up_weight),
                "majority_accept_to_reject": len(down_majority),
                "majority_reject_to_accept": len(up_majority),
                "all_accept_to_reject": len(all_reviewer_accept_to_reject),
                "all_reject_to_accept": len(all_reviewer_reject_to_accept),
            }
        )

        cases[f"{venue} accept_to_reject"] = sorted(
            down_majority, key=lambda row: (float(row["confidence_weighted_mean"]), row["accept_votes"]), reverse=True
        )[:12]
        cases[f"{venue} reject_to_accept"] = sorted(
            up_majority, key=lambda row: (float(row["confidence_weighted_mean"]), row["reject_votes"])
        )[:12]
    return summaries, cases


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def case_line(row: dict[str, Any]) -> str:
    return (
        f"- [{row['title']}]({row['forum_url']}) "
        f"({row['venue']}, #{row['paper_number']}): scores `{row['scores']}`, "
        f"threshold `{fmt_float(row['accept_threshold'], 1)}`, "
        f"confidence-weighted mean `{fmt_float(row['confidence_weighted_mean'], 2)}`, "
        f"reviewer majority `{row['reviewer_majority']}`, final `{row['decision']}`. "
        f"Public AC/meta-review themes: {row['meta_review']}."
    )


def build_report(
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    cases: dict[str, list[dict[str, Any]]],
    tweet: dict[str, Any],
) -> str:
    tweet_text = tweet.get("text") or "Area chairs <= paper weights."
    tweet_created = tweet.get("created_at") or "2026-04-30T20:27:57Z"

    summary_rows = []
    for item in summaries:
        summary_rows.append(
            [
                item["venue"],
                item["public_papers"],
                item["papers_with_reviews"],
                item["analyzable_accept_reject"],
                f"{item['accepts']}/{item['rejects']}",
                fmt_float(item["weighted_score_pointbiserial_r"]),
                fmt_float(item["weighted_score_auc"]),
                fmt_float(item["threshold_accuracy"]),
                f"{item['majority_accept_to_reject']}/{item['majority_reject_to_accept']}",
                f"{item['all_accept_to_reject']}/{item['all_reject_to_accept']}",
            ]
        )

    coverage_rows = [
        [config.label, config.domain, config.accept_threshold if config.accept_threshold is not None else "n/a", config.public_scope]
        for config in VENUES
    ]

    report = f"""# Area Chairs vs Paper Weights: A Public OpenReview Audit

_Inspired by._ Dan Roy's tweet on {tweet_created} said: "{tweet_text}" The sharp version of the hypothesis is: if we aggregate reviewer scores with a simple confidence weighting, do area-chair/meta-review decisions mostly reduce to paper weights, or do ACs visibly add judgment?

_Bottom line._ Reviewer scores are strongly predictive where the full public decision surface is visible, especially at ICLR. But the public data also shows a nontrivial set of AC/PC overrides: papers with majority-positive reviews that are rejected, and papers with majority-negative reviews that are accepted. The override set is not noise; it is where the reviewing system is doing its most human work. The problem is that most venues do not publish enough structured meta-review evidence to distinguish good discretion from opaque discretion.

## What Was Measured

- Review score: first numeric value in the public `rating`, `recommendation`, or `overall_recommendation` field.
- Simple weighting: confidence-weighted mean score, using reviewer confidence when present and unit weight otherwise.
- Reviewer accept signal: score at or above a venue-specific threshold (`6` for ICLR, `3` for ICML 2025, `4` for NeurIPS 2025).
- AC override proxy: final public accept/reject decision disagrees with the reviewer-majority signal.
- Strong override: all scored reviewers point one way and the final decision points the other.
- Ethical constraint: AC identities are not deanonymized. The report highlights public paper cases and anonymized meta-review behavior, not named ACs.

## Venue Coverage

{markdown_table(["Venue", "OpenReview domain", "Accept-score threshold", "Public-data interpretation"], coverage_rows)}

## Quantitative Results

{markdown_table(["Venue", "Public papers", "With scores", "Analyzable A/R", "Accept/Reject", "Point-biserial r", "AUC", "Weighted threshold acc.", "Maj. accept->reject / reject->accept", "All accept->reject / reject->accept"], summary_rows)}

Interpretation:

- ICLR is the cleanest measurement setting because rejected papers are broadly public. Across 2024-2026, the confidence-weighted score is highly correlated with the final decision, but hundreds of majority-signal overrides remain visible.
- ICML 2025 and NeurIPS 2025 show high simple-rule accuracy in the public sample, but the sample is dominated by accepted papers. The small public-rejected slice should not be treated as representative of all rejects, and public meta-review rationales are not exposed for the highlighted overrides.
- AISTATS 2026, RLC 2025, and AAAI 2025 cannot support this exact public audit today: public submissions/decisions exist for some of them, but public official reviews and meta-reviews are missing or not exposed in the same OpenReview surface.

Important ICLR 2026 context: the official ICLR retrospective says the review process was disrupted by an OpenReview security incident, after which review scores were reset to the pre-rebuttal state, some AC work was reassigned, and ACs were asked to infer the expected outcome had discussion proceeded normally. That makes ICLR 2026 both valuable and unusual: it is a stress test of AC discretion, but not a clean year for interpreting public reviewer scores as final reviewer intent.

## Where AC/PC Judgment Visibly Overrides Reviewers

### Majority reviewer accept -> final reject

"""
    for key in [k for k in cases if k.endswith("accept_to_reject")]:
        if cases[key]:
            report += f"\n#### {key.replace(' accept_to_reject', '')}\n\n"
            report += "\n".join(case_line(row) for row in cases[key][:6]) + "\n"

    report += "\n### Majority reviewer reject -> final accept\n\n"
    for key in [k for k in cases if k.endswith("reject_to_accept")]:
        if cases[key]:
            report += f"\n#### {key.replace(' reject_to_accept', '')}\n\n"
            report += "\n".join(case_line(row) for row in cases[key][:6]) + "\n"

    report += """
## Qualitative Reading of the Override Cases

The public ICLR meta-reviews suggest four recurring reasons an AC may be more than a weighted average:

1. _Score calibration failure._ Reviewers use the same numeric score differently. A paper with `6 6 6` may be a fragile accept in one area and a clear reject in another if the written concerns reveal unresolved correctness or novelty issues.
2. _Concern aggregation._ A single reviewer may identify a fatal issue that is not numerically reflected in the average. ACs sometimes reject papers whose mean score clears the threshold because the meta-review treats one concern as decision-critical.
3. _Rebuttal updating._ Some accepted papers with weak or negative initial scores appear to have meta-review language indicating that author responses resolved enough uncertainty for the AC/PC to move the paper upward.
4. _Portfolio and venue constraints._ Public decision notes rarely say this explicitly, but borderline papers are affected by area calibration, acceptance budgets, and consistency across similar submissions. This is precisely where thin decision records are least useful to authors.

The qualitative picture is therefore not "ACs are useless" and not "ACs are always right." It is: ACs matter most in the tails and on the boundary, but venues rarely publish enough structured rationale to let the community learn when that discretion improved the outcome.

## Recommendations for Better Reviewing Incentives

1. Publish a structured AC decision delta. Every meta-review should include: reviewer aggregate, AC recommendation, final decision, and a short controlled-vocabulary reason when they disagree.
2. Reward reviewers for calibrated updates, not just timely reviews. Review forms should ask whether the rebuttal changed the reviewer's recommendation and why.
3. Give ACs an explicit override budget report. Not a quota, but a dashboard showing how often they moved against reviewer majority and whether those papers had identifiable fatal concerns, rebuttal resolutions, or score-calibration issues.
4. Create reviewer reliability feedback loops. After decisions, reviewers should see anonymized calibration feedback: how their scores compared with area distributions and final outcomes.
5. Publish venue-level override statistics. Authors can tolerate discretion better when the venue shows how often and why discretion is used.
6. Separate "quality of paper" from "quality of review process." A paper can be rightly rejected while still receiving poor reviews. AC meta-reviews should be evaluated for whether they synthesized the evidence, not merely whether the final decision matched the average.
7. Make meta-review text first-class public data. ICML, NeurIPS, AISTATS, RLC, and AAAI could substantially improve auditability by exposing consistent public meta-review schemas, even if reviewer identities remain anonymous.

## Caveats

- This audit uses public OpenReview data only. It does not include private discussions, SAC/PC deliberations, confidential comments, desk-reject triage, or author-hidden rejected submissions.
- ICLR 2026 should be interpreted separately because of the documented security incident and review-score reset during the discussion period.
- ICML and NeurIPS public rejected papers are likely author-selected or policy-selected; their public reject slices are not representative base rates.
- The thresholds are intentionally simple and venue-specific. They follow the public numeric scales exposed in the review fields, but venues may still use area-specific calibration.
- The analysis highlights anonymized AC/meta-review behavior. It should not be used to identify or shame individual ACs.

## Sources

"""
    report += f"""- Tweet inspiration: [{TWEET_URL}]({TWEET_URL})
- ICLR 2026 process context: [A Retrospective on the ICLR 2026 Review Process](https://blog.iclr.cc/2026/03/31/a-retrospective-on-the-iclr-2026-review-process/)
- ICLR 2026 reviewer/AC workflow: [ICLR 2026 Reviewer Guide](https://iclr.cc/Conferences/2026/ReviewerGuide)
- OpenReview public API: [api2.openreview.net](https://api2.openreview.net)
- OpenReview public submission pages: [ICLR 2026](https://openreview.net/submissions?venue=ICLR.cc%2F2026%2FConference), [ICLR 2025](https://openreview.net/submissions?venue=ICLR.cc%2F2025%2FConference), [ICLR 2024](https://openreview.net/submissions?venue=ICLR.cc%2F2024%2FConference), [ICML 2025](https://openreview.net/submissions?venue=ICML.cc%2F2025%2FConference), [NeurIPS 2025](https://openreview.net/submissions?venue=NeurIPS.cc%2F2025%2FConference), [AISTATS 2026](https://openreview.net/submissions?venue=aistats.org%2FAISTATS%2F2026%2FConference), [RLC 2025](https://openreview.net/submissions?venue=rl-conference.cc%2FRLC%2F2025%2FConference), [AAAI 2025](https://openreview.net/submissions?venue=AAAI.org%2F2025%2FConference)
"""
    return report


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    tweet = fetch_tweet()
    (DATA_DIR / "tweet.json").write_text(json.dumps(tweet, indent=2, sort_keys=True), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for config in VENUES:
        try:
            any_notes = False
            for note in fetch_submissions(config):
                any_notes = True
                rows.append(reduce_submission(config, note))
            if not any_notes:
                rows.append(
                    {
                        "venue": config.label,
                        "domain": config.domain,
                        "year": config.year,
                        "paper_id": "",
                        "paper_number": "",
                        "forum_url": "",
                        "title": "",
                        "decision": "no_public_submissions",
                        "decision_label": "",
                        "has_decision_note": False,
                        "decision_note": "",
                        "n_reviews": 0,
                        "n_scored_reviews": 0,
                        "scores": "",
                        "confidences": "",
                        "mean_score": None,
                        "median_score": None,
                        "confidence_weighted_mean": None,
                        "accept_threshold": config.accept_threshold,
                        "accept_votes": 0,
                        "reject_votes": 0,
                        "reviewer_majority": "",
                        "meta_review": "",
                        "has_meta_review": False,
                        "meta_signature": "",
                    }
                )
        except urllib.error.HTTPError as exc:
            print(f"{config.label}: HTTP error {exc.code}", file=sys.stderr)
        except Exception as exc:
            print(f"{config.label}: failed: {exc}", file=sys.stderr)

    paper_fields = [
        "venue",
        "domain",
        "year",
        "paper_id",
        "paper_number",
        "forum_url",
        "title",
        "decision",
        "decision_label",
        "has_decision_note",
        "decision_note",
        "n_reviews",
        "n_scored_reviews",
        "scores",
        "confidences",
        "mean_score",
        "median_score",
        "confidence_weighted_mean",
        "accept_threshold",
        "accept_votes",
        "reject_votes",
        "reviewer_majority",
        "has_meta_review",
        "meta_signature",
        "meta_review",
    ]
    write_csv(DATA_DIR / "paper_decision_review_rows.csv", rows, paper_fields)

    summaries, cases = summarize(rows)
    summary_fields = [
        "venue",
        "public_papers",
        "papers_with_reviews",
        "analyzable_accept_reject",
        "accepts",
        "rejects",
        "decision_counts",
        "mean_reviews",
        "weighted_score_pointbiserial_r",
        "weighted_score_pointbiserial_p",
        "weighted_score_spearman_r",
        "weighted_score_spearman_p",
        "weighted_score_auc",
        "threshold_accuracy",
        "majority_accuracy",
        "weighted_accept_to_reject",
        "weighted_reject_to_accept",
        "majority_accept_to_reject",
        "majority_reject_to_accept",
        "all_accept_to_reject",
        "all_reject_to_accept",
    ]
    write_csv(DATA_DIR / "venue_summary.csv", summaries, summary_fields)

    case_rows = []
    for case_type, case_list in cases.items():
        for row in case_list:
            out = dict(row)
            out["case_type"] = case_type
            case_rows.append(out)
    write_csv(DATA_DIR / "override_cases.csv", case_rows, ["case_type"] + paper_fields)

    report = build_report(rows, summaries, cases, tweet)
    (REPORT_DIR / "notion_blog_openreview_ac_overrides.md").write_text(report, encoding="utf-8")
    print(REPORT_DIR / "notion_blog_openreview_ac_overrides.md")
    print(DATA_DIR / "venue_summary.csv")
    print(DATA_DIR / "override_cases.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
