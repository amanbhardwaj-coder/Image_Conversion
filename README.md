# Local Image Optimizer for macOS

Built for large local image folders (including folders that are several GB).

## Features
- Direct input/output folder selection
- No upload and no ZIP required
- JPG / JPEG / PNG / WebP input
- JPG / PNG / WebP output
- Quality/compression slider
- Parallel processing
- Recursive subfolders
- Preserve folder structure
- Optional overwrite
- Optional delete-original-after-success
- Skip conversions that would be larger
- Progress, speed, ETA and space saved

## Start
Double-click `Start_Image_Optimizer.command`.

If macOS blocks it, right-click the file, choose **Open**, then confirm.

Or run:

```bash
cd /path/to/Image_Optimizer_Local_Mac
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

The app normally opens at `http://localhost:8501`.

The Browse buttons use the normal macOS folder chooser. If macOS asks for Automation/System Events permission, allow it.

For large folders, start with 4–8 workers. Test on a small sample before enabling **Delete original after success**.
