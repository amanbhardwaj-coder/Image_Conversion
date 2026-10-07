
import io
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
from PIL import Image, ImageOps

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

st.set_page_config(
    page_title="Image Optimizer",
    page_icon="🖼️",
    layout="wide",
)

st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 2rem;}
.small-muted {color:#6b7280; font-size:0.9rem;}
div[data-testid="stMetricValue"] {font-size:1.6rem;}
</style>
""", unsafe_allow_html=True)

def choose_folder(title: str):
    """Open a native macOS/desktop folder chooser."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title)
        root.destroy()
        return folder or None
    except Exception:
        return None

def human_size(num):
    num = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}"
        num /= 1024

def list_images(folder, recursive=True):
    p = Path(folder)
    iterator = p.rglob("*") if recursive else p.glob("*")
    return sorted(
        x for x in iterator
        if x.is_file() and x.suffix.lower() in SUPPORTED_EXTENSIONS
    )

def ensure_rgb(img, background="white"):
    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, background)
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return img.convert("RGB")

def build_output_path(src, input_root, output_root, fmt, keep_structure=True):
    ext = ".jpg" if fmt == "JPG" else f".{fmt.lower()}"
    if keep_structure:
        rel = src.relative_to(input_root)
        dest = output_root / rel
        dest = dest.with_suffix(ext)
    else:
        dest = output_root / f"{src.stem}{ext}"
    return dest

def convert_one(src, dest, fmt, quality, overwrite, only_if_smaller):
    try:
        old_size = src.stat().st_size

        if dest.exists() and not overwrite and src.resolve() != dest.resolve():
            return {
                "status": "SKIPPED",
                "file": str(src),
                "output": str(dest),
                "old": old_size,
                "new": dest.stat().st_size,
                "reason": "Output already exists",
            }

        with Image.open(src) as im:
            im.load()
            im = ImageOps.exif_transpose(im)

            out = io.BytesIO()

            if fmt == "JPG":
                work = ensure_rgb(im)
                work.save(
                    out,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )

            elif fmt == "WEBP":
                # Preserve transparency where present.
                work = im.convert("RGBA") if im.mode in ("RGBA", "LA") or "transparency" in im.info else im.convert("RGB")
                work.save(
                    out,
                    format="WEBP",
                    quality=quality,
                    method=6,
                )

            elif fmt == "PNG":
                # PNG is lossless, so "quality" is mapped to compression effort.
                # Higher quality slider -> stronger compression effort.
                compress_level = max(0, min(9, round(quality / 100 * 9)))
                if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    work = im.convert("RGBA")
                else:
                    work = im.copy()
                work.save(
                    out,
                    format="PNG",
                    optimize=True,
                    compress_level=compress_level,
                )

            data = out.getvalue()
            new_size = len(data)

        if only_if_smaller and new_size >= old_size:
            return {
                "status": "SKIPPED",
                "file": str(src),
                "output": str(dest),
                "old": old_size,
                "new": new_size,
                "reason": "Converted file would not be smaller",
            }

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)

        return {
            "status": "CONVERTED",
            "file": str(src),
            "output": str(dest),
            "old": old_size,
            "new": new_size,
            "reason": "",
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "file": str(src),
            "output": str(dest),
            "old": 0,
            "new": 0,
            "reason": str(e),
        }

# Session defaults
if "input_dir" not in st.session_state:
    st.session_state.input_dir = str(Path.cwd())
if "output_dir" not in st.session_state:
    st.session_state.output_dir = str(Path.cwd() / "optimized_images")

st.title("🖼️ Image Optimizer & Converter")
st.caption("Convert and compress JPG, PNG and WebP images locally on your Mac.")

left, right = st.columns(2)

with left:
    st.subheader("Input folder")
    c1, c2 = st.columns([5, 1])
    with c1:
        st.session_state.input_dir = st.text_input(
            "Input path",
            value=st.session_state.input_dir,
            label_visibility="collapsed",
        )
    with c2:
        if st.button("Browse", key="browse_input", use_container_width=True):
            picked = choose_folder("Select input image folder")
            if picked:
                st.session_state.input_dir = picked
                st.rerun()

with right:
    st.subheader("Output folder")
    c1, c2 = st.columns([5, 1])
    with c1:
        st.session_state.output_dir = st.text_input(
            "Output path",
            value=st.session_state.output_dir,
            label_visibility="collapsed",
        )
    with c2:
        if st.button("Browse", key="browse_output", use_container_width=True):
            picked = choose_folder("Select output folder")
            if picked:
                st.session_state.output_dir = picked
                st.rerun()

st.divider()

a, b, c = st.columns([1.2, 1.2, 1.5])

with a:
    fmt = st.selectbox("Convert to", ["JPG", "WEBP", "PNG"], index=0)

with b:
    quality = st.slider("Quality / compression", 1, 100, 85, 1)

with c:
    recursive = st.toggle("Include subfolders", value=True)
    keep_structure = st.toggle("Keep subfolder structure", value=True)

d, e = st.columns(2)
with d:
    only_if_smaller = st.toggle("Only save when output is smaller", value=True)
with e:
    overwrite = st.toggle("Overwrite existing output files", value=False)

if fmt == "PNG":
    st.info(
        "PNG is lossless. The quality slider controls compression effort rather than visual quality. "
        "For much smaller web images, WebP is usually the better choice."
    )

input_dir = Path(st.session_state.input_dir).expanduser()
output_dir = Path(st.session_state.output_dir).expanduser()

if not input_dir.exists() or not input_dir.is_dir():
    st.error("Input folder does not exist.")
    st.stop()

files = list_images(input_dir, recursive=recursive)
total_input_size = sum(p.stat().st_size for p in files)

m1, m2, m3 = st.columns(3)
m1.metric("Images found", f"{len(files):,}")
m2.metric("Input size", human_size(total_input_size))
m3.metric("Target format", fmt)

with st.expander("Preview files", expanded=False):
    if files:
        preview = "\n".join(str(p.relative_to(input_dir)) for p in files[:100])
        st.code(preview)
        if len(files) > 100:
            st.caption(f"Showing first 100 of {len(files):,} files.")
    else:
        st.write("No supported images found.")

st.divider()

if st.button("🚀 Convert Images", type="primary", use_container_width=True, disabled=not files):
    output_dir.mkdir(parents=True, exist_ok=True)

    progress = st.progress(0)
    status_text = st.empty()

    results = []
    max_workers = min(8, max(2, os.cpu_count() or 2))

    jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for src in files:
            dest = build_output_path(
                src,
                input_dir,
                output_dir,
                fmt,
                keep_structure=keep_structure,
            )
            jobs.append(
                executor.submit(
                    convert_one,
                    src,
                    dest,
                    fmt,
                    quality,
                    overwrite,
                    only_if_smaller,
                )
            )

        for idx, future in enumerate(as_completed(jobs), start=1):
            results.append(future.result())
            progress.progress(idx / len(jobs))
            status_text.text(f"Processing {idx:,} / {len(jobs):,}")

    status_text.empty()

    converted = [r for r in results if r["status"] == "CONVERTED"]
    skipped = [r for r in results if r["status"] == "SKIPPED"]
    errors = [r for r in results if r["status"] == "ERROR"]

    old_total = sum(r["old"] for r in converted)
    new_total = sum(r["new"] for r in converted)
    saved = max(0, old_total - new_total)
    pct = (saved / old_total * 100) if old_total else 0

    st.success("Conversion complete.")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Converted", f"{len(converted):,}")
    r2.metric("Skipped", f"{len(skipped):,}")
    r3.metric("Errors", f"{len(errors):,}")
    r4.metric("Space saved", f"{human_size(saved)} ({pct:.1f}%)")

    if errors:
        with st.expander("Errors", expanded=True):
            for r in errors:
                st.error(f'{r["file"]}: {r["reason"]}')

    if skipped:
        with st.expander("Skipped files", expanded=False):
            for r in skipped[:200]:
                st.write(f'• {Path(r["file"]).name} — {r["reason"]}')

    with st.expander("Converted files", expanded=False):
        for r in converted[:300]:
            reduction = (1 - r["new"] / r["old"]) * 100 if r["old"] else 0
            st.write(
                f'• {Path(r["file"]).name} → {Path(r["output"]).name} '
                f'({reduction:.1f}% smaller)'
            )

    st.caption(f"Output saved to: {output_dir}")
