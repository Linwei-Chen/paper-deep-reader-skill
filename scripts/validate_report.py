#!/usr/bin/env python3
"""Validate structure, grounding, visual coverage, and local assets in a report."""

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
    report_path: Path, text: str, sections: dict[int, str], results: Results
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

    if not re.search(r"图表.*覆盖|覆盖.*图表", sections.get(4, "")):
        results.error("Section 4 must contain a complete visual-coverage ledger.")
    if not re.search(r"强支持|部分支持|弱支持|未支持", sections.get(4, "")):
        results.error("Section 4 must grade claim support strength.")
    if "未来" not in sections.get(5, ""):
        results.error("Section 5 must include future research directions.")
    if "最终判断" not in sections.get(6, ""):
        results.warn("Section 6 should contain an explicit final judgment.")

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
) -> None:
    manifest = load_json(manifest_path, results, "Visual manifest")
    if not isinstance(manifest, dict):
        return

    visuals = manifest.get("visuals", [])
    if not isinstance(visuals, list):
        results.error("Visual manifest field 'visuals' must be a list.")
        return

    report_images = resolved_image_paths(report_path, text)
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
    results.note(
        f"Visual coverage: {len(visuals)} total, {key_count} marked key."
    )


def validate_source_map(path: Path, results: Results) -> None:
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

    schema_version = source_map.get("schema_version", 1)
    if schema_version == 2:
        profile = source_map.get("reader_profile")
        if not isinstance(profile, dict):
            results.error("source_map.json schema v2 requires a 'reader_profile' object.")
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
    validate_structure(report_path, text, sections, results)

    if args.manifest:
        manifest_path = Path(args.manifest).expanduser().resolve()
        validate_manifest(manifest_path, report_path, text, results)
    else:
        results.warn("No visual manifest supplied; full figure/table coverage is unverified.")

    if not args.allow_missing_source_map:
        source_map_path = (
            Path(args.source_map).expanduser().resolve()
            if args.source_map
            else report_path.parent / "source_map.json"
        )
        validate_source_map(source_map_path, results)

    return print_results(results, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
