from pathlib import Path
import zipfile, os, textwrap

base = Path("/mnt/data/image_optimizer_streamlit_hosted")
base.mkdir(exist_ok=True)

app_code = r'''
import io
import os
import zipfile
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
from PIL import Image, ImageOps

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}

st.set_page_config(
    page_title="Image Optimizer",
    page_icon="🖼️",
    layout="wide",
)

st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 2rem;}
div[data-testid="stMetricValue"] {font-size: 1.6rem;}
</style>
""", unsafe_allow_html=True)

def human_size(num):
    num = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}"
        num /= 1024

def ensure_rgb(img, background="white"):
    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, background)
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return img.convert("RGB")

def convert_bytes(data, filename, fmt, quality):
    with Image.open(io.BytesIO(data)) as im:
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
            work = (
                im.convert("RGBA")
                if im.mode in ("RGBA", "LA") or "transparency" in im.info
                else im.convert("RGB")
            )
            work.save(
                out,
                format="WEBP",
                quality=quality,
                method=6,
            )

        elif fmt == "PNG":
            compress_level = max(0, min(9, round(quality / 100 * 9)))
            work = im.copy()
            if work.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                work = work.convert("RGBA")
            work.save(
                out,
                format="PNG",
                optimize=True,
                compress_level=compress_level,
            )

        return out.getvalue()

def output_name(name, fmt):
    p = Path(name)
    ext = ".jpg" if fmt == "JPG" else f".{fmt.lower()}"
    return str(p.with_suffix(ext))

def extract_zip(uploaded_zip):
    files = []
    with zipfile.ZipFile(uploaded_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            p = Path(info.filename)
            if p.suffix.lower() in SUPPORTED:
                files.append({
                    "name": info.filename,
                    "data": zf.read(info),
                })
    return files

st.title("🖼️ Image Optimizer & Converter")
st.caption("Convert and compress JPG, PNG and WebP images directly in your browser.")

tab_files, tab_zip = st.tabs(["Upload Images", "Upload ZIP / Folder"])

uploaded_items = []

with tab_files:
    uploads = st.file_uploader(
        "Choose images",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help="You can select multiple images at once.",
    )
    if uploads:
        uploaded_items.extend(
            {"name": f.name, "data": f.getvalue()} for f in uploads
        )

with tab_zip:
    zip_upload = st.file_uploader(
        "Choose a ZIP file",
        type=["zip"],
        accept_multiple_files=False,
        help="ZIP a whole folder on your Mac and upload it here. Subfolder structure will be preserved.",
        key="zip_upload",
    )
    if zip_upload:
        try:
            uploaded_items.extend(extract_zip(io.BytesIO(zip_upload.getvalue())))
        except Exception as e:
            st.error(f"Could not read ZIP: {e}")

st.divider()

c1, c2, c3 = st.columns([1.1, 1.4, 1.5])

with c1:
    fmt = st.selectbox("Convert to", ["JPG", "WEBP", "PNG"])

with c2:
    quality = st.slider("Quality / compression", 1, 100, 85, 1)

with c3:
    only_if_smaller = st.toggle("Only keep output if smaller", value=True)

if fmt == "PNG":
    st.info(
        "PNG is lossless. The slider controls compression effort, not visual quality. "
        "For much smaller files, WebP is usually the better choice."
    )

total_size = sum(len(x["data"]) for x in uploaded_items)

m1, m2, m3 = st.columns(3)
m1.metric("Images loaded", f"{len(uploaded_items):,}")
m2.metric("Input size", human_size(total_size))
m3.metric("Target format", fmt)

with st.expander("Preview file list", expanded=False):
    if uploaded_items:
        for item in uploaded_items[:200]:
            st.write(f"• {item['name']}")
        if len(uploaded_items) > 200:
            st.caption(f"Showing first 200 of {len(uploaded_items):,} files.")
    else:
        st.write("No images uploaded yet.")

st.divider()

if st.button(
    "🚀 Convert Images",
    type="primary",
    use_container_width=True,
    disabled=not uploaded_items,
):
    progress = st.progress(0)
    status = st.empty()

    results = []
    max_workers = min(8, max(2, os.cpu_count() or 2))

    def job(item):
        try:
            old_size = len(item["data"])
            converted = convert_bytes(
                item["data"],
                item["name"],
                fmt,
                quality,
            )
            new_size = len(converted)

            if only_if_smaller and new_size >= old_size:
                return {
                    "status": "SKIPPED",
                    "name": item["name"],
                    "old": old_size,
                    "new": new_size,
                    "data": None,
                    "reason": "Converted file would not be smaller",
                }

            return {
                "status": "CONVERTED",
                "name": output_name(item["name"], fmt),
                "old": old_size,
                "new": new_size,
                "data": converted,
                "reason": "",
            }

        except Exception as e:
            return {
                "status": "ERROR",
                "name": item["name"],
                "old": len(item["data"]),
                "new": 0,
                "data": None,
                "reason": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(job, item) for item in uploaded_items]

        for idx, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            progress.progress(idx / len(futures))
            status.text(f"Processing {idx:,} / {len(futures):,}")

    status.empty()

    converted = [r for r in results if r["status"] == "CONVERTED"]
    skipped = [r for r in results if r["status"] == "SKIPPED"]
    errors = [r for r in results if r["status"] == "ERROR"]

    old_total = sum(r["old"] for r in converted)
    new_total = sum(r["new"] for r in converted)
    saved = max(0, old_total - new_total)
    pct = saved / old_total * 100 if old_total else 0

    st.success("Conversion complete.")

    a, b, c, d = st.columns(4)
    a.metric("Converted", f"{len(converted):,}")
    b.metric("Skipped", f"{len(skipped):,}")
    c.metric("Errors", f"{len(errors):,}")
    d.metric("Space saved", f"{human_size(saved)} ({pct:.1f}%)")

    if converted:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for r in converted:
                zf.writestr(r["name"], r["data"])

        zip_buffer.seek(0)

        st.download_button(
            "⬇️ Download Converted Images ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"converted_{fmt.lower()}_images.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )

    if skipped:
        with st.expander("Skipped files", expanded=False):
            for r in skipped[:200]:
                st.write(f"• {r['name']} — {r['reason']}")

    if errors:
        with st.expander("Errors", expanded=True):
            for r in errors:
                st.error(f"{r['name']}: {r['reason']}")
'''

requirements = """streamlit>=1.39
Pillow>=10.0
"""

readme = r'''
# Hosted Image Optimizer

This version is designed for Streamlit Community Cloud / streamlit.app.

## Why there is no local folder picker

A hosted Streamlit app runs on a remote server. The server cannot open Finder or directly access folders on your Mac.

Instead, this version lets you:

- Upload multiple JPG / PNG / WebP files
- Upload a ZIP containing a complete folder
- Choose JPG / PNG / WebP output
- Set image quality
- Convert in the browser-hosted app
- Download all converted images as a ZIP

## Deploy

Use:

- app.py
- requirements.txt

Main file path: `app.py`
'''

(base / "app.py").write_text(app_code)
(base / "requirements.txt").write_text(requirements)
(base / "README.md").write_text(readme)

zip_path = Path("/mnt/data/Image_Optimizer_Streamlit_Hosted.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in base.iterdir():
        z.write(f, arcname=f"Image_Optimizer_Streamlit_Hosted/{f.name}")

print(zip_path)
