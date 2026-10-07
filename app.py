import io
import os
import platform
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
from PIL import Image, ImageOps

SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp'}

st.set_page_config(page_title='Local Image Optimizer', page_icon='🖼️', layout='wide')

st.markdown('''
<style>
.block-container {max-width: 1200px; padding-top: 1.5rem; padding-bottom: 3rem;}
div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.2); padding: 12px; border-radius: 12px;}
div.stButton > button {min-height: 44px; border-radius: 10px; font-weight: 600;}
</style>
''', unsafe_allow_html=True)


def human_size(n):
    n = float(n)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024 or unit == 'TB':
            return f'{n:.1f} {unit}'
        n /= 1024


def format_eta(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}h {m}m'
    if m:
        return f'{m}m {s}s'
    return f'{s}s'


def mac_choose_folder(prompt):
    if platform.system() != 'Darwin':
        return None, 'Browse is optimized for macOS. Paste the folder path manually.'
    script = f'''tell application "System Events"
activate
set chosenFolder to choose folder with prompt "{prompt}"
return POSIX path of chosenFolder
end tell'''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return result.stdout.strip(), None
        err = result.stderr.strip()
        if '-128' in err:
            return None, None
        return None, err or 'Could not open folder picker.'
    except Exception as exc:
        return None, str(exc)


def scan_images(folder, recursive=True):
    iterator = folder.rglob('*') if recursive else folder.glob('*')
    return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED)


def has_transparency(img):
    return img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)


def flatten_rgb(img, background=(255, 255, 255)):
    if has_transparency(img):
        rgba = img.convert('RGBA')
        base = Image.new('RGBA', rgba.size, background + (255,))
        base.alpha_composite(rgba)
        return base.convert('RGB')
    return img.convert('RGB')


def ext_for(fmt):
    return '.jpg' if fmt == 'JPG' else f'.{fmt.lower()}'


def build_dest(src, input_root, output_root, fmt, keep_structure):
    ext = ext_for(fmt)
    if keep_structure:
        return (output_root / src.relative_to(input_root)).with_suffix(ext)
    return output_root / f'{src.stem}{ext}'


def encode_image(src, fmt, quality):
    with Image.open(src) as img:
        img.load()
        img = ImageOps.exif_transpose(img)
        out = io.BytesIO()
        if fmt == 'JPG':
            flatten_rgb(img).save(out, format='JPEG', quality=quality, optimize=True, progressive=True)
        elif fmt == 'WEBP':
            work = img.convert('RGBA') if has_transparency(img) else img.convert('RGB')
            work.save(out, format='WEBP', quality=quality, method=6)
        elif fmt == 'PNG':
            work = img.copy()
            if work.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
                work = work.convert('RGBA')
            compress_level = max(0, min(9, round((quality / 100) * 9)))
            work.save(out, format='PNG', optimize=True, compress_level=compress_level)
        else:
            raise ValueError(f'Unsupported format: {fmt}')
        return out.getvalue()


def process_one(src, dest, fmt, quality, only_if_smaller, overwrite, delete_original):
    try:
        src = Path(src)
        dest = Path(dest)
        old_size = src.stat().st_size
        same_path = src.resolve() == dest.resolve()

        if dest.exists() and not overwrite and not same_path:
            return {'status':'SKIPPED','src':str(src),'dest':str(dest),'old':old_size,'new':dest.stat().st_size,'reason':'Output already exists'}

        data = encode_image(src, fmt, quality)
        new_size = len(data)

        if only_if_smaller and new_size >= old_size:
            return {'status':'SKIPPED','src':str(src),'dest':str(dest),'old':old_size,'new':new_size,'reason':'Converted image would not be smaller'}

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + '.tmp')
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, dest)

        if delete_original and not same_path and src.exists():
            src.unlink()

        return {'status':'CONVERTED','src':str(src),'dest':str(dest),'old':old_size,'new':new_size,'reason':''}
    except Exception as exc:
        return {'status':'ERROR','src':str(src),'dest':str(dest),'old':0,'new':0,'reason':str(exc)}


if 'input_dir' not in st.session_state:
    st.session_state.input_dir = str(Path.home() / 'Downloads')
if 'output_dir' not in st.session_state:
    st.session_state.output_dir = str(Path.home() / 'Downloads' / 'optimized_images')

st.title('🖼️ Local Image Optimizer & Converter')
st.caption('For large local folders on your Mac — no uploads, no ZIPs, no cloud transfer.')

c1, c2 = st.columns(2)
with c1:
    st.subheader('Input folder')
    a, b = st.columns([5,1])
    with a:
        value = st.text_input('Input folder path', value=st.session_state.input_dir, label_visibility='collapsed', key='input_path')
        st.session_state.input_dir = value
    with b:
        if st.button('Browse', key='browse_input', use_container_width=True):
            selected, err = mac_choose_folder('Choose input image folder')
            if selected:
                st.session_state.input_dir = selected
                st.rerun()
            elif err:
                st.error(err)

with c2:
    st.subheader('Output folder')
    a, b = st.columns([5,1])
    with a:
        value = st.text_input('Output folder path', value=st.session_state.output_dir, label_visibility='collapsed', key='output_path')
        st.session_state.output_dir = value
    with b:
        if st.button('Browse', key='browse_output', use_container_width=True):
            selected, err = mac_choose_folder('Choose output folder')
            if selected:
                st.session_state.output_dir = selected
                st.rerun()
            elif err:
                st.error(err)

input_root = Path(st.session_state.input_dir).expanduser()
output_root = Path(st.session_state.output_dir).expanduser()

st.divider()
st.subheader('Conversion settings')

s1, s2, s3, s4 = st.columns([1,1.3,1.2,1.2])
with s1:
    fmt = st.selectbox('Convert to', ['JPG','WEBP','PNG'])
with s2:
    quality = st.slider('Quality / compression', 1, 100, 85, 1)
with s3:
    max_workers = min(12, os.cpu_count() or 8)
    workers = st.slider('Parallel workers', 1, max_workers, min(6, max_workers), 1)
with s4:
    recursive = st.toggle('Include subfolders', value=True)
    keep_structure = st.toggle('Keep folder structure', value=True)

x1, x2, x3 = st.columns(3)
with x1:
    only_if_smaller = st.toggle('Only save when output is smaller', value=True)
with x2:
    overwrite = st.toggle('Overwrite existing outputs', value=False)
with x3:
    delete_original = st.toggle('Delete original after success', value=False)

if fmt == 'PNG':
    st.info('PNG is lossless. The slider controls compression effort, not visual quality. WebP is better for much smaller files.')
if delete_original:
    st.warning('Delete Original is ON. A source file is deleted only after the converted output is written successfully.')

st.divider()

if not input_root.exists() or not input_root.is_dir():
    st.error('Input folder does not exist. Choose a valid folder.')
    st.stop()

with st.spinner('Scanning images...'):
    files = scan_images(input_root, recursive)

total_size = sum((p.stat().st_size for p in files if p.exists()), 0)

m1, m2, m3, m4 = st.columns(4)
m1.metric('Images found', f'{len(files):,}')
m2.metric('Input size', human_size(total_size))
m3.metric('Target format', fmt)
m4.metric('Workers', workers)

with st.expander('Preview files'):
    if not files:
        st.write('No JPG, JPEG, PNG or WebP images found.')
    for p in files[:200]:
        try:
            st.write(f'• {p.relative_to(input_root)}')
        except Exception:
            st.write(f'• {p}')
    if len(files) > 200:
        st.caption(f'Showing first 200 of {len(files):,} images.')

st.divider()

if st.button('🚀 Start Conversion', type='primary', use_container_width=True, disabled=not files):
    output_root.mkdir(parents=True, exist_ok=True)
    progress = st.progress(0)
    status_box = st.empty()
    detail_box = st.empty()
    start = time.time()
    results = []

    futures = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for src in files:
            dest = build_dest(src, input_root, output_root, fmt, keep_structure)
            fut = executor.submit(process_one, src, dest, fmt, quality, only_if_smaller, overwrite, delete_original)
            futures[fut] = src

        total = len(futures)
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            progress.progress(i / total)
            status_box.markdown(f'**Processed {i:,} / {total:,}** • {rate:.1f} images/sec • ETA {format_eta(eta)}')
            if result['status'] == 'ERROR':
                detail_box.error(f"Error: {Path(result['src']).name} — {result['reason']}")
            else:
                detail_box.caption(Path(result['src']).name)

    elapsed = time.time() - start
    converted = [r for r in results if r['status'] == 'CONVERTED']
    skipped = [r for r in results if r['status'] == 'SKIPPED']
    errors = [r for r in results if r['status'] == 'ERROR']
    old_total = sum(r['old'] for r in converted)
    new_total = sum(r['new'] for r in converted)
    saved = max(0, old_total - new_total)
    pct = (saved / old_total * 100) if old_total else 0

    st.success(f'Finished in {format_eta(elapsed)}.')
    r1, r2, r3, r4 = st.columns(4)
    r1.metric('Converted', f'{len(converted):,}')
    r2.metric('Skipped', f'{len(skipped):,}')
    r3.metric('Errors', f'{len(errors):,}')
    r4.metric('Space saved', f'{human_size(saved)} ({pct:.1f}%)')
    st.info(f'Output folder: {output_root}')

    if skipped:
        with st.expander('Skipped files'):
            for r in skipped[:500]:
                st.write(f"⏭️ {Path(r['src']).name} — {r['reason']}")
    if errors:
        with st.expander('Errors', expanded=True):
            for r in errors[:500]:
                st.error(f"{r['src']} — {r['reason']}")
