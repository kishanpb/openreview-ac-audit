#!/usr/bin/env python3
"""Add standalone plots and meta-review analysis to the OpenReview AC audit."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import random
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
PLOT_DIR = REPORT_DIR / "plots"
OPENREVIEW_API2 = "https://api2.openreview.net"
BLOG_TITLE = "Area Chairs vs Paper Weights: What ACs Add, and How to AC Well"
ROY_TWEET_URL = "https://x.com/roydanroy/status/2049948895690510736"
SARATH_TWEET_URL = "https://x.com/apsarathchandar/status/2050377912864342048"
CRC_ICLR_2026_DISTRIBUTION_URL = "https://x.com/CRC_8341/status/2053411384965407149"
AMIT_CONFERENCE_DISTRIBUTION_URL = "https://x.com/AmitLeViAI/status/2053588076551676199"
NEURIPS_2026_HANDBOOK_URL = "https://nips.cc/Conferences/2026/MainTrackHandbook"
NEURIPS_2026_AC_PILOT_URL = "https://blog.neurips.cc/2026/03/23/refining-the-review-cycle-neurips-2026-area-chair-pilot/"
NEURIPS_2026_REVIEWING_GUIDELINES_URL = "https://neurips.cc/Conferences/2026/ReviewerGuidelines"
RLC_2026_SUBMISSION_URL = "https://rl-conference.cc/submissionInstructions.html"
ARR_2026_INCENTIVES_URL = "https://aclrollingreview.org/incentives2026"
AYAN_LINKEDIN_URL = "https://www.linkedin.com/posts/ayan-banerjee-6337589_neurips-had-close-to-40k-submissions-the-share-7458685306699960320-BoIx"
BITTER_LESSON_URL = "http://www.incompleteideas.net/IncIdeas/BitterLesson.html"

VENUES = [
    {
        "label": "ICLR 2026",
        "domain": "ICLR.cc/2026/Conference",
        "threshold": 6.0,
        "fetch": True,
    },
    {
        "label": "ICLR 2025",
        "domain": "ICLR.cc/2025/Conference",
        "threshold": 6.0,
        "fetch": True,
    },
    {
        "label": "ICLR 2024",
        "domain": "ICLR.cc/2024/Conference",
        "threshold": 6.0,
        "fetch": True,
    },
    {
        "label": "ICML 2025",
        "domain": "ICML.cc/2025/Conference",
        "threshold": 3.0,
        "fetch": True,
    },
    {
        "label": "NeurIPS 2025",
        "domain": "NeurIPS.cc/2025/Conference",
        "threshold": 4.0,
        "fetch": True,
    },
    {
        "label": "AISTATS 2026",
        "domain": "aistats.org/AISTATS/2026/Conference",
        "threshold": None,
        "fetch": True,
    },
    {
        "label": "RLC 2025",
        "domain": "rl-conference.cc/RLC/2025/Conference",
        "threshold": None,
        "fetch": True,
    },
    {
        "label": "AAAI 2025",
        "domain": "AAAI.org/2025/Conference",
        "threshold": None,
        "fetch": False,
    },
]

ANALYZABLE_VENUE_LABELS = {"ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"}
CONTEXT_ONLY_VENUE_LABELS = {"AISTATS 2026", "RLC 2025", "AAAI 2025"}
VENUE_INTERPRETATIONS = {
    "ICLR 2026": "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
    "ICLR 2025": "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
    "ICLR 2024": "Full public submissions on OpenReview, including accepted/rejected/withdrawn where public notes expose decisions.",
    "ICML 2025": "Public OpenReview sample: accepted papers plus public rejected papers; rejected sample is not the full submission pool.",
    "NeurIPS 2025": "Public OpenReview sample: accepted papers plus public rejected papers; rejected sample is not the full submission pool.",
}

ACCEPTANCE_BENCHMARKS = [
    {
        "venue": "ICLR 2026",
        "submitted": 19525,
        "accepted": 5355,
        "rate": 0.274,
        "source_label": "ICLR 2026 retrospective",
        "source_url": "https://blog.iclr.cc/2026/03/31/a-retrospective-on-the-iclr-2026-review-process/",
    },
    {
        "venue": "ICLR 2025",
        "submitted": 11565,
        "accepted": 3710,
        "rate": 0.3208,
        "source_label": "RIKEN AIP ICLR 2025 acceptance note",
        "source_url": "https://aip.riken.jp/news/iclr2025/?lang=en",
    },
    {
        "venue": "ICLR 2024",
        "submitted": 7262,
        "accepted": 2260,
        "rate": 0.31,
        "source_label": "ICLR 2024 fact sheet",
        "source_url": "https://media.iclr.cc/Conferences/ICLR2024/ICLR2024-Fact_Sheet.pdf",
    },
    {
        "venue": "ICML 2025",
        "submitted": 12107,
        "accepted": 3260,
        "rate": 0.2693,
        "source_label": "RIKEN AIP ICML 2025 acceptance note",
        "source_url": "https://aip.riken.jp/news/icml2025/?lang=en",
    },
    {
        "venue": "NeurIPS 2025",
        "submitted": 21575,
        "accepted": 5290,
        "rate": 0.2452,
        "source_label": "RIKEN AIP NeurIPS 2025 acceptance note",
        "source_url": "https://aip.riken.jp/news/neurips2025/?lang=en",
    },
    {
        "venue": "AISTATS 2026",
        "submitted": None,
        "accepted": None,
        "rate": 0.25,
        "source_label": "AISTATS 2026 CFP says acceptance rates tend to be around 25%",
        "source_url": "https://virtual.aistats.org/Conferences/2026/CallForPapers",
    },
    {
        "venue": "RLC 2025",
        "submitted": 295,
        "accepted": 115,
        "rate": 0.390,
        "source_label": "RIKEN AIP RLC 2025 acceptance note",
        "source_url": "https://aip.riken.jp/news/rlc2025/?lang=en",
    },
    {
        "venue": "AAAI 2025",
        "submitted": 12957,
        "accepted": 3032,
        "rate": 0.234,
        "source_label": "RIKEN AIP AAAI-25 acceptance note",
        "source_url": "https://aip.riken.jp/news/202412_aaai25/",
    },
]

THEMES = [
    (
        "Novelty / related work",
        r"\b(novel|novelty|incremental|prior work|related work|similar|positioning|contribution)\b",
    ),
    (
        "Evidence / baselines",
        r"\b(experiment|empirical|baseline|comparison|ablation|evaluation|metric|dataset|result)\b",
    ),
    (
        "Correctness / theory",
        r"\b(correct|proof|assumption|theory|theorem|lemma|math|equation|claim|soundness)\b",
    ),
    (
        "Unresolved rebuttal",
        r"\b(not addressed|unresolved|outstanding|partial|remained|not fully|unconvincing|response did not)\b",
    ),
    (
        "Scope / significance",
        r"\b(significance|scope|impact|motivation|bar for acceptance|importance|relevance)\b",
    ),
    (
        "Presentation / clarity",
        r"\b(readability|unclear|clarity|presentation|writing|hard to follow|organization)\b",
    ),
    (
        "Calibration / review quality",
        r"\b(calibration|program chair|pc|inflated|downweight|score|review quality|superficial|reviewer)\b",
    ),
    (
        "Implementation / reproducibility",
        r"\b(implement|code|reproduc|computational|efficiency|practical|runtime|open source)\b",
    ),
    (
        "Ethics / safety",
        r"\b(ethic|safety|harm|privacy|bias|jailbreak|misuse)\b",
    ),
]

GUIDELINE_FEATURES = [
    ("60+ words", "AC rationale is at least 60 words"),
    ("Mentions reviews", "Synthesizes reviewer evidence or concerns"),
    ("Mentions rebuttal/discussion", "References author response, rebuttal, or discussion"),
    ("Strengths+weaknesses", "Contains both positive and negative assessment language"),
    ("Decision/recommendation", "States a decision or recommendation"),
    ("Causal justification", "Uses explicit reason/issue/concern language"),
]

STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "although",
    "among",
    "and",
    "another",
    "are",
    "around",
    "authors",
    "because",
    "been",
    "being",
    "but",
    "can",
    "could",
    "does",
    "during",
    "each",
    "few",
    "for",
    "from",
    "has",
    "have",
    "however",
    "into",
    "its",
    "may",
    "more",
    "most",
    "not",
    "one",
    "only",
    "our",
    "out",
    "paper",
    "papers",
    "review",
    "reviewer",
    "reviewers",
    "reviews",
    "some",
    "submission",
    "such",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "through",
    "was",
    "were",
    "which",
    "while",
    "with",
    "work",
    "would",
    "added",
    "addressed",
    "approach",
    "approaches",
    "concern",
    "concerns",
    "discussion",
    "higher",
    "justification",
    "lower",
    "method",
    "methods",
    "metareview",
    "model",
    "models",
    "overall",
    "problem",
    "proposed",
    "raised",
    "result",
    "results",
    "score",
    "scores",
    "summary",
    "they",
}
STOPWORDS.update(
    {
        "all",
        "based",
        "believe",
        "other",
        "rating",
        "should",
        "think",
        "very",
        "well",
    }
)


def content_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def clean_text(value: Any) -> str:
    value = content_value(value)
    if value is None:
        return ""
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def first_number(value: Any) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", clean_text(value))
    return float(match.group(0)) if match else None


def note_invitation(note: dict[str, Any]) -> str:
    invitations = note.get("invitations")
    if isinstance(invitations, list):
        for invitation in invitations:
            if "/-/" in invitation and not invitation.endswith("/-/Edit"):
                return invitation
        return invitations[0] if invitations else ""
    return note.get("invitation") or ""


def invitation_kind(note: dict[str, Any]) -> str:
    invitation = note_invitation(note)
    if "/-/" in invitation:
        return invitation.rsplit("/-/", 1)[-1]
    return invitation.rsplit("/", 1)[-1]


def is_kind(note: dict[str, Any], *kinds: str) -> bool:
    kind = invitation_kind(note).lower()
    return any(k.lower() in kind for k in kinds)


def openreview_get(params: dict[str, Any], tries: int = 7) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{OPENREVIEW_API2}/notes?{query}"
    ctx = ssl._create_unverified_context()
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "codex-openreview-analysis/1.1"})
            with urllib.request.urlopen(request, context=ctx, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 + attempt * 2)
    raise RuntimeError(f"OpenReview request failed: {url}") from last_error


def fetch_submissions(config: dict[str, Any], limit: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = openreview_get(
            {
                "invitation": f"{config['domain']}/-/Submission",
                "limit": limit,
                "offset": offset,
                "details": "directReplies",
            }
        )
        notes = data.get("notes", [])
        if not notes:
            break
        rows.extend(notes)
        offset += len(notes)
        count = data.get("count")
        print(f"{config['label']}: fetched {offset}/{count or '?'}", file=sys.stderr)
        if count is not None and offset >= int(count):
            break
        if len(notes) < limit:
            break
        time.sleep(0.25)
    return rows


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
    notes = [reply for reply in replies if is_kind(reply, "Decision")]
    return sorted(notes, key=lambda note: note.get("tcdate") or note.get("cdate") or 0)[-1] if notes else None


def extract_meta_note(replies: list[dict[str, Any]]) -> dict[str, Any] | None:
    notes = [reply for reply in replies if is_kind(reply, "Meta_Review", "Metareview")]
    return sorted(notes, key=lambda note: note.get("tcdate") or note.get("cdate") or 0)[-1] if notes else None


def extract_review_score(content: dict[str, Any]) -> tuple[float | None, str, str]:
    for field in ["rating", "recommendation", "overall_recommendation", "final_rating", "final_recommendation"]:
        if field in content:
            return first_number(content[field]), field, clean_text(content[field])
    for field, value in content.items():
        if "rating" in field.lower() or "recommend" in field.lower():
            return first_number(value), field, clean_text(value)
    return None, "", ""


def extract_review_confidence(content: dict[str, Any]) -> float | None:
    for field, value in content.items():
        if "confidence" in field.lower():
            return first_number(value)
    return None


def note_text(note: dict[str, Any] | None) -> str:
    if not note:
        return ""
    content = note.get("content") or {}
    preferred = [
        "summary",
        "metareview",
        "metareview:_summary,_strengths_and_weaknesses",
        "reviewer_concerns",
        "reviewer_scores",
        "comment",
        "justification_for_why_not_higher_score",
        "justification_for_why_not_lower_score",
        "decision",
        "title",
    ]
    parts = []
    seen = set()
    for key in preferred:
        if key in content:
            seen.add(key)
            text = clean_text(content.get(key))
            if text:
                parts.append(f"{key}: {text}")
    for key, value in content.items():
        if key in seen:
            continue
        text = clean_text(value)
        if text:
            parts.append(f"{key}: {text}")
    return " | ".join(parts)


def review_stats(replies: list[dict[str, Any]], threshold: float | None) -> dict[str, Any]:
    scores = []
    confidences = []
    for reply in replies:
        if not is_kind(reply, "Official_Review"):
            continue
        score, _, _ = extract_review_score(reply.get("content") or {})
        confidence = extract_review_confidence(reply.get("content") or {})
        if score is None:
            continue
        scores.append(score)
        confidences.append(confidence if confidence is not None and confidence > 0 else 1.0)
    weighted_mean = ""
    if scores:
        weighted_mean = sum(s * c for s, c in zip(scores, confidences)) / sum(confidences)
    accept_votes = sum(1 for score in scores if threshold is not None and score >= threshold)
    reject_votes = sum(1 for score in scores if threshold is not None and score < threshold)
    if accept_votes > reject_votes:
        majority = "accept"
    elif reject_votes > accept_votes:
        majority = "reject"
    else:
        majority = "tie"
    return {
        "scores": scores,
        "n_scored_reviews": len(scores),
        "weighted_mean": weighted_mean,
        "accept_votes": accept_votes,
        "reject_votes": reject_votes,
        "reviewer_majority": majority,
    }


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", text))


def boolean_features(meta_text: str, decision_text: str) -> dict[str, bool]:
    text = f"{meta_text} {decision_text}".lower()
    meta_lower = meta_text.lower()
    positive = bool(re.search(r"\b(strength|positive|strong|merit|well written|valuable|novel)\b", meta_lower))
    negative = bool(re.search(r"\b(weakness|concern|issue|limitation|flaw|unclear|insufficient|lack)\b", meta_lower))
    return {
        "feature_60_words": word_count(meta_text) >= 60,
        "feature_mentions_reviews": bool(re.search(r"\b(reviewer|reviewers|reviews|score|concern)\b", text)),
        "feature_mentions_rebuttal": bool(re.search(r"\b(rebuttal|response|author feedback|discussion|after discussion|updated|addressed)\b", text)),
        "feature_strengths_weaknesses": positive and negative,
        "feature_decision_recommendation": bool(re.search(r"\b(accept|reject|recommend|decision)\b", text)),
        "feature_causal_justification": bool(re.search(r"\b(because|due to|therefore|thus|given|concern|issue|rationale|reason)\b", text)),
    }


def theme_flags(text: str) -> dict[str, bool]:
    lower = text.lower()
    return {name: bool(re.search(pattern, lower)) for name, pattern in THEMES}


def reduce_submission(config: dict[str, Any], note: dict[str, Any]) -> dict[str, Any]:
    content = note.get("content") or {}
    replies = note.get("details", {}).get("directReplies", []) or []
    decision_note = extract_decision_note(replies)
    meta_note = extract_meta_note(replies)
    decision_source = dict(content)
    if decision_note:
        decision_source.update(decision_note.get("content") or {})
    decision, decision_label = classify_decision(config["domain"], decision_source)
    stats = review_stats(replies, config["threshold"])
    reviewer_majority = stats["reviewer_majority"]
    override_type = "not_analyzable"
    if decision in {"accept", "reject"} and stats["n_scored_reviews"] >= 2:
        if decision == "reject" and reviewer_majority == "accept":
            override_type = "accept_to_reject"
        elif decision == "accept" and reviewer_majority == "reject":
            override_type = "reject_to_accept"
        elif reviewer_majority in {"accept", "reject"}:
            override_type = "aligned"
        else:
            override_type = "tie"
    strong_override = (
        (override_type == "accept_to_reject" and stats["reject_votes"] == 0 and stats["accept_votes"] > 0)
        or (override_type == "reject_to_accept" and stats["accept_votes"] == 0 and stats["reject_votes"] > 0)
    )
    meta = note_text(meta_note)
    decision_text = note_text(decision_note)
    features = boolean_features(meta, decision_text)
    feature_score = sum(features.values()) / len(features)
    themes = theme_flags(f"{meta} {decision_text}")
    return {
        "venue": config["label"],
        "domain": config["domain"],
        "paper_id": note.get("id", ""),
        "paper_number": note.get("number", ""),
        "forum_url": f"https://openreview.net/forum?id={note.get('id', '')}",
        "title": clean_text(content.get("title")),
        "decision": decision,
        "decision_label": decision_label,
        "threshold": config["threshold"] if config["threshold"] is not None else "",
        "n_scored_reviews": stats["n_scored_reviews"],
        "scores": " ".join(f"{score:g}" for score in stats["scores"]),
        "weighted_mean": stats["weighted_mean"],
        "accept_votes": stats["accept_votes"],
        "reject_votes": stats["reject_votes"],
        "reviewer_majority": reviewer_majority,
        "override_type": override_type,
        "strong_override": strong_override,
        "has_public_meta_review": bool(meta),
        "has_public_decision_comment": word_count(decision_text) > 4,
        "meta_word_count": word_count(meta),
        "decision_word_count": word_count(decision_text),
        "public_rationale_word_count": word_count(meta) + word_count(decision_text),
        "guideline_evidence_score": feature_score,
        "meta_text": meta,
        "decision_text": decision_text,
        **features,
        **{f"theme_{name}": value for name, value in themes.items()},
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for field in [
            "threshold",
            "weighted_mean",
            "guideline_evidence_score",
        ]:
            if row.get(field) in {"", None}:
                row[field] = None
            else:
                row[field] = float(row[field])
        for field in [
            "n_scored_reviews",
            "paper_number",
            "accept_votes",
            "reject_votes",
            "meta_word_count",
            "decision_word_count",
            "public_rationale_word_count",
        ]:
            if row.get(field) not in {"", None}:
                row[field] = int(float(row[field]))
        for field in ["strong_override", "has_public_meta_review", "has_public_decision_comment"] + [
            key for key in row.keys() if key.startswith("feature_") or key.startswith("theme_")
        ]:
            row[field] = str(row.get(field)).lower() == "true"
    return rows


def fetch_or_load_meta_rows(refresh: bool = False) -> list[dict[str, Any]]:
    path = DATA_DIR / "meta_decision_text_rows.csv"
    if path.exists() and not refresh:
        return read_csv(path)
    rows = []
    for config in VENUES:
        if not config["fetch"]:
            rows.append(
                {
                    "venue": config["label"],
                    "domain": config["domain"],
                    "paper_id": "",
                    "paper_number": "",
                    "forum_url": "",
                    "title": "",
                    "decision": "no_public_submissions",
                    "override_type": "not_analyzable",
                    "n_scored_reviews": 0,
                    "has_public_meta_review": False,
                    "has_public_decision_comment": False,
                    "meta_word_count": 0,
                    "decision_word_count": 0,
                    "public_rationale_word_count": 0,
                    "guideline_evidence_score": 0.0,
                    "meta_text": "",
                    "decision_text": "",
                }
            )
            continue
        for note in fetch_submissions(config):
            rows.append(reduce_submission(config, note))
    fields = [
        "venue",
        "domain",
        "paper_id",
        "paper_number",
        "forum_url",
        "title",
        "decision",
        "decision_label",
        "threshold",
        "n_scored_reviews",
        "scores",
        "weighted_mean",
        "accept_votes",
        "reject_votes",
        "reviewer_majority",
        "override_type",
        "strong_override",
        "has_public_meta_review",
        "has_public_decision_comment",
        "meta_word_count",
        "decision_word_count",
        "public_rationale_word_count",
        "guideline_evidence_score",
        "meta_text",
        "decision_text",
    ]
    fields += [feature for feature, _ in GUIDELINE_FEATURES]
    feature_key_map = {
        "60+ words": "feature_60_words",
        "Mentions reviews": "feature_mentions_reviews",
        "Mentions rebuttal/discussion": "feature_mentions_rebuttal",
        "Strengths+weaknesses": "feature_strengths_weaknesses",
        "Decision/recommendation": "feature_decision_recommendation",
        "Causal justification": "feature_causal_justification",
    }
    fields = [field for field in fields if field not in feature_key_map]
    fields += list(feature_key_map.values())
    fields += [f"theme_{name}" for name, _ in THEMES]
    write_csv(path, rows, fields)
    return read_csv(path)


def load_summary_rows() -> list[dict[str, Any]]:
    rows = []
    with (DATA_DIR / "venue_summary.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key in [
                "public_papers",
                "papers_with_reviews",
                "analyzable_accept_reject",
                "accepts",
                "rejects",
                "majority_accept_to_reject",
                "majority_reject_to_accept",
                "all_accept_to_reject",
                "all_reject_to_accept",
            ]:
                row[key] = int(float(row[key] or 0))
            for key in [
                "weighted_score_pointbiserial_r",
                "weighted_score_auc",
                "threshold_accuracy",
                "majority_accuracy",
            ]:
                row[key] = float(row[key]) if row[key] else None
            rows.append(row)
    return rows


def fmt_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def build_venue_coverage_section() -> str:
    rows = []
    for config in VENUES:
        if config["label"] not in ANALYZABLE_VENUE_LABELS:
            continue
        threshold = config["threshold"] if config["threshold"] is not None else "n/a"
        rows.append(
            f"| {config['label']} | {config['domain']} | {threshold} | {VENUE_INTERPRETATIONS[config['label']]} |"
        )
    excluded = ", ".join(["AISTATS 2026", "RLC 2025", "AAAI 2025"])
    return f"""## Venue Coverage

| Venue | OpenReview domain | Accept-score threshold | Public-data interpretation |
| --- | --- | --- | --- |
{chr(10).join(rows)}

Context-only venues excluded from aggregate tables: {excluded}. They are useful process references, but their public OpenReview surfaces did not expose comparable review-score and meta-review data for this audit; showing zero-filled rows would be misleading.

"""


def build_quantitative_results_section() -> str:
    rows = [
        row
        for row in load_summary_rows()
        if row["venue"] in ANALYZABLE_VENUE_LABELS
        and row["papers_with_reviews"] > 0
        and row["analyzable_accept_reject"] > 0
    ]
    order = {venue: i for i, venue in enumerate(["ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"])}
    rows.sort(key=lambda row: order[row["venue"]])
    table_rows = []
    for row in rows:
        table_rows.append(
            "| "
            + " | ".join(
                [
                    row["venue"],
                    str(row["public_papers"]),
                    str(row["papers_with_reviews"]),
                    str(row["analyzable_accept_reject"]),
                    f"{row['accepts']}/{row['rejects']}",
                    fmt_metric(row["weighted_score_pointbiserial_r"]),
                    fmt_metric(row["weighted_score_auc"]),
                    fmt_metric(row["threshold_accuracy"]),
                    f"{row['majority_accept_to_reject']}/{row['majority_reject_to_accept']}",
                    f"{row['all_accept_to_reject']}/{row['all_reject_to_accept']}",
                ]
            )
            + " |"
        )
    return f"""## Quantitative Results

| Venue | Public papers | With scores | Analyzable A/R | Accept/Reject | Point-biserial r | AUC | Weighted threshold acc. | Maj. accept->reject / reject->accept | All accept->reject / reject->accept |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(table_rows)}

Interpretation:

- ICLR is the cleanest measurement setting because rejected papers are broadly public. Across 2024-2026, the confidence-weighted score is highly correlated with the final decision, but hundreds of majority-signal overrides remain visible.
- ICML 2025 and NeurIPS 2025 show high simple-rule accuracy in the public sample, but the sample is dominated by accepted papers. The small public-rejected slice should not be treated as representative of all rejects, and public meta-review rationales are not exposed for the highlighted overrides.
- AISTATS 2026, RLC 2025, and AAAI 2025 are not counted in this table. They appear only in caveats/sources because the public surfaces did not expose enough comparable review or meta-review structure for this audit.

"""


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def svg_text(x: float, y: float, text: str, size: int = 13, weight: str = "400", color: str = "#17202a", anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Inter, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{esc(text)}</text>'
    )


def wrap_svg_text(x: float, y: float, text: str, max_chars: int, size: int = 12, color: str = "#4d5965") -> tuple[str, float]:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    out = []
    for i, line in enumerate(lines):
        out.append(svg_text(x, y + i * (size + 4), line, size=size, color=color))
    return "\n".join(out), y + max(1, len(lines)) * (size + 4)


def svg_frame(width: int, height: int, title: str, subtitle: str) -> tuple[list[str], int, int, int, int]:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfbf8"/>',
        svg_text(28, 36, title, size=24, weight="700", color="#111827"),
    ]
    wrapped, y_after = wrap_svg_text(28, 64, subtitle, max_chars=104, size=14, color="#4b5563")
    parts.append(wrapped)
    top = int(y_after + 20)
    left, right, bottom = 185, width - 32, height - 64
    return parts, left, right, top, bottom


def save_svg(path: Path, parts: list[str]) -> None:
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def plot_predictiveness(summary_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "01_predictiveness_metrics.svg"
    rows = [row for row in summary_rows if row["weighted_score_auc"] is not None]
    width, height = 980, 470
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "How well do simple reviewer-score rules predict final decisions?",
        "AUC measures ranking quality of confidence-weighted review scores; threshold and majority accuracy are direct accept/reject rules. ICML/NeurIPS are public samples, not full reject pools.",
    )
    colors = {"AUC": "#2f6f73", "Threshold acc.": "#d58c2a", "Majority acc.": "#7158a8"}
    x0, x1 = left, right - 150
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(svg_text(x, bottom + 18, f"{tick:.2f}", size=11, color="#6b7280", anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * y_step + 10
        parts.append(svg_text(28, y + 23, row["venue"], size=13, weight="600"))
        metrics = [
            ("AUC", row["weighted_score_auc"]),
            ("Threshold acc.", row["threshold_accuracy"]),
            ("Majority acc.", row["majority_accuracy"]),
        ]
        for j, (name, value) in enumerate(metrics):
            yy = y + j * 18
            w = (x1 - x0) * value
            parts.append(f'<rect x="{x0}" y="{yy}" width="{w:.1f}" height="12" rx="2" fill="{colors[name]}"/>')
            parts.append(svg_text(x0 + w + 6, yy + 10, f"{value:.2f}", size=11, color="#374151"))
    legend_x = right - 126
    for j, (name, color) in enumerate(colors.items()):
        yy = top + 12 + j * 24
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="13" height="13" fill="{color}"/>')
        parts.append(svg_text(legend_x + 20, yy + 11, name, size=12))
    parts.append(svg_text(28, height - 16, "Source: public OpenReview notes fetched via api2.openreview.net; thresholds: ICLR=6, ICML=3, NeurIPS=4.", size=11, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_override_counts(summary_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "02_override_counts.svg"
    rows = [row for row in summary_rows if row["analyzable_accept_reject"] > 0]
    max_total = max(row["majority_accept_to_reject"] + row["majority_reject_to_accept"] for row in rows)
    width, height = 980, 470
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Where final decisions move against the reviewer-majority signal",
        "Grouped bars count papers where reviewer-majority accept became final reject, and reviewer-majority reject became final accept. Dark labels show unanimous-reviewer strong overrides.",
    )
    x0, x1 = left, right - 190
    y_step = (bottom - top) / len(rows)
    colors = {"accept_to_reject": "#b94a48", "reject_to_accept": "#3478a6"}
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        value = int(max_total * tick)
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 18, f"{value}", size=11, color="#6b7280", anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * y_step + 8
        parts.append(svg_text(28, y + 28, row["venue"], size=13, weight="600"))
        values = [
            ("accept_to_reject", row["majority_accept_to_reject"], row["all_accept_to_reject"]),
            ("reject_to_accept", row["majority_reject_to_accept"], row["all_reject_to_accept"]),
        ]
        for j, (key, value, strong) in enumerate(values):
            yy = y + j * 22
            w = (x1 - x0) * value / max_total if max_total else 0
            parts.append(f'<rect x="{x0}" y="{yy}" width="{w:.1f}" height="15" rx="2" fill="{colors[key]}"/>')
            label = f"{value} total; {strong} unanimous"
            parts.append(svg_text(x0 + w + 8, yy + 12, label, size=11, color="#374151"))
    legend_x = right - 168
    legend = [("accept->reject", colors["accept_to_reject"]), ("reject->accept", colors["reject_to_accept"])]
    for j, (name, color) in enumerate(legend):
        yy = top + 14 + j * 26
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="14" height="14" fill="{color}"/>')
        parts.append(svg_text(legend_x + 20, yy + 12, name, size=12))
    parts.append(svg_text(28, height - 16, "Override = final accept/reject disagrees with reviewer-majority signal. This is a public-data proxy, not private AC intent.", size=11, color="#6b7280"))
    save_svg(path, parts)
    return path


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = (len(values) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - idx) + values[hi] * (idx - lo)


def plot_score_overlap(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "03_score_overlap_iclr.svg"
    years = ["ICLR 2024", "ICLR 2025", "ICLR 2026"]
    data = {}
    for venue in years:
        for decision in ["accept", "reject"]:
            xs = [
                row["weighted_mean"]
                for row in meta_rows
                if row["venue"] == venue and row["decision"] == decision and isinstance(row.get("weighted_mean"), float)
            ]
            data[(venue, decision)] = xs
    width, height = 980, 520
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "ICLR score distributions overlap near the decision boundary",
        "Box-and-whisker marks show confidence-weighted reviewer scores by final decision. The vertical line is the simple threshold 6; overlap is where AC judgment has room to matter.",
    )
    x0, x1 = left, right - 30
    def sx(value: float) -> float:
        return x0 + (x1 - x0) * value / 10.0
    for tick in range(0, 11, 2):
        x = sx(tick)
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 18, str(tick), size=11, color="#6b7280", anchor="middle"))
    parts.append(f'<line x1="{sx(6):.1f}" x2="{sx(6):.1f}" y1="{top}" y2="{bottom}" stroke="#111827" stroke-width="2" stroke-dasharray="4 4"/>')
    parts.append(svg_text(sx(6) + 6, top + 12, "threshold 6", size=11, color="#111827"))
    colors = {"accept": "#3478a6", "reject": "#b94a48"}
    y_step = (bottom - top) / 6
    idx = 0
    for venue in years:
        parts.append(svg_text(28, top + idx * y_step + 37, venue, size=13, weight="700"))
        for decision in ["accept", "reject"]:
            xs = data[(venue, decision)]
            y = top + idx * y_step + 24
            idx += 1
            if not xs:
                continue
            p10, p25, p50, p75, p90 = [percentile(xs, q) for q in [0.1, 0.25, 0.5, 0.75, 0.9]]
            parts.append(svg_text(110, y + 4, decision, size=12, color=colors[decision], weight="600"))
            parts.append(f'<line x1="{sx(p10):.1f}" x2="{sx(p90):.1f}" y1="{y}" y2="{y}" stroke="{colors[decision]}" stroke-width="2"/>')
            parts.append(f'<rect x="{sx(p25):.1f}" y="{y-10}" width="{sx(p75)-sx(p25):.1f}" height="20" fill="{colors[decision]}" opacity="0.25" stroke="{colors[decision]}"/>')
            parts.append(f'<line x1="{sx(p50):.1f}" x2="{sx(p50):.1f}" y1="{y-13}" y2="{y+13}" stroke="{colors[decision]}" stroke-width="3"/>')
            parts.append(svg_text(sx(p90) + 6, y + 4, f"n={len(xs)}, median={p50:.2f}", size=11, color="#374151"))
    parts.append(svg_text(28, height - 16, "Source: public ICLR OpenReview notes; withdrawn and desk-reject papers omitted.", size=11, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_rationale_availability(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "04_public_rationale_availability.svg"
    rows = []
    for venue in ["ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"]:
        subset = [r for r in meta_rows if r["venue"] == venue and r["override_type"] in {"accept_to_reject", "reject_to_accept"}]
        if not subset:
            continue
        any_rationale = [r for r in subset if r["has_public_meta_review"] or r["has_public_decision_comment"]]
        with_meta = [r for r in subset if r["has_public_meta_review"]]
        med_words = median([r["public_rationale_word_count"] for r in any_rationale]) if any_rationale else 0
        rows.append((venue, len(subset), len(with_meta) / len(subset), len(any_rationale) / len(subset), med_words))
    width, height = 980, 450
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Do public override cases expose an AC/PC rationale?",
        "Bars show the share of majority-signal overrides with a public meta-review and with any public rationale. Labels show median public-rationale length when a rationale exists.",
    )
    x0, x1 = left, right - 190
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 18, f"{int(tick*100)}%", size=11, color="#6b7280", anchor="middle"))
    for i, (venue, n, meta_share, any_share, med_words) in enumerate(rows):
        y = top + i * y_step + 12
        parts.append(svg_text(28, y + 24, venue, size=13, weight="600"))
        for j, (label, share, color) in enumerate([
            ("public meta-review", meta_share, "#2f6f73"),
            ("any public rationale", any_share, "#d58c2a"),
        ]):
            yy = y + j * 21
            if label == "public meta-review" and not venue.startswith("ICLR"):
                parts.append(f'<rect x="{x0}" y="{yy}" width="{x1 - x0:.1f}" height="15" rx="2" fill="#e5e7eb"/>')
                parts.append(svg_text(x0 + 8, yy + 12, "n/a: no comparable public meta-review field", size=11, color="#374151"))
                continue
            w = (x1 - x0) * share
            parts.append(f'<rect x="{x0}" y="{yy}" width="{w:.1f}" height="15" rx="2" fill="{color}"/>')
            parts.append(svg_text(x0 + w + 8, yy + 12, f"{share*100:.0f}% ({label})", size=11, color="#374151"))
        parts.append(svg_text(right - 170, y + 22, f"n={n}; median words={med_words:.0f}", size=12, color="#374151"))
    parts.append(svg_text(28, height - 16, "Absence of public rationale is not proof of absent private deliberation; it is a transparency gap.", size=11, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_theme_frequency(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "05_iclr_override_reason_themes.svg"
    subset = [
        row
        for row in meta_rows
        if row["venue"].startswith("ICLR") and row["override_type"] in {"accept_to_reject", "reject_to_accept"} and row["has_public_meta_review"]
    ]
    directions = ["accept_to_reject", "reject_to_accept"]
    rows = []
    for theme, _ in THEMES:
        values = []
        for direction in directions:
            denom = [row for row in subset if row["override_type"] == direction]
            pct = sum(1 for row in denom if row.get(f"theme_{theme}")) / len(denom) if denom else 0
            values.append(pct)
        rows.append((theme, values[0], values[1]))
    width, height = 1120, 730
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "What reasons appear in public ICLR override meta-reviews?",
        "Regex-coded themes over public ICLR meta-review text. Bars are percentages within each override direction; one meta-review can mention multiple themes.",
    )
    x0, x1 = left + 105, right - 165
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, f"{int(tick*100)}%", size=13, color="#6b7280", anchor="middle"))
    for i, (theme, down, up) in enumerate(rows):
        y = top + i * y_step + 8
        parts.append(svg_text(28, y + 25, theme, size=17, weight="600"))
        for j, (value, color) in enumerate([(down, "#b94a48"), (up, "#3478a6")]):
            yy = y + j * 22
            w = (x1 - x0) * value
            parts.append(f'<rect x="{x0}" y="{yy}" width="{w:.1f}" height="16" rx="2" fill="{color}"/>')
            parts.append(svg_text(x0 + w + 8, yy + 14, f"{value*100:.0f}%", size=13, color="#374151"))
    legend_x = right - 130
    for j, (label, color) in enumerate([("accept->reject", "#b94a48"), ("reject->accept", "#3478a6")]):
        yy = top + 10 + j * 24
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="14" height="14" fill="{color}"/>')
        parts.append(svg_text(legend_x + 21, yy + 12, label, size=13))
    parts.append(svg_text(28, height - 16, "Theme coding is reproducible and intentionally coarse; it detects public evidence, not private AC intent.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z][a-z0-9_]{2,}", text.lower())
        if token not in STOPWORDS and "_" not in token and not token.startswith("reviewer")
    ]


def cluster_override_reasons(meta_rows: list[dict[str, Any]], k: int = 7) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs = [
        row
        for row in meta_rows
        if row["venue"].startswith("ICLR")
        and row["override_type"] in {"accept_to_reject", "reject_to_accept"}
        and row["meta_word_count"] >= 30
    ]
    if len(docs) < k:
        return [], []
    tokenized = [tokenize(row["meta_text"]) for row in docs]
    df = Counter()
    for tokens in tokenized:
        df.update(set(tokens))
    vocab = [word for word, count in df.most_common(700) if count >= 5]
    index = {word: i for i, word in enumerate(vocab)}
    matrix = np.zeros((len(docs), len(vocab)), dtype=float)
    for i, tokens in enumerate(tokenized):
        tf = Counter(token for token in tokens if token in index)
        for token, count in tf.items():
            matrix[i, index[token]] = count
    idf = np.log((1 + len(docs)) / (1 + np.array([df[word] for word in vocab]))) + 1
    matrix *= idf
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1
    matrix = matrix / norms[:, None]
    random.seed(11)
    np.random.seed(11)
    init_indices = np.linspace(0, len(docs) - 1, k, dtype=int)
    centers = matrix[init_indices].copy()
    labels = np.zeros(len(docs), dtype=int)
    for _ in range(40):
        distances = 1 - matrix @ centers.T
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster_id in range(k):
            members = matrix[labels == cluster_id]
            if len(members):
                center = members.mean(axis=0)
                norm = np.linalg.norm(center)
                centers[cluster_id] = center / norm if norm else center
    cluster_rows = []
    doc_rows = []
    for cluster_id in range(k):
        members = [doc for doc, label in zip(docs, labels) if label == cluster_id]
        if not members:
            continue
        centroid = matrix[labels == cluster_id].mean(axis=0)
        top_terms = [vocab[i] for i in centroid.argsort()[-10:][::-1]]
        theme_counts = Counter()
        for member in members:
            for theme, _ in THEMES:
                if member.get(f"theme_{theme}"):
                    theme_counts[theme] += 1
        label = auto_cluster_label(top_terms, theme_counts)
        counts = Counter(member["override_type"] for member in members)
        cluster_rows.append(
            {
                "cluster_id": cluster_id,
                "cluster_label": label,
                "top_terms": ", ".join(top_terms[:8]),
                "n": len(members),
                "accept_to_reject": counts["accept_to_reject"],
                "reject_to_accept": counts["reject_to_accept"],
                "top_theme": theme_counts.most_common(1)[0][0] if theme_counts else "",
            }
        )
        for member in members:
            doc_rows.append(
                {
                    "paper_id": member["paper_id"],
                    "venue": member["venue"],
                    "title": member["title"],
                    "override_type": member["override_type"],
                    "cluster_id": cluster_id,
                    "cluster_label": label,
                }
            )
    cluster_rows.sort(key=lambda row: row["n"], reverse=True)
    return cluster_rows, doc_rows


def auto_cluster_label(top_terms: list[str], theme_counts: Counter[str]) -> str:
    joined = " ".join(top_terms)
    if theme_counts:
        primary = theme_counts.most_common(1)[0][0]
        if primary == "Evidence / baselines" and re.search(r"benchmark|dataset|evaluation|baseline|ablation", joined):
            return "Benchmark and evaluation adequacy"
        if primary == "Novelty / related work" and re.search(r"novel|related|prior|incremental|contribution", joined):
            return "Novelty and related-work positioning"
        if primary == "Correctness / theory" or re.search(r"proof|theory|assumption|theorem|lemma|bound", joined):
            return "Correctness and theoretical support"
        if primary == "Unresolved rebuttal" or re.search(r"response|rebuttal|unresolved|outstanding", joined):
            return "Rebuttal did not resolve concerns"
        if primary == "Calibration / review quality" or re.search(r"calibration|positive|negative|disagreement", joined):
            return "Score calibration and reviewer disagreement"
        if primary == "Presentation / clarity" or re.search(r"clarity|writing|presentation|readability", joined):
            return "Presentation and clarity"
        return primary
    return "Mixed AC synthesis reasons"


def plot_reason_clusters(cluster_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "06_meta_review_reason_clusters.svg"
    rows = cluster_rows[:8]
    max_total = max((row["n"] for row in rows), default=1)
    width, height = 1220, 1020
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Unsupervised clusters of public ICLR override rationales",
        "TF-IDF k-means over public ICLR override meta-reviews. Cluster labels are assigned from top terms; stacked bars split accept->reject and reject->accept cases.",
    )
    x0, x1 = 455, right - 225
    y_step = (bottom - top) / max(1, len(rows))
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        value = int(max_total * tick)
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, f"{value}", size=13, color="#6b7280", anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * y_step + 12
        label_svg, _ = wrap_svg_text(28, y + 4, row["cluster_label"], max_chars=34, size=20, color="#111827")
        parts.append(label_svg)
        term_svg, _ = wrap_svg_text(28, y + 58, f"terms: {row['top_terms']}", max_chars=48, size=15, color="#6b7280")
        parts.append(term_svg)
        down = int(row["accept_to_reject"])
        up = int(row["reject_to_accept"])
        w_down = (x1 - x0) * down / max_total
        w_up = (x1 - x0) * up / max_total
        parts.append(f'<rect x="{x0}" y="{y}" width="{w_down:.1f}" height="27" rx="2" fill="#b94a48"/>')
        parts.append(f'<rect x="{x0 + w_down:.1f}" y="{y}" width="{w_up:.1f}" height="27" rx="2" fill="#3478a6"/>')
        parts.append(svg_text(x0 + w_down + w_up + 10, y + 20, f"n={row['n']}", size=15))
    legend_x = right - 135
    for j, (label, color) in enumerate([("accept->reject", "#b94a48"), ("reject->accept", "#3478a6")]):
        yy = top + 12 + j * 28
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="15" height="15" fill="{color}"/>')
        parts.append(svg_text(legend_x + 22, yy + 13, label, size=15))
    parts.append(svg_text(28, height - 16, "Only public ICLR override meta-reviews with 30+ words are clustered; no author/private discussion text is used.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_guideline_evidence(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "07_guideline_evidence_scorecard.svg"
    iclr = [row for row in meta_rows if row["venue"].startswith("ICLR") and row["decision"] in {"accept", "reject"} and row["n_scored_reviews"] >= 2]
    groups = {
        "Aligned decisions": [row for row in iclr if row["override_type"] == "aligned"],
        "Override decisions": [row for row in iclr if row["override_type"] in {"accept_to_reject", "reject_to_accept"}],
        "Unanimous overrides": [row for row in iclr if row["strong_override"]],
    }
    feature_keys = [
        ("feature_60_words", "60+ words"),
        ("feature_mentions_reviews", "Mentions reviews"),
        ("feature_mentions_rebuttal", "Rebuttal/discussion"),
        ("feature_strengths_weaknesses", "Strengths+weaknesses"),
        ("feature_decision_recommendation", "Decision/recommendation"),
        ("feature_causal_justification", "Causal justification"),
    ]
    width, height = 1180, 650
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Do public ICLR meta-reviews show evidence of guideline-like behavior?",
        "Heuristic public-evidence checks inspired by AC guidance: synthesize reviews, discuss rebuttal/discussion, justify decisions, and write enough explanation. This is not a private compliance audit.",
    )
    x0, x1 = 295, right - 225
    y_step = (bottom - top) / len(feature_keys)
    colors = ["#2f6f73", "#d58c2a", "#7158a8"]
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, f"{int(tick*100)}%", size=13, color="#6b7280", anchor="middle"))
    for i, (key, label) in enumerate(feature_keys):
        y = top + i * y_step + 12
        parts.append(svg_text(28, y + 27, label, size=15, weight="600"))
        for j, (group, rows) in enumerate(groups.items()):
            pct = sum(1 for row in rows if row.get(key)) / len(rows) if rows else 0
            yy = y + j * 21
            w = (x1 - x0) * pct
            parts.append(f'<rect x="{x0}" y="{yy}" width="{w:.1f}" height="15" rx="2" fill="{colors[j]}"/>')
            parts.append(svg_text(x0 + w + 8, yy + 12, f"{pct*100:.0f}%", size=12, color="#374151"))
    legend_x = right - 210
    for j, (group, rows) in enumerate(groups.items()):
        yy = top + 10 + j * 28
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="15" height="15" fill="{colors[j]}"/>')
        parts.append(svg_text(legend_x + 22, yy + 13, f"{group} (n={len(rows)})", size=12))
    parts.append(svg_text(28, height - 16, "Guideline evidence = public text signals; private AC/SAC deliberation may be better or worse than what is public.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_unanimous_override_rationale(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "08_unanimous_override_rationale.svg"
    rows = []
    for venue in ["ICLR 2024", "ICLR 2025", "ICLR 2026"]:
        subset = [row for row in meta_rows if row["venue"] == venue and row["strong_override"]]
        if not subset:
            continue
        robust = [
            row
            for row in subset
            if row["has_public_meta_review"]
            and row["meta_word_count"] >= 150
            and row["feature_mentions_reviews"]
            and row["feature_causal_justification"]
        ]
        rows.append((venue, len(subset), len(robust) / len(subset)))
    width, height = 880, 410
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "When all reviewers point one way, is the public override heavily justified?",
        "ICLR-only comparable public meta-review test: 150+ words, mentions reviews, and uses causal concern/issue language.",
    )
    x0, x1 = left, right - 120
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 18, f"{int(tick*100)}%", size=11, color="#6b7280", anchor="middle"))
    for i, (venue, n, share) in enumerate(rows):
        y = top + i * y_step + 18
        parts.append(svg_text(28, y + 12, venue, size=13, weight="600"))
        w = (x1 - x0) * share
        parts.append(f'<rect x="{x0}" y="{y}" width="{w:.1f}" height="18" rx="2" fill="#7158a8"/>')
        parts.append(svg_text(x0 + w + 8, y + 14, f"{share*100:.0f}% of {n} unanimous overrides", size=12))
    parts.append(svg_text(28, height - 16, "ICML/NeurIPS omitted here because their public decision-comment surfaces are not comparable meta-review fields.", size=11, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_three_accept_vote_fate(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "10_three_accept_votes_fate.svg"
    rows = []
    for venue in ["ICLR 2024", "ICLR 2025", "ICLR 2026", "ICML 2025", "NeurIPS 2025"]:
        subset = [
            row
            for row in meta_rows
            if row["venue"] == venue and row["decision"] in {"accept", "reject"} and row["accept_votes"] >= 3
        ]
        if not subset:
            continue
        rejected = sum(1 for row in subset if row["decision"] == "reject")
        accepted = sum(1 for row in subset if row["decision"] == "accept")
        with_rationale = sum(
            1
            for row in subset
            if row["decision"] == "reject" and (row["has_public_meta_review"] or row["has_public_decision_comment"])
        )
        rows.append((venue, accepted, rejected, with_rationale, len(subset)))
    width, height = 1180, 560
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "What happens to papers with at least three accept-leaning reviews?",
        "This directly probes the 3-accept argument: among papers with 3+ reviewer accept votes, how many are still rejected? Labels show how many such rejects expose any public rationale.",
    )
    max_total = max(total for *_, total in rows)
    x0, x1 = 250, right - 250
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        value = int(max_total * tick)
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, str(value), size=13, color="#6b7280", anchor="middle"))
    for i, (venue, accepted, rejected, with_rationale, total) in enumerate(rows):
        y = top + i * y_step + 18
        parts.append(svg_text(28, y + 16, venue, size=15, weight="700"))
        w_acc = (x1 - x0) * accepted / max_total
        w_rej = (x1 - x0) * rejected / max_total
        parts.append(f'<rect x="{x0}" y="{y}" width="{w_acc:.1f}" height="22" rx="2" fill="#3478a6"/>')
        parts.append(f'<rect x="{x0 + w_acc:.1f}" y="{y}" width="{w_rej:.1f}" height="22" rx="2" fill="#b94a48"/>')
        pct_rej = rejected / total if total else 0
        parts.append(svg_text(x0 + w_acc + w_rej + 10, y + 17, f"{rejected}/{total} rejected ({pct_rej*100:.1f}%); rationale n={with_rationale}", size=12))
    legend_x = right - 205
    for j, (label, color) in enumerate([("final accept", "#3478a6"), ("final reject", "#b94a48")]):
        yy = top + 10 + j * 28
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="15" height="15" fill="{color}"/>')
        parts.append(svg_text(legend_x + 22, yy + 13, label, size=13))
    parts.append(svg_text(28, height - 16, "Accept vote uses venue-specific thresholds: ICLR=6, ICML=3, NeurIPS=4. Public samples differ by venue.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_three_accept_capacity_load(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "12_three_accept_capacity_load.svg"
    rows = [
        row
        for row in acceptance_counterfactual_rows(meta_rows)
        if row["official_accepted"] and row["three_plus_accept_vote_papers"]
    ]
    max_total = max(
        max(int(row["official_accepted"]), int(row["three_plus_accept_vote_papers"]))
        for row in rows
    )
    width, height = 1180, 640
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Do 3+ accept-vote papers fit inside the official accept budget?",
        "Counterfactual load test inspired by the 3-accept critique: if every paper with at least three accept-leaning public reviews were accepted first, how much of the official accept budget would they consume?",
    )
    x0, x1 = 275, right - 240
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        value = int(max_total * tick)
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, f"{value}", size=13, color="#6b7280", anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * y_step + 18
        venue = row["venue"]
        slots = int(row["official_accepted"])
        three_total = int(row["three_plus_accept_vote_papers"])
        three_accepted = int(row["three_plus_accept_vote_accepted"])
        three_rejected = int(row["three_plus_accept_vote_rejected"])
        load = float(row["three_plus_slot_load"])
        parts.append(svg_text(28, y + 17, venue, size=16, weight="700"))
        w_slots = (x1 - x0) * slots / max_total
        w_acc = (x1 - x0) * three_accepted / max_total
        w_rej = (x1 - x0) * three_rejected / max_total
        parts.append(f'<rect x="{x0}" y="{y - 5}" width="{w_slots:.1f}" height="30" rx="3" fill="#eef2f7" stroke="#9ca3af"/>')
        parts.append(f'<rect x="{x0}" y="{y}" width="{w_acc:.1f}" height="20" rx="2" fill="#3478a6"/>')
        parts.append(f'<rect x="{x0 + w_acc:.1f}" y="{y}" width="{w_rej:.1f}" height="20" rx="2" fill="#b94a48"/>')
        label = f"3+ vote load {three_total}/{slots} slots ({load*100:.0f}%)"
        if load > 1:
            label += f"; short by {three_total - slots}"
        parts.append(svg_text(x0, y + 44, label, size=13, color="#111827"))
    legend_x = right - 230
    legend = [
        ("official accept slots", "#eef2f7"),
        ("3+ vote final accept", "#3478a6"),
        ("3+ vote final reject", "#b94a48"),
    ]
    for j, (label, color) in enumerate(legend):
        yy = top + 10 + j * 28
        stroke = ' stroke="#9ca3af"' if color == "#eef2f7" else ""
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="15" height="15" fill="{color}"{stroke}/>')
        parts.append(svg_text(legend_x + 22, yy + 13, label, size=13))
    parts.append(svg_text(28, height - 18, "ICML/NeurIPS public rejected samples are incomplete; treat their rejected 3+ counts as public lower bounds, not full-conference estimates.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_three_accept_rejection_decomposition(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "13_three_accept_rejection_decomposition.svg"
    rows = [
        row
        for row in acceptance_counterfactual_rows(meta_rows)
        if row["official_accepted"] and row["three_plus_accept_vote_rejected"]
    ]
    max_total = max(int(row["three_plus_accept_vote_rejected"]) for row in rows)
    width, height = 1180, 640
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "How much of 3+ accept-vote rejection is simple capacity pressure?",
        "A conservative decomposition: capacity arithmetic can explain at most the shortfall between 3+ accept-vote papers and official accept slots. The remaining public cases require substantive AC/PC rationale.",
    )
    x0, x1 = 275, right - 260
    y_step = (bottom - top) / len(rows)
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        value = int(max_total * tick)
        x = x0 + (x1 - x0) * tick
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, bottom + 22, f"{value}", size=13, color="#6b7280", anchor="middle"))
    for i, row in enumerate(rows):
        y = top + i * y_step + 20
        venue = row["venue"]
        rejected = int(row["three_plus_accept_vote_rejected"])
        capacity = int(row["capacity_shortfall_if_all_three_plus_accepted"] or 0)
        rationale = int(row["three_plus_rejections_not_forced_by_capacity"] or 0)
        capacity = min(capacity, rejected)
        rationale = max(0, rejected - capacity)
        parts.append(svg_text(28, y + 17, venue, size=16, weight="700"))
        w_cap = (x1 - x0) * capacity / max_total if max_total else 0
        w_rat = (x1 - x0) * rationale / max_total if max_total else 0
        parts.append(f'<rect x="{x0}" y="{y}" width="{w_cap:.1f}" height="22" rx="2" fill="#d58c2a"/>')
        parts.append(f'<rect x="{x0 + w_cap:.1f}" y="{y}" width="{w_rat:.1f}" height="22" rx="2" fill="#7158a8"/>')
        parts.append(svg_text(x0, y + 44, f"{rejected} rejected; capacity <= {capacity}; rationale >= {rationale}", size=13))
    legend_x = right - 246
    for j, (label, color) in enumerate([("capacity shortfall upper bound", "#d58c2a"), ("requires public rationale", "#7158a8")]):
        yy = top + 10 + j * 28
        parts.append(f'<rect x="{legend_x}" y="{yy}" width="15" height="15" fill="{color}"/>')
        parts.append(svg_text(legend_x + 22, yy + 13, label, size=13))
    parts.append(svg_text(28, height - 18, "This is not a causal claim about individual papers; it is a slot-count sanity check for the 25% acceptance-rate hypothesis.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def plot_example_case(meta_rows: list[dict[str, Any]]) -> Path:
    path = PLOT_DIR / "11_case_iJ4i5HE5ER.svg"
    row = next((r for r in meta_rows if r["paper_id"] == "iJ4i5HE5ER"), None)
    width, height = 1120, 560
    parts, left, right, top, bottom = svg_frame(
        width,
        height,
        "Case diagnostic: SophiaVL-R1 (NeurIPS 2025, iJ4i5HE5ER)",
        "This example has a reviewer-majority accept signal and a final reject in the public data. The key quantitative fact is the absence of public AC/meta-review rationale.",
    )
    if not row:
        parts.append(svg_text(40, top + 40, "Case not found in cached public OpenReview rows.", size=16))
        save_svg(path, parts)
        return path
    scores = [float(x) for x in row["scores"].split()] if row["scores"] else []
    threshold = float(row["threshold"] or 4)
    x0, x1 = 180, 730
    y0 = top + 45
    parts.append(svg_text(40, y0 - 14, "Reviewer ratings", size=16, weight="700"))
    for tick in range(1, 7):
        x = x0 + (x1 - x0) * (tick - 1) / 5
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0}" y2="{y0 + 110}" stroke="#e5e7eb"/>')
        parts.append(svg_text(x, y0 + 132, str(tick), size=13, color="#6b7280", anchor="middle"))
    tx = x0 + (x1 - x0) * (threshold - 1) / 5
    parts.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{y0}" y2="{y0 + 110}" stroke="#111827" stroke-dasharray="4 4" stroke-width="2"/>')
    parts.append(svg_text(tx + 7, y0 + 13, f"accept threshold {threshold:g}", size=13, color="#111827"))
    for i, score in enumerate(scores):
        y = y0 + 14 + i * 22
        w = (x1 - x0) * (score - 1) / 5
        color = "#3478a6" if score >= threshold else "#b94a48"
        parts.append(f'<rect x="{x0}" y="{y}" width="{w:.1f}" height="17" rx="2" fill="{color}"/>')
        parts.append(svg_text(x0 + w + 10, y + 14, f"R{i+1}: {score:g}", size=13))
    facts = [
        ("Final public decision", row["decision"].upper()),
        ("Reviewer majority", row["reviewer_majority"]),
        ("Weighted mean", f"{row['weighted_mean']:.2f}"),
        ("Public meta-review?", "yes" if row["has_public_meta_review"] else "no"),
        ("Decision comment words", str(row["decision_word_count"])),
        ("Clusterable meta-review?", "no" if not row["has_public_meta_review"] else "yes"),
    ]
    box_x, box_y = 780, top + 36
    parts.append(f'<rect x="{box_x}" y="{box_y}" width="300" height="214" rx="6" fill="#ffffff" stroke="#d1d5db"/>')
    for i, (label, value) in enumerate(facts):
        y = box_y + 28 + i * 31
        parts.append(svg_text(box_x + 16, y, label, size=13, color="#6b7280"))
        parts.append(svg_text(box_x + 194, y, value, size=14, weight="700", color="#111827"))
    note, _ = wrap_svg_text(
        40,
        y0 + 175,
        "Interpretation: this is a mixed transparency case. The public decision comment is substantive and names empirical/significance concerns, but there is no separate public meta-review, so it is not included in the ICLR meta-review clustering and is harder to audit against AC meta-review guidelines.",
        max_chars=88,
        size=14,
        color="#374151",
    )
    parts.append(note)
    parts.append(svg_text(40, height - 16, "Source: public NeurIPS 2025 OpenReview forum iJ4i5HE5ER.", size=12, color="#6b7280"))
    save_svg(path, parts)
    return path


def acceptance_counterfactual_rows(meta_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_by_venue = defaultdict(list)
    for row in meta_rows:
        public_by_venue[row["venue"]].append(row)
    rows = []
    for item in ACCEPTANCE_BENCHMARKS:
        subset = public_by_venue[item["venue"]]
        accepted = sum(1 for row in subset if row["decision"] == "accept")
        rejected = sum(1 for row in subset if row["decision"] == "reject")
        desk = sum(1 for row in subset if row["decision"] == "desk_reject")
        withdrawn = sum(1 for row in subset if row["decision"] == "withdrawn")
        denom = accepted + rejected + desk
        three_plus = [
            row for row in subset if row["decision"] in {"accept", "reject"} and row.get("accept_votes", 0) >= 3
        ]
        three_plus_rejected = sum(1 for row in three_plus if row["decision"] == "reject")
        three_plus_accepted = len(three_plus) - three_plus_rejected
        official_slots = item.get("accepted")
        official_submitted = item.get("submitted")
        capacity_shortfall = ""
        rejected_not_forced_by_capacity = ""
        lower_vote_accepts = ""
        three_plus_slot_load = ""
        accepted_three_plus_slot_share = ""
        non_three_plus_accept_slot_share = ""
        if official_slots:
            capacity_shortfall = max(0, len(three_plus) - official_slots)
            rejected_not_forced_by_capacity = max(0, three_plus_rejected - capacity_shortfall)
            lower_vote_accepts = max(0, official_slots - three_plus_accepted)
            three_plus_slot_load = len(three_plus) / official_slots
            accepted_three_plus_slot_share = three_plus_accepted / official_slots
            non_three_plus_accept_slot_share = lower_vote_accepts / official_slots
        sample_note = "full public ICLR decision surface" if item["venue"].startswith("ICLR") else "public sample / official-rate context"
        if item["venue"] in {"AISTATS 2026", "RLC 2025", "AAAI 2025"}:
            sample_note = "official-rate context only; public review scores unavailable"
        rows.append(
            {
                "venue": item["venue"],
                "official_submitted": official_submitted or "",
                "official_accepted": official_slots or "",
                "official_rate": item["rate"],
                "delta_accepts_vs_25pct": (
                    round(official_slots - official_submitted * 0.25)
                    if official_submitted and official_slots
                    else ""
                ),
                "public_accepted": accepted,
                "public_rejected": rejected,
                "public_desk_rejected": desk,
                "public_withdrawn": withdrawn,
                "public_accept_rate_all": accepted / len(subset) if subset else "",
                "public_accept_rate_post_withdrawal": accepted / denom if denom else "",
                "three_plus_accept_vote_papers": len(three_plus),
                "three_plus_accept_vote_accepted": three_plus_accepted,
                "three_plus_accept_vote_rejected": three_plus_rejected,
                "three_plus_accept_vote_reject_share": three_plus_rejected / len(three_plus) if three_plus else "",
                "three_plus_slot_load": three_plus_slot_load,
                "capacity_shortfall_if_all_three_plus_accepted": capacity_shortfall,
                "three_plus_rejections_not_forced_by_capacity": rejected_not_forced_by_capacity,
                "accepted_papers_with_fewer_than_three_accept_votes": lower_vote_accepts,
                "accepted_three_plus_slot_share": accepted_three_plus_slot_share,
                "non_three_plus_accept_slot_share": non_three_plus_accept_slot_share,
                "sample_note": sample_note,
                "source_label": item["source_label"],
                "source_url": item["source_url"],
            }
        )
    return rows


def build_summaries(meta_rows: list[dict[str, Any]], cluster_rows: list[dict[str, Any]]) -> None:
    override_rows = [row for row in meta_rows if row["override_type"] in {"accept_to_reject", "reject_to_accept"}]
    theme_summary = []
    for venue_group, rows in {
        "ICLR all override meta-reviews": [
            row for row in override_rows if row["venue"].startswith("ICLR") and row["has_public_meta_review"]
        ],
        "All public override cases": override_rows,
    }.items():
        for theme, _ in THEMES:
            for direction in ["accept_to_reject", "reject_to_accept"]:
                denom = [row for row in rows if row["override_type"] == direction]
                count = sum(1 for row in denom if row.get(f"theme_{theme}"))
                theme_summary.append(
                    {
                        "group": venue_group,
                        "override_type": direction,
                        "theme": theme,
                        "count": count,
                        "denominator": len(denom),
                        "share": count / len(denom) if denom else "",
                    }
                )
    write_csv(DATA_DIR / "meta_reason_theme_summary.csv", theme_summary, ["group", "override_type", "theme", "count", "denominator", "share"])
    write_csv(DATA_DIR / "meta_reason_clusters.csv", cluster_rows, ["cluster_id", "cluster_label", "top_terms", "n", "accept_to_reject", "reject_to_accept", "top_theme"])

    compliance_rows = []
    for venue in sorted({row["venue"] for row in meta_rows}):
        subset = [row for row in meta_rows if row["venue"] == venue and row["decision"] in {"accept", "reject"} and row["n_scored_reviews"] >= 2]
        if not subset:
            continue
        overrides = [row for row in subset if row["override_type"] in {"accept_to_reject", "reject_to_accept"}]
        for group_name, rows in [("all_analyzable", subset), ("overrides", overrides)]:
            if not rows:
                continue
            compliance_rows.append(
                {
                    "venue": venue,
                    "group": group_name,
                    "n": len(rows),
                    "public_meta_share": sum(1 for row in rows if row["has_public_meta_review"]) / len(rows),
                    "any_rationale_share": sum(1 for row in rows if row["has_public_meta_review"] or row["has_public_decision_comment"]) / len(rows),
                    "median_meta_words": median([row["meta_word_count"] for row in rows]),
                    "mean_guideline_evidence_score": mean([row["guideline_evidence_score"] for row in rows]),
                    "feature_60_words_share": sum(1 for row in rows if row["feature_60_words"]) / len(rows),
                    "feature_rebuttal_share": sum(1 for row in rows if row["feature_mentions_rebuttal"]) / len(rows),
                    "feature_review_synthesis_share": sum(1 for row in rows if row["feature_mentions_reviews"]) / len(rows),
                }
            )
    write_csv(
        DATA_DIR / "guideline_public_evidence_summary.csv",
        compliance_rows,
        [
            "venue",
            "group",
            "n",
            "public_meta_share",
            "any_rationale_share",
            "median_meta_words",
            "mean_guideline_evidence_score",
            "feature_60_words_share",
            "feature_rebuttal_share",
            "feature_review_synthesis_share",
        ],
    )
    acceptance_rows = acceptance_counterfactual_rows(meta_rows)
    write_csv(
        DATA_DIR / "acceptance_budget_analysis.csv",
        acceptance_rows,
        [
            "venue",
            "official_submitted",
            "official_accepted",
            "official_rate",
            "delta_accepts_vs_25pct",
            "public_accepted",
            "public_rejected",
            "public_desk_rejected",
            "public_withdrawn",
            "public_accept_rate_all",
            "public_accept_rate_post_withdrawal",
            "three_plus_accept_vote_papers",
            "three_plus_accept_vote_accepted",
            "three_plus_accept_vote_rejected",
            "three_plus_accept_vote_reject_share",
            "three_plus_slot_load",
            "capacity_shortfall_if_all_three_plus_accepted",
            "three_plus_rejections_not_forced_by_capacity",
            "accepted_papers_with_fewer_than_three_accept_votes",
            "accepted_three_plus_slot_share",
            "non_three_plus_accept_slot_share",
            "sample_note",
            "source_label",
            "source_url",
        ],
    )


def enhance_markdown(plot_paths: list[Path], meta_rows: list[dict[str, Any]], cluster_rows: list[dict[str, Any]]) -> None:
    report_path = REPORT_DIR / "notion_blog_openreview_ac_overrides.md"
    text = report_path.read_text(encoding="utf-8")
    text = text.replace("_Trigger._", "_Inspired by._")
    text = text.replace("- Trigger tweet:", "- Tweet inspiration:")
    text = text.replace(
        f"- Tweet inspiration: [{ROY_TWEET_URL}]({ROY_TWEET_URL})",
        f"- Tweet inspiration on ACs vs paper weights: [{ROY_TWEET_URL}]({ROY_TWEET_URL})",
    )
    text = text.replace(
        f"- Additional tweet inspiration on 3 accepts / acceptance-rate pressure: [{SARATH_TWEET_URL}]({SARATH_TWEET_URL})",
        f"- Tweet inspiration on 3 accepts / acceptance-rate pressure: [{SARATH_TWEET_URL}]({SARATH_TWEET_URL})",
    )
    process_note = (
        "_Co-written with Codex._ This essay was developed with Codex as a research, coding, and editorial partner: "
        "fetching public OpenReview data, writing analysis scripts, building plots, packaging the Notion import, and tightening the narrative. "
        "The research question, interpretation, and final judgment remain human-directed; the quantitative claims are tied to local scripts, CSVs, and public sources rather than model memory.\n\n"
        "_Disclosure and non-affiliation._ I am not affiliated with, advising, collaborating with, or writing on behalf of any author of the papers named or qualitatively discussed in this post. None of my own ML papers appears in the qualitative case analysis, named override examples, or paper-level case readings; the named cases are used only because their OpenReview records are public and illustrate process patterns.\n\n"
    )
    opener = (
        "_Area chairs are not paper weights. But when AC judgment diverges from reviewer-score weighting, the reasoning has to be legible._ "
        "Dan Roy's one-line provocation, \"Area chairs <= paper weights,\" is the right starting point because it turns a familiar complaint "
        "into a measurable question: how far do final decisions move away from simple reviewer-score aggregation, and when is that movement "
        "evidence of judgment rather than opacity?\n\n"
        "This essay is both an audit and a guide to ACing. The audit measures how much reviewer-score weighting predicts public OpenReview "
        "decisions, then studies the cases where AC/PC judgment visibly overrides reviewer majority or unanimity. The guide asks what a good "
        "AC should do in exactly those boundary cases: audit review quality, make rebuttal discussion concrete, explain which evidence mattered, "
        "and leave a decision record that future authors, reviewers, and ACs can learn from.\n\n"
        "_The test._ If we aggregate reviewer scores with a simple confidence weighting, do area-chair/meta-review decisions mostly reduce to "
        "paper weights, or do ACs visibly add judgment?\n\n"
        "_Second inspiration._ Sarath Chandar's May 2, 2026 tweet sharpened the capacity question: what should we infer when a paper has "
        "three accept-leaning reviews but is rejected in a conference culture that often talks about roughly 25% acceptance? This pass treats "
        "that as a quantitative stress test, not as a rule that three accept scores should mechanically force acceptance.\n\n"
        "_Why this got more urgent._ Two newer X posts map accepted papers as global scoreboards: China Research Collective's ICLR 2026 "
        "institution/country treemap and Amit LeVi's fractional-author extension across NeurIPS, ICLR, and ICML 2025. They do not replace the "
        "ACs-vs-weights question; they raise its stakes. Top-conference accepts are read as career, institutional, and national capital, so "
        "thinly explained AC discretion is easily reduced to leaderboard narratives about where accepted papers cluster.\n\n"
        "The answer is neither a simple indictment of ACs nor a defense of unexplained judgment. Reviewer scores are strongly predictive where the full public "
        "decision surface is visible, especially at ICLR. But the public data also shows a nontrivial set of AC/PC overrides: papers with "
        "majority-positive reviews that are rejected, and papers with majority-negative reviews that are accepted. That override set is where "
        "the review system does its most human work. It is also where venues owe authors, reviewers, and future ACs the clearest explanations.\n\n"
        + process_note
    )
    text = re.sub(r"_Process inspiration\._.*?\n\n", "", text, flags=re.S)
    text = re.sub(
        r"(?s)# .+?\n\n.*?(?=## Claims and Evidence Map|## What Was Measured)",
        lambda match: f"# {BLOG_TITLE}\n\n" + opener,
        text,
        count=1,
    )
    conflict_bullet = (
        "- Conflict-of-interest constraint: I am not associated with any authors of the papers named or qualitatively discussed here, "
        "and my own ML papers do not appear in the qualitative case analysis."
    )
    if conflict_bullet not in text:
        text = text.replace(
            "- Ethical constraint: AC identities are not deanonymized. The report highlights public paper cases and anonymized meta-review behavior, not named ACs.",
            "- Ethical constraint: AC identities are not deanonymized. The report highlights public paper cases and anonymized meta-review behavior, not named ACs.\n"
            + conflict_bullet,
        )

    claims_map = """## Claims and Evidence Map

| Claim | Evidence used here | What this does not prove |
| --- | --- | --- |
| Reviewer scores carry real signal. | Point-biserial correlations, AUC, and threshold accuracy across public ICLR/ICML/NeurIPS samples. | That scores are sufficient, calibrated across areas, or more important than review text. |
| AC/PC discretion materially changes some outcomes. | Majority-signal override counts and strong unanimous-reviewer override counts. | That every override is good or bad; only that the override surface is large enough to audit. |
| Public rationale quality is the central governance variable. | Meta-review availability, rationale word-count features, rebuttal/review-synthesis markers, and case-level reason tags. | That private AC work was absent when public rationale is thin. |
| The rough 25% acceptance story is incomplete. | Official acceptance-rate comparison, post-withdrawal public decision pools, and 3+ accept-vote capacity counterfactuals. | That any paper with three accept-leaning reviews should automatically be accepted. |
| Accepted-paper leaderboards raise the stakes. | Public affiliation and country-distribution posts for ICLR/ICML/NeurIPS accepted papers. | That country or institution share explains any paper-level decision. |
| AC matching should privilege expertise and interest. | Borderline accept-to-reject cases with short or weakly structured public rationale, plus qualitative examples requiring domain judgment. | That text length proves low expertise or that every terse reject was wrong. |
| Better incentives should score service, not taste. | High-risk decision flags, missing-rationale patterns, and reciprocal-service precedents. | That we can objectively know the "right" decision after the fact. |

"""
    if "## Claims and Evidence Map" in text:
        text = re.sub(
            r"## Claims and Evidence Map\n.*?(?=\n## What Was Measured)",
            claims_map,
            text,
            flags=re.S,
        )
    else:
        text = text.replace("## What Was Measured", claims_map + "## What Was Measured", 1)

    coverage_and_results = build_venue_coverage_section() + build_quantitative_results_section()
    if "## Venue Coverage" in text:
        text = re.sub(
            r"## Venue Coverage\n.*?(?=\nImportant ICLR 2026 context:)",
            coverage_and_results,
            text,
            flags=re.S,
        )

    visual_section = build_visual_section(plot_paths, meta_rows, cluster_rows)
    if "## Visual Argument" in text:
        text = re.sub(
            r"## Visual Argument\n.*?(?=\n## (?:Where AC/PC Judgment Visibly Overrides Reviewers|Representative Override Cases))",
            visual_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    elif "## Visual Diagnostics Under the Stats" in text:
        text = re.sub(
            r"## Visual Diagnostics Under the Stats\n.*?(?=\n## Where AC/PC Judgment Visibly Overrides Reviewers)",
            visual_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    else:
        marker = "## Where AC/PC Judgment Visibly Overrides Reviewers"
        text = text.replace(marker, visual_section + "\n" + marker)

    override_case_section = build_override_case_section(meta_rows)
    if "## Representative Override Cases" in text:
        text = re.sub(
            r"## Representative Override Cases\n.*?(?=\n## Acceptance-Rate Pressure Readout)",
            lambda match: override_case_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    else:
        text = re.sub(
            r"## Where AC/PC Judgment Visibly Overrides Reviewers\n.*?(?=\n## Acceptance-Rate Pressure Readout)",
            lambda match: override_case_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )

    advisor_section = build_advisor_section(meta_rows, cluster_rows)
    if "## Acceptance-Rate Pressure Readout" in text:
        text = re.sub(
            r"## Acceptance-Rate Pressure Readout\n.*?(?=\n## Qualitative Reading of the Override Cases)",
            advisor_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    elif "## Guideline-Compliance Readout" in text:
        text = re.sub(
            r"## Guideline-Compliance Readout\n.*?(?=\n## Qualitative Reading of the Override Cases)",
            advisor_section.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    else:
        marker = "## Qualitative Reading of the Override Cases"
        text = text.replace(marker, advisor_section + "\n" + marker)

    if "## AI Collaboration Note" in text:
        text = re.sub(
            r"## AI Collaboration Note\n.*?(?=\n## Caveats)",
            "",
            text,
            flags=re.S,
        )
    anecdote_caveat = "- The RLC 2026 story is an anonymized personal anecdote, not part of the quantitative OpenReview aggregate analysis."
    if anecdote_caveat not in text:
        text = text.replace(
            "- This audit uses public OpenReview data only. It does not include private discussions, SAC/PC deliberations, confidential comments, desk-reject triage, or author-hidden rejected submissions.",
            "- This audit uses public OpenReview data only. It does not include private discussions, SAC/PC deliberations, confidential comments, desk-reject triage, or author-hidden rejected submissions.\n"
            + anecdote_caveat,
        )
    disclosure_caveats = [
        "- I am not associated with any authors of the papers named or qualitatively discussed in this blog.",
        "- None of my own ML papers appears in the qualitative case analysis, named override examples, or paper-level case readings.",
    ]
    for caveat in disclosure_caveats:
        if caveat not in text:
            text = text.replace(anecdote_caveat, caveat + "\n" + anecdote_caveat)

    qualitative = """## Qualitative Reading of the Override Cases

The most useful reading is not that overrides are bad. The useful reading is that overrides reveal where AC judgment is doing work. A high-quality override record explains the decisive concern, how reviewers were weighted, whether rebuttal changed anything, and why the final decision moved away from the simple score signal.

The low-feedback borderline subset is the warning sign. When an accept-to-reject case is near the threshold and the public rationale is short or lacks rebuttal/review-synthesis markers, outside readers cannot tell whether expert judgment happened or whether the system produced an under-explained reversal.

"""
    recommendations = """## Recommendations for Better Reviewing Incentives

1. Make AC bidding expertise- and interest-gated, with reassignment or co-AC support for weak matches.
2. Require a structured decision delta for reviewer-majority overrides, unanimous-reviewer overrides, and 3+ accept-vote rejects.
3. Track reviewer update quality after rebuttal, not just review submission timing.
4. Add SAC repair queues for missing or very short rationales before decisions are released.
5. Publish aggregate venue diagnostics on override rates and rationale completeness without naming ACs publicly.

"""
    caveats = """## Caveats

This is a public-record audit, not a private-process audit. Missing public evidence does not prove missing private AC work, and individual examples should not be read as allegations that a decision was wrong.

ICML 2025 and NeurIPS 2025 are public-sample analyses, not full rejected-paper pools. AISTATS 2026, RLC 2025, and AAAI 2025 are used only as process/context references because comparable public review-score and meta-review fields were not available.

I am not associated with any of the authors corresponding to papers discussed in this blog. My own ML papers do not appear in the qualitative analysis. The point is to improve process legibility, not to relitigate individual accept/reject outcomes.

"""
    text = re.sub(
        r"## Qualitative Reading of the Override Cases\n.*?(?=\n## Recommendations for Better Reviewing Incentives)",
        qualitative.rstrip() + "\n\n",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"## Recommendations for Better Reviewing Incentives\n.*?(?=\n## Caveats)",
        recommendations.rstrip() + "\n\n",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"## Caveats\n.*?(?=\n## Sources)",
        caveats.rstrip() + "\n\n",
        text,
        flags=re.S,
    )

    source_lines = [
        f"- Tweet inspiration on ACs vs paper weights: [{ROY_TWEET_URL}]({ROY_TWEET_URL})",
        f"- Tweet inspiration on 3 accepts / acceptance-rate pressure: [{SARATH_TWEET_URL}]({SARATH_TWEET_URL})",
        f"- X post on ICLR 2026 accepted-paper affiliation distribution: [{CRC_ICLR_2026_DISTRIBUTION_URL}]({CRC_ICLR_2026_DISTRIBUTION_URL})",
        f"- X post extending accepted-paper distribution to NeurIPS/ICLR/ICML 2025 with fractional author credit: [{AMIT_CONFERENCE_DISTRIBUTION_URL}]({AMIT_CONFERENCE_DISTRIBUTION_URL})",
        f"- LinkedIn inspiration on submission scale and lottery framing: [{AYAN_LINKEDIN_URL}]({AYAN_LINKEDIN_URL})",
        f"- Conceptual inspiration: Rich Sutton's The Bitter Lesson: [{BITTER_LESSON_URL}]({BITTER_LESSON_URL})",
        "- ICLR Area Chair guidance: [ICLR 2026 Area Chair Guide](https://iclr.cc/Conferences/2026/AreaChairGuide)",
        "- ICML Area Chair guidance: [ICML 2025 Area Chair Instructions](https://icml.cc/Conferences/2025/AreaChairInstructions)",
        "- NeurIPS Area Chair guidance: [NeurIPS 2025 AC Guidelines](https://nips.cc/Conferences/2025/AC-Guidelines)",
        f"- NeurIPS 2026 Main Track Handbook: [{NEURIPS_2026_HANDBOOK_URL}]({NEURIPS_2026_HANDBOOK_URL})",
        f"- NeurIPS 2026 AC pilot: [{NEURIPS_2026_AC_PILOT_URL}]({NEURIPS_2026_AC_PILOT_URL})",
        f"- NeurIPS 2026 Reviewing Guidelines: [{NEURIPS_2026_REVIEWING_GUIDELINES_URL}]({NEURIPS_2026_REVIEWING_GUIDELINES_URL})",
        "- AISTATS AC guidance: [AISTATS 2026 AC Guidelines](https://virtual.aistats.org/Conferences/2026/ACGuidelines)",
        "- AISTATS acceptance-rate context: [AISTATS 2026 Call for Papers](https://virtual.aistats.org/Conferences/2026/CallForPapers)",
        "- RLC process guidance: [RLC 2024 Review Process](https://rl-conference.cc/2024/review_process.html)",
        f"- RLC/RLJ 2026 submission process context: [{RLC_2026_SUBMISSION_URL}]({RLC_2026_SUBMISSION_URL})",
        "- RLC 2025 acceptance-rate context: [RIKEN AIP RLC 2025 acceptance note](https://aip.riken.jp/news/rlc2025/?lang=en)",
        f"- Reciprocal reviewing incentive reference: [ACL Rolling Review 2026 incentives]({ARR_2026_INCENTIVES_URL})",
        "- ICML 2025 acceptance-rate context: [RIKEN AIP ICML 2025 acceptance note](https://aip.riken.jp/news/icml2025/?lang=en)",
        "- NeurIPS 2025 acceptance-rate context: [RIKEN AIP NeurIPS 2025 acceptance note](https://aip.riken.jp/news/neurips2025/?lang=en)",
        "- AAAI 2025 acceptance-rate context: [RIKEN AIP AAAI-25 acceptance note](https://aip.riken.jp/news/202412_aaai25/)",
    ]
    for line in source_lines:
        if line not in text:
            text = text.replace("- OpenReview public API:", line + "\n- OpenReview public API:")
    if "## Sources" in text:
        before, sources = text.split("## Sources", 1)
        seen_source_lines = set()
        clean_sources = []
        for line in sources.splitlines():
            if line.startswith("- ") and "process inspiration" in line:
                continue
            if line.startswith("- ") and line in seen_source_lines:
                continue
            if line.startswith("- "):
                seen_source_lines.add(line)
            clean_sources.append(line)
        text = before + "## Sources" + "\n".join(clean_sources)
    reproducibility = """## Reproducibility Package

The local source package contains the analysis scripts, cached public-data CSVs, generated plots, and validation checks used for this post. The reproducibility boundary is deliberately narrow: the code supports the public-data claims in the essay, while the qualitative interpretation remains mine.

To audit the numbers, run `python3 scripts/validate_outputs.py` against the released package. To regenerate from cached public OpenReview rows, run `python3 scripts/enhance_openreview_report_with_plots.py`. A full public-data refresh can be run with `python3 scripts/analyze_openreview_ac_overrides.py` followed by the enhancement script; that path depends on the current public OpenReview API surface and may change as venues update visibility.

"""
    if "## Reproducibility Package" in text:
        text = re.sub(
            r"## Reproducibility Package\n.*?(?=\n## Caveats)",
            reproducibility.rstrip() + "\n\n",
            text,
            flags=re.S,
        )
    else:
        text = text.replace("\n## Caveats", "\n" + reproducibility + "## Caveats", 1)
    report_path.write_text(text, encoding="utf-8")


def replace_markdown_section(text: str, start: str, end: str, replacement: str) -> str:
    pattern = rf"{re.escape(start)}\n.*?(?=\n{re.escape(end)})"
    return re.sub(pattern, lambda match: replacement.rstrip() + "\n\n", text, flags=re.S)


def build_visual_section(plot_paths: list[Path], meta_rows: list[dict[str, Any]], cluster_rows: list[dict[str, Any]]) -> str:
    iclr_overrides = [row for row in meta_rows if row["venue"].startswith("ICLR") and row["override_type"] in {"accept_to_reject", "reject_to_accept"}]
    iclr_with_meta = [row for row in iclr_overrides if row["has_public_meta_review"]]
    total_clusters = sum(row["n"] for row in cluster_rows)
    return f"""## Visual Argument

The first thing to notice is that reviewer scores are not decorative. A simple confidence-weighted score ranks accepted papers above rejected papers surprisingly well, especially in ICLR 2024 and 2025. That is the part of the "paper weights" intuition that is basically right: if all we know is the public score vector, we already know a lot about the final outcome.

![Predictiveness metrics](plots/png/01_predictiveness_metrics.png)

But prediction is not the same as governance. The interesting cases are the ones where the final decision moves against the reviewer-majority signal. Those are not rare enough to dismiss as clerical noise. In ICLR 2024 and 2025 especially, hundreds of papers sit in the region where the AC/PC decision visibly changes the outcome relative to a simple majority rule.

![Override counts](plots/png/02_override_counts.png)

The reason this can happen is visible in the score distributions. Accepted and rejected ICLR papers separate in the aggregate, but they overlap around the threshold. That overlap is the real decision surface. On one side are papers with apparently positive scores but unresolved novelty, correctness, or evaluation problems. On the other are papers with mixed scores where the AC appears to have decided that the written concerns were either answerable or outweighed by the contribution.

![ICLR score overlap](plots/png/03_score_overlap_iclr.png)

This turns the question into a transparency question. When an AC overrides the reviewer-majority signal, do we get a public rationale strong enough to learn from? ICLR is relatively good here: public meta-reviews are exposed for the override cases. ICML and NeurIPS expose public decision comments in the sampled cases, but not separate public meta-reviews in the same way. AISTATS, RLC, and AAAI do not expose enough public review/meta-review structure for the same audit.

![Public rationale availability](plots/png/04_public_rationale_availability.png)

For ICLR, the public rationales can be coded into broad reasons. The dominant pattern is not mysterious: novelty and related work, evidence and baselines, calibration of reviewer scores, and unresolved rebuttal concerns show up repeatedly. This is important because it suggests AC discretion is often doing a real synthesis job, not merely enforcing a hidden quota.

![ICLR override reason themes](plots/png/05_iclr_override_reason_themes.png)

An unsupervised pass over the public ICLR override meta-reviews tells the same story in another way. The clusters are coarse, but they map to recognizable AC moves: benchmark adequacy, novelty positioning, unresolved rebuttal, theoretical support, and review-score calibration. The clustering should not replace reading individual cases; it is useful because it turns thousands of borderline decisions into a process map.

![Meta-review reason clusters](plots/png/06_meta_review_reason_clusters.png)

The guideline question is sharper. AC guides generally ask ACs to synthesize reviews, manage discussion, assess rebuttal, and justify decisions. Public ICLR meta-reviews often show evidence of this behavior, especially for override cases. The metric here is deliberately conservative: it measures public evidence of guideline-like behavior, not private compliance.

![Guideline evidence scorecard](plots/png/07_guideline_evidence_scorecard.png)

The hardest cases are unanimous-reviewer overrides. If all reviewers point one way and the AC/PC moves the other way, the public explanation should be unusually explicit. The data shows a mixed picture: many ICLR unanimous overrides have strong public rationale signals, but not all of them do. That is exactly where conferences should require a structured decision delta.

![Unanimous override rationale](plots/png/08_unanimous_override_rationale.png)

The 25% acceptance-rate complaint needs its own denominator check. Official acceptance rates are calculated over submitted or valid papers. ACs often experience a later decision pool after withdrawals and desk rejects. For ICLR, that later public pool has a substantially higher accept share than the headline acceptance rate. So the budget pressure is real, but a literal "25% of fully reviewed papers" interpretation is too crude.

The strongest version of the critique is: what happens when a paper gets at least three accept-leaning reviews? The answer is not "always accept." ICLR still rejects a meaningful minority of those papers, and the public rationales often point to novelty, correctness, missing evidence, or calibration concerns. The better norm is not a mechanical 3-accept rule; it is a high-rationale burden for rejecting such papers.

![Three accept votes fate](plots/png/10_three_accept_votes_fate.png)

The capacity question can be made more precise. If every paper with at least three accept-leaning public reviews were accepted first, would that alone overflow the official accept budget? Usually no. ICLR 2025 is the clearest pressure case: the 3+ accept-vote set is slightly larger than the official accept count. ICLR 2024 and 2026 do not show that arithmetic pressure in the same way.

![Three accept capacity load](plots/png/12_three_accept_capacity_load.png)

That leads to a useful accountability split. Some 3+ accept-vote rejections may be unavoidable under a hard slot budget, but many are not forced by capacity arithmetic. Those cases can still be correct decisions; they just need a public rationale strong enough for future ACs, reviewers, and authors to learn from the choice.

![Three accept rejection decomposition](plots/png/13_three_accept_rejection_decomposition.png)

The requested NeurIPS case, SophiaVL-R1, shows the distinction cleanly. It has four accept-leaning public scores and a final reject. The public decision comment is substantive and points to empirical/significance concerns, but there is no separate public meta-review exposed in the ICLR-style structure. That makes it a useful transparency case: the rationale is not absent, but it is harder to compare systematically with AC-guideline expectations.

![Case diagnostic iJ4i5HE5ER](plots/png/11_case_iJ4i5HE5ER.png)

The new meta-review layer covers {len(iclr_overrides):,} public ICLR majority-signal override cases, of which {len(iclr_with_meta):,} expose a public meta-review. The unsupervised reason clustering uses {total_clusters:,} public ICLR override meta-reviews with at least 30 words.

"""


def case_bullet(row: dict[str, Any]) -> str:
    themes = row.get("theme_summary") or "No public meta-review exposed"
    return (
        f"- [{row['title']}]({row['forum_url']}) ({row['venue']}, #{row['paper_number']}): "
        f"scores {row['scores']}, threshold {row['threshold']}, "
        f"confidence-weighted mean {float(row['weighted_mean']):.2f}, "
        f"reviewer majority {row['reviewer_majority']}, final {row['decision']}. "
        f"Public rationale themes: {themes}."
    )


def build_override_case_section(meta_rows: list[dict[str, Any]]) -> str:
    def ranked_rows(kind: str) -> list[dict[str, Any]]:
        rows = [
            row
            for row in meta_rows
            if row["override_type"] == kind
            and row["decision"] in {"accept", "reject"}
            and isinstance(row.get("weighted_mean"), float)
            and row["n_scored_reviews"] >= 3
        ]
        if kind == "accept_to_reject":
            return sorted(rows, key=lambda row: (-float(row["weighted_mean"]), row["venue"], row["title"]))
        return sorted(rows, key=lambda row: (float(row["weighted_mean"]), row["venue"], row["title"]))

    accept_to_reject = ranked_rows("accept_to_reject")
    reject_to_accept = ranked_rows("reject_to_accept")
    selected_accept_to_reject = []
    for venue in ["ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"]:
        venue_rows = [row for row in accept_to_reject if row["venue"] == venue]
        selected_accept_to_reject.extend(venue_rows[:2 if venue.startswith("ICLR") else 1])
    selected_reject_to_accept = []
    for venue in ["ICLR 2026", "ICLR 2025", "ICLR 2024", "ICML 2025", "NeurIPS 2025"]:
        venue_rows = [row for row in reject_to_accept if row["venue"] == venue]
        selected_reject_to_accept.extend(venue_rows[:1])

    return f"""## Representative Override Cases

The full CSVs keep the exhaustive paper-level records. The blog should not read like a dump of every named override, so this section keeps only representative public cases: high-score rejects, low-score accepts, and a small cross-venue sample where the public rationale can teach future ACs what the decision turned on.

### Majority reviewer accept -> final reject

{chr(10).join(case_bullet(row) for row in selected_accept_to_reject)}

### Majority reviewer reject -> final accept

{chr(10).join(case_bullet(row) for row in selected_reject_to_accept)}

These examples are not claims that the final decisions were wrong. They are examples of where public explanation quality matters most: if a decision moves against reviewer majority, the decision record should show what evidence outweighed the scores.

"""


def build_advisor_section(meta_rows: list[dict[str, Any]], cluster_rows: list[dict[str, Any]]) -> str:
    example = next((row for row in meta_rows if row["paper_id"] == "iJ4i5HE5ER"), None)
    no_meta_overrides = [
        row
        for row in meta_rows
        if row["override_type"] in {"accept_to_reject", "reject_to_accept"}
        and not row["has_public_meta_review"]
        and not row["has_public_decision_comment"]
    ]
    iclr = [row for row in meta_rows if row["venue"].startswith("ICLR") and row["decision"] in {"accept", "reject"} and row["n_scored_reviews"] >= 2]
    override = [row for row in iclr if row["override_type"] in {"accept_to_reject", "reject_to_accept"}]
    strong = [row for row in override if row["strong_override"]]
    strong_robust = [
        row
        for row in strong
        if row["has_public_meta_review"]
        and row["meta_word_count"] >= 150
        and row["feature_mentions_reviews"]
        and row["feature_causal_justification"]
    ]
    rebuttal_share = sum(1 for row in override if row["feature_mentions_rebuttal"]) / len(override) if override else 0
    review_share = sum(1 for row in override if row["feature_mentions_reviews"]) / len(override) if override else 0
    cluster_lines = "\n".join(
        f"- {row['cluster_label']}: {row['n']} cases; top terms `{row['top_terms']}`."
        for row in cluster_rows[:5]
    )
    borderline_accept_to_reject = [
        row
        for row in meta_rows
        if row["override_type"] == "accept_to_reject"
        and row["decision"] == "reject"
        and isinstance(row.get("threshold"), float)
        and isinstance(row.get("weighted_mean"), float)
        and row["threshold"] <= row["weighted_mean"] < row["threshold"] + 0.75
        and row["n_scored_reviews"] >= 3
    ]
    short_borderline = [row for row in borderline_accept_to_reject if row["public_rationale_word_count"] < 120]
    no_rebuttal_borderline = [row for row in borderline_accept_to_reject if not row["feature_mentions_rebuttal"]]
    no_review_synthesis_borderline = [row for row in borderline_accept_to_reject if not row["feature_mentions_reviews"]]
    short_theme_counts = Counter()
    for row in short_borderline:
        for theme, _ in THEMES:
            if row.get(f"theme_{theme}"):
                short_theme_counts[theme] += 1
    short_theme_line = ", ".join(
        f"{theme.lower()} ({count})" for theme, count in short_theme_counts.most_common(5)
    )
    matching_section = f"""
### Why AC Matching Should Be Expertise- and Interest-Gated

The case for high-expertise, high-interest AC matching is strongest exactly where paper weights are weakest: borderline majority-accept papers that the AC/PC rejects. In the public sample, {len(borderline_accept_to_reject):,} accept-to-reject cases sit within 0.75 points of the venue accept threshold with at least three scored reviews. Of those, {len(short_borderline):,} have fewer than 120 public rationale words, {len(no_rebuttal_borderline):,} have no public rebuttal/discussion marker, and {len(no_review_synthesis_borderline):,} have no public review-synthesis marker.

That is not evidence about individual AC expertise. It is evidence that low-context public explanations make expertise hard to audit. The short-rationale cases are not generic: their recurring themes are {short_theme_line}. The decisive issues often require field taste and technical fluency: whether a causal-discovery permutation test really needs stronger exchangeability justification, whether a multilingual benchmark measures a new failure mode rather than dataset surface form, whether a privacy defense needs formal guarantees, whether regenerating recommender-system data violates the domain's realism assumptions, or whether an LLM/generalization claim is only recombining existing theory. Those are poor fits for an AC assignment made mainly for load balancing or weak topical overlap.

The practical norm is direct: AC bidding is part of review quality, not scheduling metadata. An AC should bid high only when they have enough domain expertise to identify the live technical issue and enough interest to run the discussion. If a paper is borderline and the assigned AC cannot write a specific decision-critical question before rebuttal, the system should reassign it or add a domain co-AC/SAC before the final decision. Otherwise, a legitimate expert veto and a weakly documented low-engagement reversal can look the same to authors: a score-positive paper turned into a reject with too little explanation to learn from.

"""
    acceptance_rows = acceptance_counterfactual_rows(meta_rows)
    neurips_2025_overrides = [
        row
        for row in meta_rows
        if row["venue"] == "NeurIPS 2025"
        and row["override_type"] in {"accept_to_reject", "reject_to_accept"}
    ]
    neurips_2025_accept_to_reject = sum(1 for row in neurips_2025_overrides if row["override_type"] == "accept_to_reject")
    neurips_2025_reject_to_accept = sum(1 for row in neurips_2025_overrides if row["override_type"] == "reject_to_accept")
    neurips_2025_three_plus = next((row for row in acceptance_rows if row["venue"] == "NeurIPS 2025"), None)
    budget_lines = []
    for item in ACCEPTANCE_BENCHMARKS:
        if item["venue"] not in ANALYZABLE_VENUE_LABELS:
            continue
        if item.get("submitted") and item.get("accepted"):
            delta = int(round(item["accepted"] - item["submitted"] * 0.25))
            budget_lines.append(
                f"- {item['venue']}: official rate {item['rate']*100:.1f}%, {delta:+d} accepted papers relative to an exact 25% cap."
            )
        else:
            budget_lines.append(f"- {item['venue']}: public CFP language says rates tend to be around 25%, but no final count was used here.")
    budget_lines.append(
        "- AISTATS 2026, RLC 2025, and AAAI 2025 are excluded from this arithmetic because comparable public review-score/meta-review data were unavailable."
    )
    three_vote_lines = []
    capacity_lines = []
    for row in acceptance_rows:
        if not row["official_accepted"] or not row["three_plus_accept_vote_papers"]:
            continue
        venue = row["venue"]
        rejected = int(row["three_plus_accept_vote_rejected"])
        total = int(row["three_plus_accept_vote_papers"])
        load = float(row["three_plus_slot_load"])
        forced = int(row["capacity_shortfall_if_all_three_plus_accepted"] or 0)
        rationale = int(row["three_plus_rejections_not_forced_by_capacity"] or 0)
        caveat = "public lower bound" if not venue.startswith("ICLR") else "full public ICLR surface"
        three_vote_lines.append(
            f"- {venue}: {rejected}/{total} public papers with 3+ accept-leaning reviews were rejected ({load*100:.0f}% of official accept slots; {caveat})."
        )
        capacity_lines.append(
            f"- {venue}: capacity arithmetic can explain at most {min(forced, rejected)} of those {rejected} rejections; at least {rationale} require a substantive paper-level rationale."
        )
    example_text = ""
    case_reading = ""
    if example:
        example_themes = [
            key.replace("theme_", "")
            for key, value in example.items()
            if key.startswith("theme_") and value
        ]
        example_text = (
            f"The requested example, [SophiaVL-R1](https://openreview.net/forum?id=iJ4i5HE5ER), is therefore a useful negative control: "
            f"it has public scores `{example['scores']}`, reviewer majority `{example['reviewer_majority']}`, final `{example['decision']}`, "
            f"`{example['decision_word_count']}` public decision-comment words, and theme tags `{', '.join(example_themes)}`. "
            f"It cannot be assigned to the ICLR meta-review clusters because NeurIPS exposes a decision comment here, not a separate public meta-review."
        )
        case_reading = """
### Case Reading: SophiaVL-R1

The quantitative signature is simple: four public reviews are accept-leaning under the NeurIPS threshold, the confidence-weighted mean is 4.75, and the final decision is reject. The public decision comment is not empty or generic; it gives a substantive critique. In plain language, the rejection rationale centers on modest gains against a matched GRPO baseline, limited evidence that the thinking-reward component independently helps, insufficient reliability analysis for the reward signal, and a presentation/table-consistency issue.

That makes the case more instructive than a missing-rationale case. It shows a plausible kind of reviewer-majority override: the AC/PC may decide that reviewers liked the direction but did not price a specific baseline or ablation concern strongly enough. The public weakness is structural, not necessarily substantive: without a separate meta-review field, it is harder to tell which reviewer concerns were upweighted, whether reviewers updated after rebuttal, and whether the final decision differed from the AC's initial decision hypothesis.

For a future AC, the teachable version of this decision would say: "Reviewer support was real, but the decisive unresolved issue was X; the rebuttal addressed Y but not Z; therefore I am downweighting the numeric majority for reasons A and B." That is the standard this post argues for across venues.

"""
    return f"""## Acceptance-Rate Pressure Readout

Inspired by Sarath Chandar's May 2, 2026 tweet about three accept-leaning reviews and the "25% acceptance rate" constraint, I added a base-rate and capacity-counterfactual analysis. The safe reading is not "three accepts should automatically accept the paper." The safe reading is: if a paper has three or more accept-leaning reviews and is still rejected, the AC/PC rationale should be unusually legible, because authors and future ACs will naturally ask whether the decision was about paper substance, review calibration, or acceptance-budget pressure.

The first distinction is denominator choice. Official acceptance rates use submitted or valid papers. ACs often experience a later decision pool after desk rejects and withdrawals. For ICLR, that means an official 27-32% acceptance rate can coexist with a roughly 37-43% accept share among public non-withdrawn decision cases. That does not remove budget pressure, but it makes a literal "only 25% of fully reviewed papers can pass" story too crude.

Relative to a literal 25% cap:

{chr(10).join(budget_lines)}

The strongest empirical version of the concern is the "3 accepts" test:

{chr(10).join(three_vote_lines)}

The second distinction is capacity arithmetic. Ask a counterfactual question: if every public paper with 3+ accept-leaning reviews were accepted first, would the conference exceed its official accept count?

{chr(10).join(capacity_lines)}

The newer accepted-paper distribution posts add a different pressure point. China Research Collective's ICLR 2026 treemap presents accepted papers as a country/institution map, with China (Mainland) at 43.7%, the USA at 31.9%, Hong Kong at 7.7%, and Singapore at 5.5% in that visualization. Amit LeVi's fractional-author extension makes the same kind of public scoreboard across NeurIPS, ICLR, and ICML 2025; in that chart, China and the United States are the top two countries in all three venues, with the order flipping by conference.

I would not use those charts to infer anything about a specific AC decision. Their value is qualitative: they show how quickly review outcomes become status metrics for labs, countries, and careers. That raises the cost of opaque discretion. If ACs are doing real synthesis work, the community needs to see enough of that synthesis to avoid two oversimplified stories: "the process is mostly noise" and "the leaderboard itself explains merit."

The newer submission-scale argument, inspired by Ayan Banerjee's LinkedIn post, is different from the three-accept complaint. Taking the close-to-40k NeurIPS submission scale as given, the post asks whether, after a minimum quality threshold, review noise makes each non-desk-rejected paper behave like an approximately equal-probability trial. The repeated-submission math is correct under that assumption: with per-paper acceptance probability 0.267, six independent submissions give an 84.5% chance of at least one acceptance, and ten give 95.5%. The stated 81% figure corresponds more closely to NeurIPS 2025's official 24.5% acceptance rate, where six independent submissions give 81.5% and ten give 94.0%.

The empirical question is whether the equal-probability premise holds. The public data cannot observe latent paper quality directly, but it can test whether reviewer-score evidence is nearly flat after a minimum threshold. It is not. Using the proposed ICLR-style rule, "three reviews, average at least 6.49, and at most one reviewer below 6," an iid draw from public ICLR reviewer-score marginals gives a qualifying probability of 14.4% for ICLR 2025 and 12.8% for ICLR 2024, not 26.7%. Conditional on actually satisfying that rule among observed exact-three-review public papers, the final accept rate was 97.8% in ICLR 2025 and 96.7% in ICLR 2024. Weighted-score buckets are also sharply monotone: ICLR 2025 papers with weighted means 5-6 were accepted 24.4%, 6-6.49 were accepted 82.4%, 6.49-7 were accepted 94.8%, and 7-8 were accepted 98.1%.

The verified version of the post's point is therefore not "quality does not matter." It is: at massive submission scale, even a noisy-but-informative review process can make repeated marginal submission strategically powerful, especially if LLMs reduce the cost of producing many non-desk-rejected papers. That weakens "number of top-conference accepts" as a proxy for research depth. It also raises the burden on ACs and venues: preserving signal requires review-quality auditing, explicit rationale for high-risk decisions, and enough public reasoning that repeated draws are not mistaken for a clean measure of research depth.

Interpretation: a hard global target creates real pressure at the margin, and ICLR 2025 shows a concrete version of it. But capacity arithmetic alone cannot explain most public 3+ accept-vote rejections in the audited years. That supports a stronger transparency norm: if an AC/PC rejects a paper with 3+ accept-leaning reviews, the public rationale should say what outweighed the scores: novelty, correctness, missing evidence, review calibration, unresolved rebuttal, area calibration, or another explicit reason.

## Guideline-Compliance Readout

The public AC guidelines are directionally consistent across venues: ACs should synthesize reviewer evidence, manage discussion, assess author response/rebuttal, write a meta-review that explains the decision, and explicitly justify decisions that go against reviewer signals. RLC's process is more structural: SACs can reject against senior-reviewer consensus only with PC review, and accepted papers are expected to have SAC/SR agreement.

The data can test only public evidence of those norms, not private compliance. On public ICLR override cases, review-synthesis language appears in {review_share*100:.0f}% of public meta-reviews, while rebuttal/discussion language appears in {rebuttal_share*100:.0f}%. For unanimous-reviewer overrides, {len(strong_robust):,}/{len(strong):,} have a stronger public rationale signal: a 150+ word meta-review that mentions reviews and gives causal concern/issue language.

{example_text}

### Reason Clusters

The unsupervised ICLR meta-review clusters are not a substitute for reading the cases, but they turn thousands of AC decisions into a map of recurring judgment moves:

{cluster_lines}

{case_reading}### AC Story Archetypes

The data should not be read as a scoreboard of individual ACs. It is better read as a library of process stories. Five archetypes are especially useful for future ACs:

1. _The evidence-synthesizing override._ The reviewer-majority signal points one way, but the meta-review names a decisive issue, connects it to review text, and explains why rebuttal/discussion did or did not resolve it. This is the strongest form of AC discretion.
2. _The calibration rescue._ Reviewers use scores inconsistently, or one strong review is numerically outvoted by weaker reviews. A good AC makes the calibration judgment explicit instead of hiding it behind the final decision.
3. _The budget-shadow decision._ A paper looks acceptable in isolation, but the venue bar or area calibration is invoked implicitly. These cases are not necessarily illegitimate, but they are the ones most in need of transparent comparison language.
4. _The unteachable decision._ The final outcome diverges from reviewer evidence, but the public record does not explain what mattered. This is the failure mode the incentive proposal targets: not harshness, but missing institutional memory.
5. _The expertise bottleneck._ The final call depends on a domain-specific judgment that reviewers did not settle: benchmark adequacy, formal guarantees, theorem assumptions, domain realism, safety bar, or novelty relative to a narrow literature. These are the cases where AC matching matters before the review even starts.

{matching_section}
### AC Lessons

- Strong AC stories are visible when the meta-review does three things: names the evidence, explains why a reviewer-majority signal is insufficient, and records what changed or did not change after rebuttal/discussion.
- Weak public AC stories are not necessarily bad private AC work. They are cases where the venue provides too little public rationale for the community to learn from the decision.
- The highest-value process intervention is not replacing ACs with weighted scores; it is requiring high-expertise AC matching plus a structured decision delta whenever the AC/PC moves against reviewer majority or unanimity.
- Reviewer incentives should reward calibrated post-rebuttal updates. If a reviewer does not engage after an author response, the AC should mark whether that review was downweighted and why.
- Venue dashboards should report override rates, rationale availability, and guideline-evidence scores by area, without naming ACs publicly. This creates accountability while reducing shaming incentives.

## NeurIPS 2026 AC Recommendations

NeurIPS 2026 is already moving toward the right target. The public 2026 handbook tells ACs not to focus too much on scores, to judge the quality of review comments, to write an initial meta-review before author response, to lead reviewer-author discussion, and to explain in the final meta-review whether the author response addressed the initial issues. The 2026 AC pilot also makes the AC role more explicitly reciprocal: AC-authors can have their own reviews/meta-reviews withheld if they do not complete assigned meta-reviews, and severe non-engagement can lead to sanctions.

That policy direction matches the stress points in this audit. In the public NeurIPS 2025 sample, there are {neurips_2025_accept_to_reject} majority-accept-to-reject cases and {neurips_2025_reject_to_accept} majority-reject-to-accept cases. Among papers with at least three accept-leaning public reviews, {int(neurips_2025_three_plus['three_plus_accept_vote_rejected']) if neurips_2025_three_plus else 0}/{int(neurips_2025_three_plus['three_plus_accept_vote_papers']) if neurips_2025_three_plus else 0} were rejected; because the public rejected sample is incomplete, that is a lower bound rather than a full-conference estimate. The actionable lesson for 2026 is not to ban overrides; it is to make the override reasoning durable enough that authors, SACs, and future ACs can learn from it.

For the upcoming NeurIPS 2026 cycle, I would recommend six operational norms:

1. Treat AC bidding as the first quality gate. ACs should bid high only on papers where they have enough expertise and interest to identify decision-critical questions; SACs should add a domain co-AC or reassign when a borderline paper lands with a low-expertise, low-interest match.
2. Treat the initial meta-review as a contract with the author. It should say which concerns are decision-critical, which concerns are peripheral, and what evidence would actually move the paper.
3. Add a structured final-decision delta. The final meta-review should explicitly say what changed after rebuttal/discussion, what did not change, and why the final decision differs from the reviewer-majority signal when it does.
4. Escalate high-disagreement papers early. Three accept-leaning reviews plus a reject inclination, or three reject-leaning reviews plus an accept inclination, should automatically get SAC attention before author notification.
5. Track reviewer update quality. Reviewers who engage after rebuttal, correct mistakes, or revise scores with clear reasoning should receive credit. Reviews that remain stale after a substantive author response should be explicitly downweighted.
6. Publish post-cycle aggregate diagnostics. NeurIPS does not need to name ACs publicly, but it should publish area-level override rates, public-rationale completeness, reviewer-engagement rates, AC expertise-match diagnostics, and how often initial meta-review concerns were resolved.

Personally, as a first-time AC at NeurIPS 2026, I want to treat this essay as a checklist I am accountable to. For every assigned paper, I will write an initial decision hypothesis before author response, ask reviewers concrete post-rebuttal questions, track which reviews actually updated, and make any final override legible rather than hidden behind the score average. If a paper sits in a high-risk zone, such as 3+ accept-leaning reviews with a reject inclination, reviewer-majority reject with an accept inclination, or a stale decisive review after rebuttal, I will try to surface that explicitly to the SACs. My hope is to convince SACs and PCs that this is not extra bureaucracy; it is how we make hard decisions teachable, auditable, and less opaque for the next cycle.

## A Practical Guide to ACing

The useful version of the question is not "how do I pick accept or reject?" It is: how does an area chair turn noisy, partial, uneven reviewer evidence into a decision that is fair to authors, useful to the venue, and legible to the community after the fact? Across ML conferences, the AC role sits between three imperfect signals: the paper itself, the reviews, and the venue's finite acceptance budget. A good AC does not pretend any one of those signals is enough.

The AC's job has four parts. First, protect paper quality: novelty, correctness, empirical support, clarity, ethics, and fit to venue. Second, protect review quality: a review can be negative but excellent, positive but superficial, or numerically strong while textually fragile. Third, protect process quality: rebuttal, reviewer discussion, conflict handling, and area calibration should change decisions when they reveal real information. Fourth, protect explanation quality: the meta-review should make the final judgment understandable even to someone who disagrees.

### Before Reviews Arrive

Start at bidding. A good AC bid should mean: I understand this paper's technical neighborhood, I can tell what evidence would change my mind, and I am interested enough to run the discussion if the reviews conflict. A low-expertise AC can still manage logistics, but they should not be the decisive interpreter of a borderline technical dispute without a domain co-AC or SAC backup.

Then calibrate before triage. Read the venue's AC instructions, contribution-type guidance, and any area-specific norms. Write down your own decision rubric before the scores anchor you. For each paper type, ask what would be fatal, what would be fixable, and what would be a matter of taste. For example, missing baselines may be fatal for an empirical methods paper, less central for a theory paper, and different again for a dataset, benchmark, or negative-results paper.

Set a private standard for review quality. A review that says "incremental" should identify the closest prior work. A review that says "insufficient experiments" should name which comparison would change the decision. A review that says "strong paper" should still say why the contribution clears the venue bar. The AC should not average reviews before auditing whether the reviews deserve to be averaged.

### When Reviews Arrive

Read the paper enough to know whether the reviews are responding to the same object. Then audit the reviews along four axes: specificity, evidence, score-text consistency, and independence. If one reviewer gives a high score but lists fatal concerns, ask whether the score is inflated. If one reviewer gives a low score but cannot identify a concrete flaw, ask whether the review is under-evidenced. If several reviewers repeat the same mistaken premise, do not treat that as independent evidence.

The AC should write an initial decision hypothesis, not an initial verdict. A good hypothesis has this shape: "Current evidence points to X because of A and B; the live decision questions are C and D; rebuttal or reviewer discussion could change the decision if it resolves E." This is especially important for borderline papers, high-variance scores, and any case where the reviewer-majority signal may be overridden.

### During Rebuttal and Discussion

The best ACs make discussion concrete. Do not ask reviewers whether they "still feel the same." Ask: did the rebuttal resolve your correctness concern? Does the new experiment answer the missing-baseline issue? Is the novelty objection still valid given the cited related work? Should your score move, and if not, why not?

Track reviewer updating as evidence. Reviewers who engage deeply after rebuttal should get more weight than reviewers who ignore a substantive response. A stale review is not useless, but it should be labeled as stale. If the final decision depends on a concern from a non-engaged reviewer, the meta-review should explain why that concern remains decision-critical despite the lack of update.

### Making the Decision

Separate paper merit from process confidence. Some papers deserve rejection even after poor reviews; some papers deserve acceptance despite mixed scores; some papers need escalation because the process has not produced enough reliable evidence. The AC should be especially cautious in three cases: rejecting a paper with three or more accept-leaning reviews, accepting a paper with reviewer-majority reject, and overruling unanimous reviewers in either direction. These may be correct decisions, but they require a higher explanation burden.

Use scores as a diagnostic, not a command. A weighted score is useful because it summarizes reviewer sentiment and highlights outliers. It is dangerous when it hides the content of the disagreement. The AC should ask: is the disagreement about facts, values, venue bar, contribution type, or reviewer calibration? Different disagreements require different actions.

### Writing the Meta-Review

A publishable meta-review should teach. It should not merely announce. The minimal structure is:

1. Decision summary: final recommendation and confidence.
2. Evidence summary: the strongest reasons for and against acceptance.
3. Reviewer weighting: which reviews were most decision-relevant and why.
4. Rebuttal delta: what changed after author response and discussion.
5. Override delta: if the decision differs from reviewer majority or unanimity, what outweighed the scores.
6. Residual uncertainty: what remains unclear, and why the final call is still justified.

The tone matters. Authors can accept a hard decision more easily when the AC shows that the paper was actually understood. A good reject meta-review does not need to be long, but it should be specific enough that the authors know what would have changed the outcome. A good accept meta-review should still name limitations, because acceptance is not certification of perfection.

### What Good AC Work Looks Like

Good AC work is often quiet. It looks like noticing that two reviewers used "novelty" differently. It looks like asking one reviewer to update after a rebuttal rather than treating silence as consent. It looks like accepting a polarizing paper because the negative review was broad but not substantiated. It looks like rejecting a high-score paper because one correctness flaw survived discussion. It looks like telling authors exactly which concern remained decisive.

The failure mode is not only a wrong decision. The failure mode is an unteachable decision. If future ACs, reviewers, and authors cannot tell why a reviewer-majority signal was overridden, the process loses institutional memory. The practical standard should be: every hard AC call should leave behind enough reasoning that the next AC can make a better one.

## A Personal Story: Missing Meta-Review as Decision Debt

One personal double-blind RLC 2026 case motivates this section. The decision could plausibly have moved from reject to accept if the AC/SAC had engaged with the positive evidence, reviewer disagreement, and author response. Instead, the final process gave no meaningful meta-review to learn from. A missing meta-review converts a scientific disagreement into an institutional dead end.

The frustrating part is not simply rejection. Rejection can be correct. The frustrating part is that the process did not produce a decision record. Without a meta-review, authors cannot tell whether the decisive issue was novelty, correctness, empirical support, scope, reviewer calibration, venue budget, or simple non-engagement. Future ACs also cannot learn what standard was applied. To authors, the decision can look like private judgment without a public reasoning trail.

The publicly detailed RLC review-process design I could verify, from RLC 2024, makes this especially salient because it explicitly gives the SAC/AC a synthesizing role: they check review quality, can ask authors direct questions, write a meta-review, and PC review is expected when a rejection recommendation goes against a senior-reviewer acceptance recommendation. The RLC/RLJ 2026 submission page confirms the use of OpenReview for submissions and review correspondence, but does not expose the same detailed process text on that page. The architecture is still the right lesson. But architecture does not guarantee service. If an AC is not engaged in the synthesis work, the authors can experience the process as under-explained no matter how thoughtful the written policy is.

This is why "please write better meta-reviews" is too weak as a reform. Venues need incentives that make minimum AC service observable, repairable, and consequential during the cycle, before decisions are released. The goal is not to punish harsh decisions. The goal is to prevent unreasoned decisions.

## Data-Inspired AC Incentives

The audit suggests an incentive mechanism that is process-based rather than outcome-based. Do not reward ACs for accepting papers, rejecting papers, matching reviewer averages, or pleasing authors. Reward ACs for observable service quality: timely meta-reviews, concrete reviewer engagement, explicit rebuttal deltas, and clear explanations when final decisions diverge from reviewer signals.

A practical mechanism could work like this:

1. Every paper gets a machine-checkable decision record before author notification: reviewer aggregate, AC/SAC recommendation, final decision, meta-review word count, rebuttal mention, reviewer-weighting statement, and override-delta field.
2. High-risk cases are automatically flagged: no meta-review, very short meta-review, no rebuttal delta after author response, reviewer-majority override, unanimous-reviewer override, and 3+ accept-leaning reviews with final reject.
3. SACs get a pre-release repair queue. The goal is to fix missing explanations before authors see decisions, not to punish ACs afterward.
4. ACs receive a private service-quality score based on rationale completeness, discussion engagement, override explanation, timeliness, and review-quality auditing.
5. Good service is rewarded with visible credit: public service certificates, future AC preference, reduced emergency-review load, and optional letters to department chairs or advisors.
6. Incomplete service has consequences: own-paper review access can be delayed until assigned meta-reviews are complete, future AC invitations can be paused, and chronic non-engagement can be escalated to PCs.
7. The venue publishes only aggregate diagnostics: percentage of decisions with complete meta-reviews, number of repaired meta-reviews before release, override-rationale completeness, and reviewer-engagement rates by area.

This mechanism borrows the spirit of reciprocal reviewing policies that withhold benefits from authors who do not complete service, but adapts it to AC work. The clean version is a service escrow: if you submit to the venue and accept AC/reviewer duties, you owe the venue timely, auditable service. If that service is incomplete, the system should notice before authors receive an under-explained decision.

The key guardrail is that the metric must never evaluate whether the AC made the "right" accept/reject call. That would create perverse incentives and punish legitimate judgment. The metric should evaluate whether the decision is explainable, whether reviewer evidence was handled responsibly, and whether high-disagreement cases were escalated. In other words: score the service, not the taste.

"""


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    refresh = "--refresh" in sys.argv
    meta_rows = fetch_or_load_meta_rows(refresh=refresh)
    summary_rows = load_summary_rows()
    cluster_rows, cluster_docs = cluster_override_reasons(meta_rows)
    build_summaries(meta_rows, cluster_rows)
    write_csv(
        DATA_DIR / "meta_reason_cluster_assignments.csv",
        cluster_docs,
        ["paper_id", "venue", "title", "override_type", "cluster_id", "cluster_label"],
    )
    plots = [
        plot_predictiveness(summary_rows),
        plot_override_counts(summary_rows),
        plot_score_overlap(meta_rows),
        plot_rationale_availability(meta_rows),
        plot_theme_frequency(meta_rows),
        plot_reason_clusters(cluster_rows),
        plot_guideline_evidence(meta_rows),
        plot_unanimous_override_rationale(meta_rows),
        plot_three_accept_vote_fate(meta_rows),
        plot_three_accept_capacity_load(meta_rows),
        plot_three_accept_rejection_decomposition(meta_rows),
        plot_example_case(meta_rows),
    ]
    enhance_markdown(plots, meta_rows, cluster_rows)
    print(REPORT_DIR / "notion_blog_openreview_ac_overrides.md")
    for plot in plots:
        print(plot)
    print(DATA_DIR / "meta_decision_text_rows.csv")
    print(DATA_DIR / "meta_reason_clusters.csv")
    print(DATA_DIR / "guideline_public_evidence_summary.csv")
    print(DATA_DIR / "acceptance_budget_analysis.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
