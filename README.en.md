# fconv

**Local file-format converter — images, documents, video, audio and PDF in one place.**
Everything runs on your own machine: nothing is uploaded, nothing phones home.

<p align="center">
  <img src="assets/icon.svg" width="80" alt="fconv">
</p>

## Why

Converting a PNG to JPG should not require installing a suite of tools, and online
converters mean uploading your files to someone else's server. `fconv` keeps all of
that on your machine, behind a small web UI, a CLI, or a Python API.

## Features

- **One entry point** — image / document / video / audio / PDF conversions
- **Three steps** — drop a file → pick a target format → convert and download
- **Batch mode** — drop many files, they convert concurrently and download as one ZIP
- **Real format sniffing** — magic numbers first, so renamed files are detected correctly
- **Readable errors** — corrupt, empty or unsupported files produce clear messages, never a stack trace
- **Persistent history** — every conversion is logged locally (`logs/history.jsonl`)
- **Offline by design** — the server binds to `127.0.0.1` only

## Supported formats

| Kind | Formats |
|---|---|
| Image | PNG, JPG, GIF, BMP, TIFF, WEBP, ICO |
| Document | TXT, MD, HTML, JSON, CSV, XML, YAML |
| PDF | PDF → TXT / MD / HTML (pypdf); PDF → PNG / JPG (optional PyMuPDF) |
| Video | MP4, MKV, AVI, MOV, WMV, FLV, WEBM (+ GIF export) — needs FFmpeg |
| Audio | MP3, WAV, OGG, FLAC, AAC, M4A (WMA as input) — needs FFmpeg |

201 format pairs, all verified with real conversions.

## Quick start

### Portable build (Windows)

1. Unzip `fconv-portable-v1.0.0.zip`
2. Double-click `启动fconv.vbs` (starts silently and opens the browser)
3. Optional: double-click `安装到桌面.bat` to create shortcuts

### From source

```bash
git clone https://github.com/x1303145921/fconv.git
cd fconv
pip install -r requirements.txt
python src/web/server.py     # http://127.0.0.1:8765
```

### CLI

```bash
pip install -e .

fconv input.png output.jpg
fconv batch *.png --format webp -o out/
fconv formats
fconv detect somefile.bin
```

## Requirements

Windows 10/11 · Python 3.10+ · Pillow, pypdf, Flask · optional PyYAML, PyMuPDF, FFmpeg.

## Tests

```bash
python -m pytest tests/ -q                     # 116 unit tests
python tests/api_e2e.py                        # 14 API checks (server running)
python benchmarks/smoke_test.py --with-ffmpeg  # 201 real conversions
```

## License

[MIT](LICENSE) © 2026 颜 (<https://github.com/x1303145921>).
Third-party components: see [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).

> The full documentation (and the UI) is in Chinese; see [README.md](README.md).
