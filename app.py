from pathlib import Path
import zipfile, os

out = Path("/mnt/data/streamlit_image_optimizer_fixed")
out.mkdir(exist_ok=True)

app_py = r'''
import io
import os
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(
    page_title="Image Optimizer & Converter",
    page_icon="🖼️",
    layout="wide",
)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ---------- Styling ----------
st.markdown(
    """
    <style>
        .block-container {
            max-width: 1150px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1 {
            margin-bottom: 0.25rem;
        }

        div[data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,0.22);
            padding: 14px;
            border-radius: 12px;
        }

        div.stButton > button,
        div.stDownloadButton > button {
            border-radius: 10px;
            min-height: 46px;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- Helpers ----------
def human_size(size_bytes: int) -> str:
    size = float(size_bytes)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def image_has_transparency(img: Image.Image) -> bool:
    return (
        img.mode in ("RGBA", "LA")
        or (img.mode == "P" and "transparency" in img.info)
    )


def flatten_to_rgb(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """Convert an image to RGB. Transparent pixels become white."""
    if image_has_transparency(img):
        rgba = img.convert("RGBA")
        base = Image.new("RGBA", rgba.size, background + (255,))
        base.alpha_composite(rgba)
        return base.convert("RGB")

    return img.convert("RGB")


def convert_image(image_bytes: bytes, output_format: str, quality: int) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.load()
        img = ImageOps.exif_transpose(img)

        output = io.BytesIO()

        if output_format == "JPG":
            converted = flatten_to_rgb(img)
            converted.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )

        elif output_format == "WEBP":
            if image_has_transparency(img):
                converted = img.convert("RGBA")
            else:
                converted = img.convert("RGB")

            converted.save(
                output,
                format="WEBP",
                quality=quality,
                method=6,
            )

        elif output_format == "PNG":
            if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                converted = img.convert("RGBA")
            else:
                converted = img.copy()

            # PNG is lossless. Higher slider values use stronger compression.
            compression_level = max(0, min(9, round((quality / 100) * 9)))

            converted.save(
                output,
                format="PNG",
                optimize=True,
                compress_level=compression_level,
            )

        else:
            raise ValueError(f"Unsupported output format: {output_format}")

        return output.getvalue()


def output_filename(original_name: str, output_format: str) -> str:
    path = Path(original_name)

    if output_format == "JPG":
        extension = ".jpg"
    elif output_format == "WEBP":
        extension = ".webp"
    else:
        extension = ".png"

    return str(path.with_suffix(extension))


def load_images_from_zip(zip_bytes: bytes):
    images = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            file_path = Path(info.filename)

            # Ignore macOS metadata files.
            if "__MACOSX" in file_path.parts or file_path.name.startswith("._"):
                continue

            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            images.append(
                {
                    "name": info.filename,
                    "data": archive.read(info),
                }
            )

    return images


def deduplicate_names(items):
    """Avoid duplicate ZIP paths if uploads contain the same filename."""
    seen = {}
    result = []

    for item in items:
        original_name = item["name"]
        path = Path(original_name)
        key = original_name.lower()

        if key not in seen:
            seen[key] = 1
            result.append(item)
            continue

        seen[key] += 1
        copy_number = seen[key]

        new_name = str(
            path.with_name(f"{path.stem}_{copy_number}{path.suffix}")
        )

        copied = dict(item)
        copied["name"] = new_name
        result.append(copied)

    return result


# ---------- Header ----------
st.title("🖼️ Image Optimizer & Converter")
st.caption(
    "Convert JPG, PNG and WebP images online, reduce file size, "
    "and download everything as a ZIP."
)

st.info(
    "Because this app is hosted online, it cannot directly browse folders on your Mac. "
    "Upload individual images or upload a ZIP of an entire folder."
)


# ---------- Upload ----------
tab1, tab2 = st.tabs(["📷 Upload Images", "📦 Upload Folder as ZIP"])

uploaded_items = []

with tab1:
    files = st.file_uploader(
        "Select JPG, PNG or WebP images",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="individual_images",
    )

    if files:
        uploaded_items.extend(
            {
                "name": uploaded_file.name,
                "data": uploaded_file.getvalue(),
            }
            for uploaded_file in files
        )

with tab2:
    zip_file = st.file_uploader(
        "Upload a ZIP containing your image folder",
        type=["zip"],
        accept_multiple_files=False,
        key="folder_zip",
        help="On macOS: right-click a folder and choose Compress.",
    )

    if zip_file is not None:
        try:
            uploaded_items.extend(
                load_images_from_zip(zip_file.getvalue())
            )
        except zipfile.BadZipFile:
            st.error("The uploaded file is not a valid ZIP.")
        except Exception as exc:
            st.error(f"Could not read the ZIP: {exc}")


uploaded_items = deduplicate_names(uploaded_items)


# ---------- Options ----------
st.divider()

st.subheader("Conversion Settings")

col1, col2, col3 = st.columns([1, 1.4, 1.6])

with col1:
    output_format = st.selectbox(
        "Convert to",
        ["JPG", "WEBP", "PNG"],
        index=0,
    )

with col2:
    quality = st.slider(
        "Quality / compression",
        min_value=1,
        max_value=100,
        value=85,
        step=1,
    )

with col3:
    only_if_smaller = st.toggle(
        "Only keep converted file when smaller",
        value=True,
    )

if output_format == "PNG":
    st.warning(
        "PNG is lossless. The slider changes compression effort, not visual quality. "
        "For much smaller image files, WebP is normally the better option."
    )


# ---------- Input summary ----------
total_input_size = sum(len(item["data"]) for item in uploaded_items)

m1, m2, m3 = st.columns(3)

with m1:
    st.metric("Images loaded", f"{len(uploaded_items):,}")

with m2:
    st.metric("Input size", human_size(total_input_size))

with m3:
    st.metric("Output format", output_format)


with st.expander("Preview file list"):
    if not uploaded_items:
        st.write("No images uploaded yet.")
    else:
        for item in uploaded_items[:250]:
            st.write(f"• {item['name']}")

        if len(uploaded_items) > 250:
            st.caption(
                f"Showing 250 of {len(uploaded_items):,} files."
            )


# ---------- Conversion ----------
st.divider()

convert_clicked = st.button(
    "🚀 Convert Images",
    type="primary",
    use_container_width=True,
    disabled=(len(uploaded_items) == 0),
)

if convert_clicked:
    progress_bar = st.progress(0)
    progress_text = st.empty()

    converted_files = []
    skipped_files = []
    failed_files = []

    converted_original_size = 0
    converted_output_size = 0

    total_files = len(uploaded_items)

    for index, item in enumerate(uploaded_items, start=1):
        try:
            original_data = item["data"]
            original_size = len(original_data)

            converted_data = convert_image(
                original_data,
                output_format,
                quality,
            )

            new_size = len(converted_data)

            if only_if_smaller and new_size >= original_size:
                skipped_files.append(
                    {
                        "name": item["name"],
                        "reason": "Converted image would not be smaller",
                        "original_size": original_size,
                        "new_size": new_size,
                    }
                )
            else:
                converted_files.append(
                    {
                        "name": output_filename(
                            item["name"],
                            output_format,
                        ),
                        "data": converted_data,
                        "original_size": original_size,
                        "new_size": new_size,
                    }
                )

                converted_original_size += original_size
                converted_output_size += new_size

        except Exception as exc:
            failed_files.append(
                {
                    "name": item["name"],
                    "reason": str(exc),
                }
            )

        progress_bar.progress(index / total_files)
        progress_text.text(
            f"Processing {index:,} of {total_files:,} images..."
        )

    progress_text.empty()

    bytes_saved = max(
        0,
        converted_original_size - converted_output_size,
    )

    percent_saved = (
        (bytes_saved / converted_original_size) * 100
        if converted_original_size
        else 0
    )

    st.success("Conversion complete.")

    r1, r2, r3, r4 = st.columns(4)

    with r1:
        st.metric("Converted", f"{len(converted_files):,}")

    with r2:
        st.metric("Skipped", f"{len(skipped_files):,}")

    with r3:
        st.metric("Errors", f"{len(failed_files):,}")

    with r4:
        st.metric(
            "Space saved",
            f"{human_size(bytes_saved)} ({percent_saved:.1f}%)",
        )

    if converted_files:
        zip_output = io.BytesIO()

        with zipfile.ZipFile(
            zip_output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for converted in converted_files:
                archive.writestr(
                    converted["name"],
                    converted["data"],
                )

        zip_output.seek(0)

        st.download_button(
            label="⬇️ Download Converted Images ZIP",
            data=zip_output.getvalue(),
            file_name=f"converted_{output_format.lower()}_images.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )

    if converted_files:
        with st.expander("Converted files"):
            for converted in converted_files[:250]:
                old_size = converted["original_size"]
                new_size = converted["new_size"]

                reduction = (
                    (1 - (new_size / old_size)) * 100
                    if old_size
                    else 0
                )

                st.write(
                    f"✅ {converted['name']} — "
                    f"{human_size(old_size)} → "
                    f"{human_size(new_size)} "
                    f"({reduction:.1f}% smaller)"
                )

    if skipped_files:
        with st.expander("Skipped files"):
            for skipped in skipped_files[:250]:
                st.write(
                    f"⏭️ {skipped['name']} — "
                    f"{skipped['reason']}"
                )

    if failed_files:
        with st.expander("Errors", expanded=True):
            for failed in failed_files:
                st.error(
                    f"{failed['name']}: {failed['reason']}"
                )
'''

requirements = """streamlit>=1.39,<2
Pillow>=10.4
"""

readme = """# Image Optimizer & Converter

Deployment-ready Streamlit Cloud application.

## Files to upload to your GitHub repository

- `app.py`
- `requirements.txt`

## Streamlit Community Cloud

Set the Main file path to:

`app.py`

## How the hosted version works

A hosted Streamlit app cannot directly browse folders on the user's computer.

The app therefore supports:

1. Uploading multiple JPG, JPEG, PNG or WebP files.
2. Uploading a ZIP containing a complete image folder.
3. Choosing JPG, WebP or PNG output.
4. Choosing quality/compression.
5. Downloading all converted files as one ZIP.

The application does not create any fixed local directories and does not use
Tkinter or Finder APIs, so it is compatible with Streamlit Community Cloud.
"""

(out / "app.py").write_text(app_py, encoding="utf-8")
(out / "requirements.txt").write_text(requirements, encoding="utf-8")
(out / "README.md").write_text(readme, encoding="utf-8")

zip_path = Path("/mnt/data/Image_Optimizer_Streamlit_FIXED.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(out / "app.py", arcname="app.py")
    z.write(out / "requirements.txt", arcname="requirements.txt")
    z.write(out / "README.md", arcname="README.md")

print("Created:", zip_path)
print("app.py lines:", len(app_py.splitlines()))
print("requirements:")
print(requirements)
