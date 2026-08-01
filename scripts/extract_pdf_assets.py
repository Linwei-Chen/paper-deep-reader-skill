#!/usr/bin/env python3
"""Inventory PDF visuals and create visual or text-only review assets.

The automatic crops are intentionally conservative candidates, not trusted
final assets. Open every crop and use the ``crop`` subcommand when an axis,
legend, caption, footnote, or panel is missing. Text-only assets expose captions,
region text, and body references but never count as visual verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


CAPTION_RE = re.compile(
    r"^\s*(?P<kind>"
    r"(?:Extended\s+Data|Supplementary|Supplemental)\s+(?:Figure|Fig\.?|Table)"
    r"|Figure|Fig(?:ure)?\.?|Table|Algorithm|Scheme|Plate|Box|Chart"
    r"|图|表|算法|图版|附图|附表|补充图|补充表)"
    r"\s*\.?\s*(?P<number>(?:[A-Z]\s*)?\d+(?:[.\-]\d+)*(?:[A-Z])?)"
    r"\s*[:：.\-]?\s*(?P<caption>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def load_fitz() -> Any:
    try:
        import fitz  # type: ignore
    except ImportError:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            print(
                "ERROR: PyMuPDF is required.\n"
                "Use an isolated run, for example:\n"
                "  uv run --isolated --with pymupdf python "
                "extract_pdf_assets.py inventory PAPER.pdf OUTPUT_DIR",
                file=sys.stderr,
            )
            raise SystemExit(2)
    return fitz


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_page_spec(spec: str | None, page_count: int) -> list[int]:
    """Return sorted zero-based page indices."""
    if not spec:
        return list(range(page_count))

    selected: set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start, end = int(start_raw), int(end_raw)
            if start > end:
                start, end = end, start
            selected.update(range(start - 1, end))
        else:
            selected.add(int(part) - 1)

    invalid = sorted(index + 1 for index in selected if index < 0 or index >= page_count)
    if invalid:
        raise ValueError(
            f"Page selection outside 1..{page_count}: "
            + ", ".join(str(page) for page in invalid)
        )
    return sorted(selected)


def block_text(block: dict[str, Any]) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        text = "".join(str(span.get("text", "")) for span in spans).strip()
        if text:
            lines.append(text)
    return " ".join(lines).strip()


def rect_list(rect: Any) -> list[float]:
    return [round(float(rect.x0), 3), round(float(rect.y0), 3),
            round(float(rect.x1), 3), round(float(rect.y1), 3)]


def rect_area(rect: Any) -> float:
    return max(0.0, float(rect.width)) * max(0.0, float(rect.height))


def horizontal_overlap(a: Any, b: Any) -> float:
    overlap = max(0.0, min(float(a.x1), float(b.x1)) - max(float(a.x0), float(b.x0)))
    denominator = max(1.0, min(float(a.width), float(b.width)))
    return overlap / denominator


def union_rect(fitz: Any, rects: Iterable[Any]) -> Any | None:
    items = list(rects)
    if not items:
        return None
    result = fitz.Rect(items[0])
    for item in items[1:]:
        result.include_rect(item)
    return result


def clamp_rect(fitz: Any, rect: Any, page_rect: Any) -> Any:
    result = fitz.Rect(
        max(float(page_rect.x0), float(rect.x0)),
        max(float(page_rect.y0), float(rect.y0)),
        min(float(page_rect.x1), float(rect.x1)),
        min(float(page_rect.y1), float(rect.y1)),
    )
    if result.width <= 1 or result.height <= 1:
        raise ValueError(f"Crop rectangle is empty after clamping: {rect}")
    return result


def points_to_pixels(rect: Any, dpi: int) -> list[int]:
    scale = dpi / 72.0
    return [
        round(float(rect.x0) * scale),
        round(float(rect.y0) * scale),
        round(float(rect.x1) * scale),
        round(float(rect.y1) * scale),
    ]


def canonical_kind(raw_kind: str) -> str:
    value = raw_kind.lower().rstrip(".")
    if "fig" in value or value in {"图", "附图", "补充图"}:
        return "figure"
    if "table" in value or value in {"表", "附表", "补充表"}:
        return "table"
    if value in {"algorithm", "算法"}:
        return "algorithm"
    if value in {"scheme"}:
        return "scheme"
    if value in {"plate", "图版"}:
        return "plate"
    if value == "box":
        return "box"
    return "chart"


def safe_label(kind: str, number: str, page_number: int) -> str:
    compact_number = re.sub(r"[^A-Za-z0-9.-]+", "", number.replace(" ", ""))
    return f"{kind}-{compact_number or 'unknown'}-p{page_number:03d}".lower()


def extract_page_text(page: Any, clip: Any | None = None) -> str:
    kwargs: dict[str, Any] = {"sort": True}
    if clip is not None:
        kwargs["clip"] = clip
    try:
        value = page.get_text("text", **kwargs)
    except TypeError:
        kwargs.pop("sort", None)
        try:
            value = page.get_text("text", **kwargs)
        except Exception:
            return ""
    except Exception:
        return ""
    return str(value or "").strip()


def bounded_text(value: str, limit: int = 12000) -> str:
    cleaned = "\n".join(line.rstrip() for line in value.splitlines()).strip()
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n\n[TRUNCATED BY EXTRACTOR]"


def visual_reference_pattern(kind: str, number: str) -> re.Pattern[str]:
    prefixes = {
        "figure": r"(?:Figure|Fig(?:ure)?\.?|图|附图|补充图)",
        "table": r"(?:Table|表|附表|补充表)",
        "algorithm": r"(?:Algorithm|算法)",
        "scheme": r"(?:Scheme|方案)",
        "plate": r"(?:Plate|图版)",
        "box": r"(?:Box|框)",
        "chart": r"(?:Chart|图表)",
    }
    prefix = prefixes.get(kind, re.escape(kind))
    escaped_number = re.escape(number).replace(r"\ ", r"\s*")
    return re.compile(
        prefix + r"\s*\.?\s*" + escaped_number + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def collect_body_references(
    page_blocks: Sequence[dict[str, Any]],
    kind: str,
    number: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    pattern = visual_reference_pattern(kind, number)
    references: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for page_record in page_blocks:
        page_number = int(page_record["page"])
        for raw_text in page_record["blocks"]:
            text = re.sub(r"\s+", " ", str(raw_text)).strip()
            if not text or CAPTION_RE.match(text) or not pattern.search(text):
                continue
            text = bounded_text(text, 1600)
            key = (page_number, text)
            if key in seen:
                continue
            seen.add(key)
            references.append({"page": page_number, "text": text})
            if len(references) >= limit:
                return references
    return references


def extract_caption_blocks(
    fitz: Any, page: Any
) -> tuple[list[dict[str, Any]], list[Any], list[dict[str, Any]]]:
    data = page.get_text("dict")
    captions: list[dict[str, Any]] = []
    graphic_boxes: list[Any] = []
    text_blocks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[float, ...]]] = set()

    for block in data.get("blocks", []):
        block_type = block.get("type")
        bbox = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
        if block_type == 1 and rect_area(bbox) > 36:
            graphic_boxes.append(bbox)
            continue
        if block_type != 0:
            continue

        text = block_text(block)
        if not text:
            continue
        text_blocks.append({"bbox": bbox, "text": text})
        match = CAPTION_RE.match(text)
        if not match:
            continue

        kind = canonical_kind(match.group("kind"))
        number = re.sub(r"\s+", "", match.group("number"))
        key = (kind, number.lower(), tuple(rect_list(bbox)))
        if key in seen:
            continue
        seen.add(key)
        captions.append(
            {
                "kind": kind,
                "number": number,
                "caption": match.group("caption").strip(),
                "raw_text": text,
                "bbox": bbox,
            }
        )

    try:
        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
            if rect_area(rect) > 36:
                graphic_boxes.append(rect)
    except Exception:
        # Some malformed PDFs expose text/images but fail on vector drawings.
        pass

    return captions, graphic_boxes, text_blocks


def caption_boundaries(
    caption_rect: Any, captions: Sequence[dict[str, Any]], page_rect: Any
) -> tuple[float, float]:
    previous = [
        float(item["bbox"].y1)
        for item in captions
        if item["bbox"] is not caption_rect
        and float(item["bbox"].y1) <= float(caption_rect.y0) + 1
    ]
    following = [
        float(item["bbox"].y0)
        for item in captions
        if item["bbox"] is not caption_rect
        and float(item["bbox"].y0) >= float(caption_rect.y1) - 1
    ]
    previous_bottom = max(previous, default=float(page_rect.y0))
    following_top = min(following, default=float(page_rect.y1))
    return previous_bottom, following_top


def tableish_score(blocks: Sequence[dict[str, Any]], caption_rect: Any) -> float:
    if not blocks:
        return 0.0
    score = 0.0
    nearest_gap = float("inf")
    for block in blocks:
        text = str(block["text"])
        bbox = block["bbox"]
        digit_count = len(re.findall(r"\d", text))
        token_count = len(text.split())
        character_count = max(1, len(re.sub(r"\s+", "", text)))
        numeric_density = digit_count / character_count
        if token_count > 25 and numeric_density < 0.07:
            score -= 8.0
        else:
            score += min(digit_count, 16) * 1.2
            score += min(numeric_density, 0.5) * 40.0
            score += 3.0 if digit_count and token_count <= 20 else 0.0
            score += 0.8 if token_count <= 12 else -2.0
        gap = min(
            abs(float(bbox.y1) - float(caption_rect.y0)),
            abs(float(bbox.y0) - float(caption_rect.y1)),
        )
        nearest_gap = min(nearest_gap, gap)
    score += min(len(blocks), 30) * 0.35
    score -= min(nearest_gap, 100.0) * 0.08
    return score


def suggested_table_crop(
    fitz: Any,
    page_rect: Any,
    caption_rect: Any,
    captions: Sequence[dict[str, Any]],
    text_blocks: Sequence[dict[str, Any]],
    padding_points: float,
) -> tuple[Any, str]:
    page_height = float(page_rect.height)
    previous_bottom, following_top = caption_boundaries(
        caption_rect, captions, page_rect
    )
    above_start = max(previous_bottom + 1, float(caption_rect.y0) - page_height * 0.46)
    below_end = min(following_top - 1, float(caption_rect.y1) + page_height * 0.46)

    def in_region(item: dict[str, Any], y0: float, y1: float) -> bool:
        bbox = item["bbox"]
        center = (float(bbox.y0) + float(bbox.y1)) / 2
        is_caption = (
            abs(float(bbox.x0) - float(caption_rect.x0)) < 0.1
            and abs(float(bbox.y0) - float(caption_rect.y0)) < 0.1
        )
        same_column = horizontal_overlap(bbox, caption_rect) >= 0.02
        return not is_caption and same_column and y0 <= center <= y1

    above = [
        item for item in text_blocks
        if in_region(item, above_start, float(caption_rect.y0) - 1)
    ]
    below = [
        item for item in text_blocks
        if in_region(item, float(caption_rect.y1) + 1, below_end)
    ]
    above_score = tableish_score(above, caption_rect)
    below_score = tableish_score(below, caption_rect)

    if max(above_score, below_score) <= 0:
        choose_above = float(caption_rect.y0) > page_height * 0.55
    else:
        # Many venues put table captions below tables; a small tie goes above.
        choose_above = above_score >= below_score * 0.88
    chosen = above if choose_above else below
    content_rect = union_rect(fitz, [item["bbox"] for item in chosen])

    if content_rect is None:
        margin_x = float(page_rect.width) * 0.035
        if choose_above:
            crop = fitz.Rect(
                margin_x,
                above_start,
                float(page_rect.width) - margin_x,
                float(caption_rect.y1) + padding_points,
            )
        else:
            crop = fitz.Rect(
                margin_x,
                float(caption_rect.y0) - padding_points,
                float(page_rect.width) - margin_x,
                below_end,
            )
        return clamp_rect(fitz, crop, page_rect), "low"

    crop = fitz.Rect(
        min(float(content_rect.x0), float(caption_rect.x0)) - padding_points,
        min(float(content_rect.y0), float(caption_rect.y0)) - padding_points,
        max(float(content_rect.x1), float(caption_rect.x1)) + padding_points,
        max(float(content_rect.y1), float(caption_rect.y1)) + padding_points,
    )
    return clamp_rect(fitz, crop, page_rect), "medium"


def suggested_crop(
    fitz: Any,
    page_rect: Any,
    caption_rect: Any,
    kind: str,
    captions: Sequence[dict[str, Any]],
    graphic_boxes: Sequence[Any],
    text_blocks: Sequence[dict[str, Any]],
    padding_points: float,
) -> tuple[Any, str]:
    """Create a deliberately broad crop and a confidence label."""
    page_height = float(page_rect.height)
    page_width = float(page_rect.width)
    max_gap = page_height * 0.52

    above = [
        rect for rect in graphic_boxes
        if rect.y1 <= caption_rect.y0 + 4
        and caption_rect.y0 - rect.y1 <= max_gap
        and horizontal_overlap(rect, caption_rect) >= 0.05
    ]
    below = [
        rect for rect in graphic_boxes
        if rect.y0 >= caption_rect.y1 - 4
        and rect.y0 - caption_rect.y1 <= max_gap
        and horizontal_overlap(rect, caption_rect) >= 0.05
    ]

    margin_x = page_width * 0.035
    confidence = "low"
    previous_bottom, following_top = caption_boundaries(
        caption_rect, captions, page_rect
    )

    if kind in {"figure", "scheme", "plate", "chart"}:
        above_area = sum(rect_area(rect) for rect in above)
        below_area = sum(rect_area(rect) for rect in below)
        choose_above = bool(above and above_area >= below_area * 0.35)
        chosen = above if choose_above else below
        visual = union_rect(fitz, chosen)
        if visual is not None:
            x0 = min(float(visual.x0), float(caption_rect.x0)) - padding_points
            x1 = max(float(visual.x1), float(caption_rect.x1)) + padding_points
            y0 = min(float(visual.y0), float(caption_rect.y0)) - padding_points
            y1 = max(float(visual.y1), float(caption_rect.y1)) + padding_points
            confidence = "medium"
            if choose_above:
                y0 = max(y0, previous_bottom + 1)
            else:
                y1 = min(y1, following_top - 1)
        else:
            x0, x1 = margin_x, page_width - margin_x
            y0 = float(caption_rect.y0) - page_height * 0.42
            y1 = float(caption_rect.y1) + padding_points
    elif kind == "table":
        return suggested_table_crop(
            fitz,
            page_rect,
            caption_rect,
            captions,
            text_blocks,
            padding_points,
        )
    else:
        x0, x1 = margin_x, page_width - margin_x
        y0 = float(caption_rect.y0) - page_height * 0.08
        y1 = float(caption_rect.y1) + page_height * 0.30

    broad = fitz.Rect(x0, y0, x1, y1)
    return clamp_rect(fitz, broad, page_rect), confidence


def render_clip_with_fitz(
    fitz: Any, page: Any, clip: Any, output_path: Path, dpi: int
) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    pixmap.save(str(output_path))
    return int(pixmap.width), int(pixmap.height)


def write_ledger(
    output_dir: Path,
    records: Sequence[dict[str, Any]],
    text_only: bool,
) -> None:
    review_note = (
        "Text-only mode: inspect the generated text evidence; visual pixels remain "
        "unverified."
        if text_only
        else "Automatic crops are candidates. Visually inspect every asset before "
        "publication."
    )
    lines = [
        "# Visual inventory",
        "",
        f"> {review_note}",
        "",
        "| ID | Label | PDF page | Caption | Candidate crop | Review |",
        "|---|---|---:|---|---|---|",
    ]
    for item in records:
        caption = str(item.get("caption") or item.get("raw_text") or "").replace("|", r"\|")
        caption = re.sub(r"\s+", " ", caption)
        crop = item.get("candidate_crop") or "not generated"
        review = "TEXT REVIEW REQUIRED" if text_only else "VISUAL REVIEW REQUIRED"
        lines.append(
            f"| {item['id']} | {item['label']} | {item['page']} | "
            f"{caption} | `{crop}` | {review} |"
        )
    (output_dir / "visual_ledger.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_text_assets(
    output_dir: Path,
    records: Sequence[dict[str, Any]],
) -> None:
    visual_text_dir = output_dir / "text" / "visuals"
    visual_text_dir.mkdir(parents=True, exist_ok=True)
    ledger_lines = [
        "# Text-only visual evidence ledger",
        "",
        "> Extracted text is not visual verification. Do not infer unreported axes, "
        "colors, curves, panels, layout, or crop completeness.",
        "",
    ]

    for item in records:
        crop_text = bounded_text(str(item.pop("_extracted_region_text", "")))
        references = item.pop("_body_references", [])
        sources: list[str] = []
        if item.get("raw_text") or item.get("caption"):
            sources.append("caption")
        if crop_text:
            sources.append("suggested-region-text")
        if references:
            sources.append("body-references")

        if not sources:
            status = "unavailable"
        elif sources == ["caption"]:
            status = "caption-only"
        else:
            status = "partial"

        relative_path = Path("text") / "visuals" / f"{item['id']}.md"
        item["text_asset"] = str(relative_path)
        item["available_text_sources"] = sources
        item["text_extraction_status"] = status
        item["text_review"] = {
            "status": "pending",
            "sources": [],
            "notes": "",
            "limitations": "",
        }

        caption_text = str(item.get("raw_text") or item.get("caption") or "").strip()
        card_lines = [
            f"# Text evidence: {item['label']}",
            "",
            "> This file contains extracted text, not a visual interpretation. "
            "The image pixels, layout, axes, colors, and panels were not verified.",
            "",
            f"- **PDF page:** {item['page']}",
            f"- **Text extraction status:** {status}",
            f"- **Available sources:** {', '.join(sources) if sources else 'none'}",
            f"- **Suggested region:** {item['suggested_crop_bbox_points']}",
            "",
            "## Caption",
            "",
            caption_text or "[No caption text recovered]",
            "",
            "## Text from suggested visual region",
            "",
            "~~~text",
            crop_text or "[No text recovered from the suggested region]",
            "~~~",
            "",
            "## Body references",
            "",
        ]
        if references:
            for reference in references:
                card_lines.append(
                    f"- [PDF p.{reference['page']}] {reference['text']}"
                )
        else:
            card_lines.append("- [No body reference recovered]")
        card_lines.extend(
            [
                "",
                "## Mandatory limitation",
                "",
                "A text-only model must not claim direct observation of visual trends, "
                "layout, axes, colors, panels, qualitative examples, or crop completeness.",
                "",
            ]
        )
        (output_dir / relative_path).write_text(
            "\n".join(card_lines),
            encoding="utf-8",
        )

        compact_caption = re.sub(r"\s+", " ", caption_text) or "[unavailable]"
        ledger_lines.extend(
            [
                f"## {item['label']}",
                "",
                f"- **PDF page:** {item['page']}",
                f"- **Status:** {status}",
                f"- **Sources:** {', '.join(sources) if sources else 'none'}",
                f"- **Text card:** [{relative_path.name}]({relative_path.as_posix()})",
                f"- **Caption:** {compact_caption}",
                "",
            ]
        )

    (output_dir / "visual_text_ledger.md").write_text(
        "\n".join(ledger_lines),
        encoding="utf-8",
    )


def inventory(args: argparse.Namespace) -> int:
    fitz = load_fitz()
    pdf_path = Path(args.pdf).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    crops_dir = output_dir / "crops"
    text_pages_dir = output_dir / "text" / "pages"
    text_pages_dir.mkdir(parents=True, exist_ok=True)
    if not args.text_only:
        pages_dir.mkdir(parents=True, exist_ok=True)
    if not args.text_only and not args.no_auto_crop:
        crops_dir.mkdir(parents=True, exist_ok=True)

    document = fitz.open(str(pdf_path))
    try:
        try:
            page_indices = parse_page_spec(args.pages, document.page_count)
        except (TypeError, ValueError) as exc:
            print(f"ERROR: invalid --pages value: {exc}", file=sys.stderr)
            return 2
        page_records: list[dict[str, Any]] = []
        page_block_records: list[dict[str, Any]] = []
        visual_records: list[dict[str, Any]] = []
        total_text_characters = 0

        for page_index in page_indices:
            page = document.load_page(page_index)
            page_number = page_index + 1
            captions, graphic_boxes, text_blocks = extract_caption_blocks(fitz, page)
            page_text = extract_page_text(page)
            total_text_characters += len(page_text)
            page_text_path = text_pages_dir / f"page-{page_number:03d}.txt"
            page_text_path.write_text(page_text + ("\n" if page_text else ""), encoding="utf-8")
            page_block_records.append(
                {
                    "page": page_number,
                    "blocks": [item["text"] for item in text_blocks],
                }
            )

            page_image: Path | None = None
            width: int | None = None
            height: int | None = None
            if not args.text_only:
                page_image = pages_dir / f"page-{page_number:03d}.png"
                width, height = render_clip_with_fitz(
                    fitz, page, page.rect, page_image, args.dpi
                )
            page_records.append(
                {
                    "page": page_number,
                    "width_pixels": width,
                    "height_pixels": height,
                    "width_points": round(float(page.rect.width), 3),
                    "height_points": round(float(page.rect.height), 3),
                    "image": (
                        str(page_image.relative_to(output_dir)) if page_image else None
                    ),
                    "text": str(page_text_path.relative_to(output_dir)),
                    "text_characters": len(page_text),
                    "caption_count": len(captions),
                }
            )

            for caption in captions:
                kind = caption["kind"]
                number = caption["number"]
                item_id = safe_label(kind, number, page_number)
                crop_rect, confidence = suggested_crop(
                    fitz,
                    page.rect,
                    caption["bbox"],
                    kind,
                    captions,
                    graphic_boxes,
                    text_blocks,
                    args.padding,
                )
                extracted_region_text = extract_page_text(page, clip=crop_rect)
                crop_path: Path | None = None
                crop_size: tuple[int, int] | None = None
                if not args.text_only and not args.no_auto_crop:
                    crop_path = crops_dir / f"{item_id}.png"
                    crop_size = render_clip_with_fitz(
                        fitz, page, crop_rect, crop_path, args.dpi
                    )

                visual_records.append(
                    {
                        "id": item_id,
                        "label": f"{kind.title()} {number}",
                        "kind": kind,
                        "number": number,
                        "page": page_number,
                        "caption": caption["caption"],
                        "raw_text": caption["raw_text"],
                        "caption_bbox_points": rect_list(caption["bbox"]),
                        "caption_bbox_pixels": points_to_pixels(caption["bbox"], args.dpi),
                        "suggested_crop_bbox_points": rect_list(crop_rect),
                        "suggested_crop_bbox_pixels": points_to_pixels(crop_rect, args.dpi),
                        "candidate_crop": (
                            str(crop_path.relative_to(output_dir)) if crop_path else None
                        ),
                        "selected_asset": None,
                        "candidate_crop_size_pixels": list(crop_size) if crop_size else None,
                        "source_page_image": (
                            str(page_image.relative_to(output_dir)) if page_image else None
                        ),
                        "source_page_text": str(page_text_path.relative_to(output_dir)),
                        "crop_confidence": confidence,
                        "crop_review_required": True,
                        "visual_verification": (
                            "not-performed" if args.text_only else "pending"
                        ),
                        "review_notes": "",
                        "key": None,
                        "claim_ids": [],
                        "_extracted_region_text": extracted_region_text,
                    }
                )

        for visual in visual_records:
            visual["_body_references"] = collect_body_references(
                page_block_records,
                str(visual["kind"]),
                str(visual["number"]),
            )
        write_text_assets(output_dir, visual_records)

        manifest = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_pdf": str(pdf_path),
            "source_sha256": sha256_file(pdf_path),
            "page_count": document.page_count,
            "render_dpi": args.dpi,
            "selected_pages": [index + 1 for index in page_indices],
            "analysis_mode": "text-only" if args.text_only else "visual",
            "text_layer_available": total_text_characters > 0,
            "text_layer_characters": total_text_characters,
            "automatic_crops_are_unverified": True,
            "pages": page_records,
            "visuals": visual_records,
        }
        manifest_path = output_dir / "visual_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_ledger(output_dir, visual_records, args.text_only)

        if args.text_only:
            print(f"Extracted text from {len(page_records)} page(s) to {text_pages_dir}")
        else:
            print(f"Rendered {len(page_records)} page(s) to {pages_dir}")
        print(f"Detected {len(visual_records)} numbered visual caption(s)")
        print(f"Manifest: {manifest_path}")
        print(f"Text evidence ledger: {output_dir / 'visual_text_ledger.md'}")
        if args.text_only:
            print(
                "TEXT-ONLY MODE: visual pixels were not inspected. Complete each key "
                "item's text_review and retain explicit limitations."
            )
            if total_text_characters == 0:
                print(
                    "WARNING: the PDF has no extractable text layer; use a matching "
                    "structured source or local OCR.",
                    file=sys.stderr,
                )
            if not visual_records:
                print(
                    "WARNING: no numbered captions were detected; inspect structured "
                    "text sources or build the visual ledger manually.",
                    file=sys.stderr,
                )
        elif visual_records:
            print("REVIEW REQUIRED: open every candidate crop before embedding it.")
        else:
            print(
                "WARNING: no numbered captions were detected; inspect page previews "
                "and build the visual ledger manually.",
                file=sys.stderr,
            )
        return 0
    finally:
        document.close()


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "bbox must contain four comma-separated numbers: x0,y0,x1,y1"
        ) from exc
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "bbox must contain four comma-separated numbers: x0,y0,x1,y1"
        )
    x0, y0, x1, y1 = parts
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError("bbox requires x1>x0 and y1>y0")
    return x0, y0, x1, y1


def crop(args: argparse.Namespace) -> int:
    fitz = load_fitz()
    pdf_path = Path(args.pdf).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    document = fitz.open(str(pdf_path))
    try:
        if args.page < 1 or args.page > document.page_count:
            print(
                f"ERROR: --page must be within 1..{document.page_count}",
                file=sys.stderr,
            )
            return 2

        page = document.load_page(args.page - 1)
        scale = args.dpi / 72.0
        x0, y0, x1, y1 = args.bbox
        padding = float(args.padding)
        pixel_rect = (
            max(0.0, x0 - padding),
            max(0.0, y0 - padding),
            x1 + padding,
            y1 + padding,
        )
        point_rect = fitz.Rect(*(coordinate / scale for coordinate in pixel_rect))
        point_rect = clamp_rect(fitz, point_rect, page.rect)
        width, height = render_clip_with_fitz(
            fitz, page, point_rect, output_path, args.dpi
        )
        print(f"Wrote {output_path} ({width}x{height}px)")
        print(
            "REVIEW REQUIRED: verify axes, legends, captions, footnotes, and all "
            "scientifically relevant panels are present."
        )
        return 0
    finally:
        document.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a PDF visual inventory with reviewable crops and text-only "
            "evidence assets."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser(
        "inventory", help="Render pages, detect captions, and suggest crops."
    )
    inventory_parser.add_argument("pdf", help="Source PDF path.")
    inventory_parser.add_argument("output", help="Output assets directory.")
    inventory_parser.add_argument(
        "--dpi", type=int, default=180, help="Render resolution (default: 180)."
    )
    inventory_parser.add_argument(
        "--pages",
        help='Optional 1-based page ranges, e.g. "1-5,8,11-13". Default: all.',
    )
    inventory_parser.add_argument(
        "--padding",
        type=float,
        default=10.0,
        help="Padding around heuristic crops in PDF points (default: 10).",
    )
    inventory_parser.add_argument(
        "--no-auto-crop",
        action="store_true",
        help="Render pages and inventory captions without candidate crops.",
    )
    inventory_parser.add_argument(
        "--text-only",
        action="store_true",
        help=(
            "Skip page/crop images and emit caption, region-text, and body-reference "
            "assets for models without vision."
        ),
    )
    inventory_parser.set_defaults(handler=inventory)

    crop_parser = subparsers.add_parser(
        "crop", help="Create an exact crop using page-preview pixel coordinates."
    )
    crop_parser.add_argument("pdf", help="Source PDF path.")
    crop_parser.add_argument("output", help="Output PNG path.")
    crop_parser.add_argument("--page", type=int, required=True, help="1-based PDF page.")
    crop_parser.add_argument(
        "--bbox",
        type=parse_bbox,
        required=True,
        help="Pixel bbox x0,y0,x1,y1 measured on a page rendered at --dpi.",
    )
    crop_parser.add_argument(
        "--dpi", type=int, default=180, help="Render resolution (default: 180)."
    )
    crop_parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="Extra padding in pixels (default: 0).",
    )
    crop_parser.set_defaults(handler=crop)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "dpi", 1) < 72:
        parser.error("--dpi must be at least 72")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
