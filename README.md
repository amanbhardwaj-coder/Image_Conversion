
# Image Optimizer Streamlit

A local Streamlit tool for converting and reducing JPG, PNG and WebP images.

## Features

- Select input and output folders with Browse buttons
- JPG / PNG / WebP input support
- Convert to JPG, PNG or WebP
- Quality/compression slider
- Recursive subfolder scanning
- Option to preserve folder structure
- Skip files when the converted result is larger
- Overwrite control
- Progress bar and conversion summary
- Preserves transparency for PNG/WebP
- JPG conversion places transparent areas on a white background

## Install

Open Terminal in this folder and run:

```bash
python3 -m pip install -r requirements.txt
```

## Start

```bash
python3 -m streamlit run app.py
```

Your browser should open automatically.

## macOS folder picker

The Browse buttons use the native Tk folder picker available with most macOS Python installations.

If the Browse button does not open a picker, you can still paste the folder path directly into the Input/Output fields.
