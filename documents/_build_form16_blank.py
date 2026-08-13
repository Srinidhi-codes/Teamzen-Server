"""Build a blank Form 16 Part B template (graphics + images only) from the sample PDF."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import fitz

ASSETS = Path(__file__).resolve().parent / "form16_assets"
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "MSXPS6972G_PARTB_2026-27.pdf"
OUT = ASSETS / "form16_partb_blank.pdf"
SAMPLE_COPY = ASSETS / "form16_partb_sample.pdf"


def _replay_drawings(src_page: fitz.Page, dst_page: fitz.Page) -> None:
    shape = dst_page.new_shape()
    for path in src_page.get_drawings():
        for item in path.get("items", []):
            op = item[0]
            if op == "l":  # line
                shape.draw_line(item[1], item[2])
            elif op == "re":  # rectangle
                shape.draw_rect(item[1])
            elif op == "qu":  # quad
                shape.draw_quad(item[1])
            elif op == "c":  # curve
                shape.draw_bezier(item[1], item[2], item[3], item[4])
            elif op == "m":  # move — start of path handled by next ops
                pass
        stroke = path.get("color")
        fill = path.get("fill")
        width = path.get("width") if path.get("width") is not None else 0.5
        closePath = bool(path.get("closePath"))
        stroke_opacity = path.get("stroke_opacity")
        fill_opacity = path.get("fill_opacity")
        if stroke_opacity is None:
            stroke_opacity = 1
        if fill_opacity is None:
            fill_opacity = 1
        line_join = path.get("lineJoin")
        if isinstance(line_join, (list, tuple)):
            line_join = line_join[0] if line_join else 0
        line_join = int(line_join or 0)
        line_cap = path.get("lineCap")
        if isinstance(line_cap, (list, tuple)):
            line_cap = line_cap[0] if line_cap else 0
        line_cap = int(line_cap or 0)
        shape.finish(
            color=stroke,
            fill=fill,
            width=width,
            closePath=closePath,
            even_odd=bool(path.get("even_odd", False)),
            stroke_opacity=stroke_opacity,
            fill_opacity=fill_opacity,
            dashes=path.get("dashes"),
            lineJoin=line_join,
            lineCap=line_cap,
        )
    shape.commit()


def build_blank() -> str:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sample = SAMPLE if SAMPLE.exists() else SAMPLE_COPY
    if not sample.exists():
        raise FileNotFoundError(f"Form 16 sample PDF not found at {SAMPLE}")
    if sample != SAMPLE_COPY:
        shutil.copy2(sample, SAMPLE_COPY)

    src = fitz.open(sample)
    dst = fitz.open()
    for sp in src:
        dp = dst.new_page(width=sp.rect.width, height=sp.rect.height)

        # Images first (watermark under table lines)
        infos = sorted(
            sp.get_image_info(xrefs=True),
            key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]),
            reverse=True,
        )
        for info in infos:
            xref = info["xref"]
            bbox = fitz.Rect(info["bbox"])
            try:
                pix = fitz.Pixmap(src, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                if bbox.width > 300 and bbox.height > 200:
                    dp.insert_image(bbox, pixmap=pix, keep_proportion=False, overlay=False)
                else:
                    dp.insert_image(bbox, pixmap=pix, keep_proportion=False, overlay=True)
            except Exception as e:
                print("skip image", xref, e)

        _replay_drawings(sp, dp)

    dst.save(str(OUT), deflate=True, garbage=4)
    dst.close()
    src.close()
    print("wrote", OUT, "bytes", OUT.stat().st_size)
    return str(OUT)


if __name__ == "__main__":
    build_blank()
    doc = fitz.open(str(OUT))
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    preview = ASSETS / "blank_page1_preview.png"
    pix.save(str(preview))
    print("preview", preview, "pages", doc.page_count)
    doc.close()
