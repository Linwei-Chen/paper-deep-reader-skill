#!/usr/bin/env python3
"""Validate report structure, grounding, and visual or text-only evidence coverage."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote


SECTION_RE = re.compile(r"^##\s+([1-6])(?:[.、])?\s*(.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\("
    r"(?P<path><[^>]+>|[^)\s]+)"
    r"(?:\s+[\"'][^\"']*[\"'])?\)"
)
PLACEHOLDER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bTODO\b",
        r"\bTBD\b",
        r"待补(?:充|图|写)?",
        r"待填写",
        r"待插(?:入|图)?",
        r"\[论文标题\]",
        r"\[作者\]",
        r"\[official URL\]",
        r"\[(?:\.{3}|…)\]",
        r"<paper[-_ ]?(?:slug|title|path)>",
    )
]
ANCHOR_RE = re.compile(
    r"(?:图|表|附图|附表|补充图|补充表|图版|式|算法|定理|定义|命题|引理|案例|附录)"
    r"\s*[A-Z]?\s*\d+(?:\([a-z0-9]+\))?"
    r"|(?:Figure|Fig\.?|Table|Scheme|Plate|Box|Chart|Eq\.?|Equation|Algorithm|"
    r"Theorem|Definition|Proposition|Lemma|Case|Appendix)\s*[A-Z]?\s*\d+"
    r"|PDF\s*p\.\s*\d+"
    r"|§\s*\d+(?:\.\d+)*",
    re.IGNORECASE,
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
TEXT_ONLY_DISCLOSURE_RE = re.compile(
    r"无视觉(?:模式|模型)|视觉内容(?:未|没有)(?:直接)?核验"
    r"|text[- ]only mode|visual (?:content|pixels?) (?:was |were )?not (?:directly )?verified",
    re.IGNORECASE,
)


class Results:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def strip_markdown(value: str) -> str:
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[*_`>#~]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def visible_length(value: str) -> int:
    plain = strip_markdown(value)
    return len(
        re.sub(
            r"[\s，。；：、“”‘’！？,.!?;:/\\|()\[\]{}<>《》—–\-+]",
            "",
            plain,
        )
    )


def split_sections(text: str, results: Results) -> dict[int, str]:
    matches = list(SECTION_RE.finditer(text))
    numbers = [int(match.group(1)) for match in matches]
    if numbers != [1, 2, 3, 4, 5, 6]:
        results.error(
            "Top-level sections must appear exactly once and in order 1..6; "
            f"found {numbers or 'none'}."
        )

    sections: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[number] = text[match.end():end].strip()
    return sections


def first_content_line(section: str) -> str:
    for line in section.splitlines():
        candidate = strip_markdown(line)
        if candidate and not candidate.startswith("来源"):
            return candidate
    return ""


def resolve_local_target(report_path: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if target.startswith(("http://", "https://", "data:", "#")):
        return None
    target = unquote(target.split("#", 1)[0])
    return (report_path.parent / target).resolve()


def validate_structure(
    report_path: Path,
    text: str,
    sections: dict[int, str],
    results: Results,
    text_only: bool = False,
) -> None:
    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        results.error("Missing level-1 report title.")

    for number in range(1, 7):
        content = strip_markdown(sections.get(number, ""))
        if not content:
            results.error(f"Section {number} is empty.")

    pitch = first_content_line(sections.get(1, ""))
    if not pitch:
        results.error("Section 1 has no elevator pitch.")
    else:
        pitch_length = visible_length(pitch)
        is_cjk_pitch = len(CJK_RE.findall(pitch)) >= 5
        if is_cjk_pitch and pitch_length > 50:
            results.error(
                f"Chinese elevator pitch exceeds 50 visible characters ({pitch_length})."
            )
        elif not is_cjk_pitch:
            pitch_words = len(WORD_RE.findall(strip_markdown(pitch)))
            if pitch_words > 30:
                results.error(
                    f"Elevator pitch exceeds 30 words ({pitch_words})."
                )

    is_quick = "本报告为快读" in text or "快读模式" in text
    plain_length = visible_length(text)
    minimum = 800 if is_quick else 2500
    if plain_length < minimum:
        results.warn(
            f"Report is unusually short for {'quick' if is_quick else 'deep'} mode "
            f"({plain_length} visible characters; expected at least {minimum})."
        )

    if not re.search(
        r"(?:图表|视觉).{0,12}覆盖|覆盖.{0,12}(?:图表|视觉)",
        sections.get(4, ""),
    ):
        results.error("Section 4 must contain a complete visual-coverage ledger.")
    if not re.search(r"强支持|部分支持|弱支持|未支持", sections.get(4, "")):
        results.error("Section 4 must grade claim support strength.")
    if "未来" not in sections.get(5, ""):
        results.error("Section 5 must include future research directions.")
    if "最终判断" not in sections.get(6, ""):
        results.warn("Section 6 should contain an explicit final judgment.")
    if text_only and not TEXT_ONLY_DISCLOSURE_RE.search(text):
        results.error(
            "Text-only reports must explicitly disclose that visual content was "
            "not directly verified."
        )

    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            results.error(f"Unresolved placeholder found: {match.group(0)!r}.")

    if text.count("$$") % 2:
        results.error("Unbalanced display-math delimiter '$$'.")

    anchor_count = len(ANCHOR_RE.findall(text))
    minimum_anchors = 2 if is_quick else 5
    if anchor_count < minimum_anchors:
        results.warn(
            f"Only {anchor_count} source-anchor occurrence(s) found; "
            f"expected at least {minimum_anchors}."
        )

    images = list(IMAGE_RE.finditer(text))
    for image in images:
        alt = image.group("alt").strip()
        raw_target = image.group("path")
        if not alt:
            results.error(f"Image has empty alt text: {raw_target}")
        local_path = resolve_local_target(report_path, raw_target)
        if local_path is not None and not local_path.is_file():
            results.error(f"Referenced image does not exist: {raw_target}")
    results.note(f"Found {len(images)} Markdown image reference(s).")


def label_pattern(kind: str, number: str) -> re.Pattern[str]:
    escaped = re.escape(number).replace(r"\ ", r"\s*")
    if kind == "figure":
        prefix = (
            r"(?:图|附图|补充图|(?:Extended\s+Data|Supplementary|Supplemental)\s+"
            r"(?:Figure|Fig\.?)|Figure|Fig\.?)"
        )
    elif kind == "table":
        prefix = (
            r"(?:表|附表|补充表|(?:Extended\s+Data|Supplementary|Supplemental)\s+"
            r"Table|Table)"
        )
    elif kind == "scheme":
        prefix = r"(?:Scheme|方案)"
    elif kind == "plate":
        prefix = r"(?:Plate|图版)"
    elif kind == "box":
        prefix = r"(?:Box|框)"
    elif kind == "chart":
        prefix = r"(?:Chart|图表)"
    else:
        prefix = r"(?:算法|Algorithm)"
    return re.compile(prefix + r"\s*" + escaped + r"(?!\d)", re.IGNORECASE)


def resolved_image_paths(report_path: Path, text: str) -> set[Path]:
    paths: set[Path] = set()
    for match in IMAGE_RE.finditer(text):
        path = resolve_local_target(report_path, match.group("path"))
        if path is not None:
            paths.add(path)
    return paths


def load_json(path: Path, results: Results, label: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        results.error(f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        results.error(f"{label} is invalid JSON ({path}): {exc}")
    return None


def unresolved_json_paths(value: Any, path: str = "$") -> list[str]:
    unresolved: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            unresolved.extend(unresolved_json_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            unresolved.extend(unresolved_json_paths(child, f"{path}[{index}]"))
    elif isinstance(value, str) and value.strip().upper() in {
        "REPLACE_ME",
        "TODO",
        "TBD",
    }:
        unresolved.append(path)
    return unresolved


def validate_manifest(
    manifest_path: Path,
    report_path: Path,
    text: str,
    results: Results,
    text_only: bool = False,
) -> None:
    manifest = load_json(manifest_path, results, "Visual manifest")
    if not isinstance(manifest, dict):
        return

    manifest_mode = str(manifest.get("analysis_mode", "")).strip()
    if text_only and manifest_mode != "text-only":
        results.error(
            "Text-only validation requires a manifest with analysis_mode='text-only'."
        )
    if not text_only and manifest_mode == "text-only":
        results.error(
            "Manifest was generated in text-only mode; rerun validation with --text-only."
        )
    try:
        manifest_schema_version = int(manifest.get("schema_version", 1))
    except (TypeError, ValueError):
        manifest_schema_version = 1

    visuals = manifest.get("visuals", [])
    if not isinstance(visuals, list):
        results.error("Visual manifest field 'visuals' must be a list.")
        return

    report_images = resolved_image_paths(report_path, text)
    allowed_text_only_images: set[Path] = set()
    unclassified = 0
    key_count = 0

    for index, visual in enumerate(visuals, start=1):
        if not isinstance(visual, dict):
            results.error(f"Visual manifest item {index} is not an object.")
            continue
        kind = str(visual.get("kind", ""))
        number = str(visual.get("number", ""))
        label = str(visual.get("label") or f"{kind} {number}")
        if not kind or not number:
            results.error(f"Visual manifest item {index} lacks kind/number.")
            continue

        if not label_pattern(kind, number).search(text):
            results.error(f"Numbered visual is absent from report coverage: {label}.")

        key = visual.get("key")
        if not isinstance(key, bool):
            unclassified += 1
            continue
        if not key:
            continue

        key_count += 1
        if text_only:
            visual_verification = str(
                visual.get("visual_verification", "")
            ).strip()
            if visual_verification not in {
                "not-performed",
                "externally-verified",
            }:
                results.error(
                    f"Key visual has invalid text-only visual_verification: {label}."
                )

            text_asset = visual.get("text_asset")
            if not text_asset:
                results.error(f"Key visual has no text_asset: {label}.")
            else:
                text_asset_path = (
                    manifest_path.parent / str(text_asset)
                ).resolve()
                if not text_asset_path.is_file():
                    results.error(
                        f"Text evidence asset for {label} does not exist: "
                        f"{text_asset_path}"
                    )

            text_review = visual.get("text_review")
            if not isinstance(text_review, dict):
                results.error(f"Key visual has no text_review object: {label}.")
            else:
                if text_review.get("status") != "complete":
                    results.error(f"Key visual text review is incomplete: {label}.")
                sources = text_review.get("sources")
                if (
                    not isinstance(sources, list)
                    or not sources
                    or not all(
                        isinstance(source, str) and source.strip()
                        for source in sources
                    )
                ):
                    results.error(
                        f"Key visual text review has no valid sources: {label}."
                    )
                if not str(text_review.get("notes", "")).strip():
                    results.error(
                        f"Key visual text review has no notes: {label}."
                    )
                if not str(text_review.get("limitations", "")).strip():
                    results.error(
                        f"Key visual text review has no limitations: {label}."
                    )

            if (
                visual_verification == "not-performed"
                and visual.get("crop_review_required") is False
            ):
                results.error(
                    f"Unverified text-only visual cannot clear crop review: {label}."
                )

            candidate_crop = visual.get("candidate_crop")
            if candidate_crop and visual_verification == "not-performed":
                candidate_path = (
                    manifest_path.parent / str(candidate_crop)
                ).resolve()
                if candidate_path in report_images:
                    results.error(
                        f"Unverified candidate crop is embedded in text-only report: "
                        f"{label}."
                    )
            if visual_verification == "externally-verified":
                if visual.get("crop_review_required") is not False:
                    results.error(
                        f"Externally verified visual still requires crop review: {label}."
                    )
                if not str(visual.get("review_notes", "")).strip():
                    results.error(
                        f"Externally verified visual has no reviewer notes: {label}."
                    )
                selected_asset = visual.get("selected_asset")
                if not selected_asset:
                    results.error(
                        f"Externally verified visual has no selected_asset: {label}."
                    )
                else:
                    selected_path = (
                        manifest_path.parent / str(selected_asset)
                    ).resolve()
                    allowed_text_only_images.add(selected_path)
                    if not selected_path.is_file():
                        results.error(
                            f"Externally verified asset does not exist: {selected_path}"
                        )
                    if selected_path not in report_images:
                        results.error(
                            f"Externally verified asset is not embedded: {label}."
                        )
            continue

        if (
            manifest_schema_version >= 2
            and visual.get("visual_verification")
            not in {"complete", "externally-verified"}
        ):
            results.error(f"Key visual lacks completed visual verification: {label}.")
        if visual.get("crop_review_required") is not False:
            results.error(f"Key visual still requires crop review: {label}.")

        selected_asset = visual.get("selected_asset")
        if not selected_asset:
            results.error(f"Key visual has no selected_asset: {label}.")
            continue
        asset_path = (manifest_path.parent / str(selected_asset)).resolve()
        if not asset_path.is_file():
            results.error(f"Selected asset for {label} does not exist: {asset_path}")
        if asset_path not in report_images:
            results.error(f"Selected asset for {label} is not embedded in report.")

    if unclassified:
        results.error(
            f"{unclassified} visual(s) have key=null; classify every numbered visual."
        )
    if visuals and key_count == 0:
        results.warn("No visual is marked key=true; verify this is intentional.")
    if not visuals:
        results.note(
            "Manifest contains no detected visuals; manually confirm the paper has no "
            "numbered figures/tables or add missed entries."
        )
    if text_only:
        for image in IMAGE_RE.finditer(text):
            local_path = resolve_local_target(report_path, image.group("path"))
            if local_path is None:
                results.error(
                    "Text-only reports cannot embed remote/data images without a "
                    "manifested external visual verification."
                )
            elif local_path not in allowed_text_only_images:
                results.error(
                    f"Text-only report embeds an unverified image: {image.group('path')}"
                )
    results.note(
        f"Visual coverage: {len(visuals)} total, {key_count} marked key."
    )


def validate_source_map(
    path: Path,
    results: Results,
    text_only: bool = False,
) -> None:
    source_map = load_json(path, results, "Source map")
    if not isinstance(source_map, dict):
        return

    for placeholder_path in unresolved_json_paths(source_map):
        results.error(
            f"source_map.json contains an unresolved placeholder at {placeholder_path}."
        )

    paper = source_map.get("paper")
    if not isinstance(paper, dict):
        results.error("source_map.json requires a 'paper' object.")
    else:
        for field in ("title", "sources", "page_convention"):
            if not paper.get(field):
                results.error(f"source_map.json paper.{field} is missing.")

    try:
        schema_version = int(source_map.get("schema_version", 1))
    except (TypeError, ValueError):
        schema_version = -1
    if schema_version in {2, 3}:
        profile = source_map.get("reader_profile")
        if not isinstance(profile, dict):
            results.error(
                "source_map.json schema v2+ requires a 'reader_profile' object."
            )
        else:
            for field in ("domain", "audience", "goal", "depth", "language"):
                if not profile.get(field):
                    results.error(
                        f"source_map.json reader_profile.{field} is missing."
                    )
            selected_lenses = profile.get("selected_lenses")
            if (
                not isinstance(selected_lenses, list)
                or not selected_lenses
                or not all(
                    isinstance(item, str) and item.strip()
                    for item in selected_lenses
                )
            ):
                results.error(
                    "source_map.json reader_profile.selected_lenses must be "
                    "a non-empty string list."
                )
    elif schema_version != 1:
        results.warn(f"Unrecognized source_map schema_version: {schema_version!r}.")

    if text_only and schema_version != 3:
        results.error(
            "Text-only reports require source_map schema v3 execution metadata."
        )
    if schema_version == 3:
        execution = source_map.get("execution")
        if not isinstance(execution, dict):
            results.error(
                "source_map.json schema v3 requires an 'execution' object."
            )
        else:
            visual_mode = execution.get("visual_mode")
            visual_verification = execution.get("visual_verification")
            if visual_mode not in {"visual", "text-only"}:
                results.error(
                    "source_map.json execution.visual_mode must be visual or text-only."
                )
            if visual_verification not in {
                "complete",
                "not-performed",
                "externally-verified",
            }:
                results.error(
                    "source_map.json execution.visual_verification is invalid."
                )
            if text_only and visual_mode != "text-only":
                results.error(
                    "Text-only validation conflicts with source_map visual_mode."
                )
            if not text_only and visual_mode == "text-only":
                results.error(
                    "source_map visual_mode is text-only; use --text-only."
                )
            if (
                not text_only
                and visual_mode == "visual"
                and visual_verification
                not in {"complete", "externally-verified"}
            ):
                results.error(
                    "Visual source_map requires completed visual verification."
                )
            if (
                text_only
                and visual_verification
                not in {"not-performed", "externally-verified"}
            ):
                results.error(
                    "Text-only source_map cannot claim direct visual verification."
                )
            text_sources = execution.get("text_evidence_sources")
            if text_only and (
                not isinstance(text_sources, list)
                or not text_sources
                or not all(
                    isinstance(source, str) and source.strip()
                    for source in text_sources
                )
            ):
                results.error(
                    "Text-only source_map requires non-empty text_evidence_sources."
                )

    claims = source_map.get("claims")
    if not isinstance(claims, list) or not claims:
        results.error("source_map.json requires a non-empty 'claims' list.")
        return

    seen_ids: set[str] = set()
    allowed_statuses = {"strong", "partial", "weak", "unsupported"}
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            results.error(f"source_map claim {index} is not an object.")
            continue
        claim_id = str(claim.get("id", "")).strip()
        if not claim_id:
            results.error(f"source_map claim {index} has no id.")
        elif claim_id in seen_ids:
            results.error(f"Duplicate source_map claim id: {claim_id}")
        else:
            seen_ids.add(claim_id)
        if not claim.get("claim"):
            results.error(f"source_map claim {claim_id or index} has no text.")
        status = claim.get("status")
        if status not in allowed_statuses:
            results.error(
                f"source_map claim {claim_id or index} has invalid status: {status!r}."
            )
        evidence = claim.get("evidence")
        if status != "unsupported" and (not isinstance(evidence, list) or not evidence):
            results.error(
                f"Supported claim {claim_id or index} has no evidence row."
            )

    results.note(f"Source map contains {len(claims)} claim(s).")


def print_results(results: Results, strict: bool) -> int:
    for message in results.errors:
        print(f"ERROR: {message}")
    for message in results.warnings:
        print(f"WARNING: {message}")
    for message in results.notes:
        print(f"NOTE: {message}")

    blocking = len(results.errors) + (len(results.warnings) if strict else 0)
    if blocking:
        mode = "strict mode" if strict else "validation"
        print(
            f"FAIL ({mode}): {len(results.errors)} error(s), "
            f"{len(results.warnings)} warning(s)."
        )
        return 1
    print(f"PASS: 0 errors, {len(results.warnings)} warning(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a paper deep-reading Markdown report."
    )
    parser.add_argument("report", help="Path to report.md.")
    parser.add_argument(
        "--manifest", help="Path to visual_manifest.json (recommended)."
    )
    parser.add_argument(
        "--source-map",
        help="Path to source_map.json. Defaults to report sibling source_map.json.",
    )
    parser.add_argument(
        "--allow-missing-source-map",
        action="store_true",
        help="Do not require source_map.json (for chat-only or explicitly reduced output).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help=(
            "Validate the no-vision workflow: require disclosure and completed "
            "text evidence reviews instead of direct crop verification."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path = Path(args.report).expanduser().resolve()
    if not report_path.is_file():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        return 2

    text = report_path.read_text(encoding="utf-8")
    results = Results()
    sections = split_sections(text, results)
    validate_structure(
        report_path,
        text,
        sections,
        results,
        text_only=args.text_only,
    )

    if args.manifest:
        manifest_path = Path(args.manifest).expanduser().resolve()
        validate_manifest(
            manifest_path,
            report_path,
            text,
            results,
            text_only=args.text_only,
        )
    else:
        results.warn("No visual manifest supplied; full figure/table coverage is unverified.")

    if not args.allow_missing_source_map:
        source_map_path = (
            Path(args.source_map).expanduser().resolve()
            if args.source_map
            else report_path.parent / "source_map.json"
        )
        validate_source_map(
            source_map_path,
            results,
            text_only=args.text_only,
        )

    return print_results(results, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
