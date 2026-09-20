# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
格式约定：`新增` / `变更` / `修复` / `清理` / `已知限制`。

## [1.0.0] - 2026-09-20

首个公开版本。定位不变：**本地运行、文件不上传的格式转换工具**。
这一版把 0.2.0 的遗留问题清干净，并补齐了开源发布所需的全部工程件。

### 新增

- **转换历史（持久化）**：`logs/history.jsonl` 记录每次任务的源文件、转换方向、结果、
  失败原因、耗时、字节数；新增 `GET /api/history` 接口，界面底部新增「转换记录」面板。
- **运行日志**：`logs/fconv.log`（2MB × 3 份轮转），新增 `src/fconv/history.py` 统一管理。
- **`src/fconv/ffmpeg.py`**：FFmpeg 定位与调用封装，支持 `FCONV_FFMPEG` 环境变量与项目内
  `tools/ffmpeg/` 目录，音视频两条链路共用。
- **全格式矩阵冒烟测试** `benchmarks/smoke_test.py`：把声明支持的 **201 个格式对**逐个真跑，
  并对产物做真实性校验（图片能打开、JSON/XML/YAML 能解析、ZIP 非空）。
- **API 与浏览器自动化验收**：`tests/test_web_api.py`（Flask 测试客户端）与
  `tests/test_web_api.py` 之外的浏览器交互检查（上传 → 转换 → 下载 → 刷新后历史仍在 → 错误路径）。
- **工程规范文件**：`.gitattributes`、`CODE_OF_CONDUCT.md`、`.github` 下 issue / PR 模板与
  CI 工作流、`requirements-dev.txt`、`docs/RELEASE_NOTES-v1.0.0.md`。
- **`python -m fconv`** 入口，以及 `create_app()` 工厂函数（方便 WSGI 部署）。

### 变更

- **版本号统一到 1.0.0**，唯一来源为 `fconv.__version__`：CLI、`/api/health`、界面页脚、
  打包脚本全部从它读，不再各写一份。
- **文本转换重写为中转表示（pivot）**：源格式 → Python 对象 → 目标格式。
  7 种格式 × 7 种格式共 49 个方向都有明确实现，不再「没写分支就原样拷贝」。
- **错误码体系补全**：新增 `file_too_large`，错误一律以 `ConvertResult` 返回，
  转换器内部异常不会穿透到服务层。
- **上传目录改为「一任务一子目录」**：出错提示里显示的是用户原本的文件名，不再带任务号前缀。
- **批量转换**支持 `output_dir` 指定输出目录，结果按输入顺序返回，ZIP 内同名文件自动加序号。
- **Web 服务**：新增 413/404/500 的 JSON 化错误响应、上传目录过期清理（默认 24 小时）、
  单请求上限提高到 200MB、`/api/health` 增加版本号与 FFmpeg 可用性。
- **命令输出改为 ASCII 标记**（`[OK]` / `[FAIL]`），避免 Windows GBK 控制台把 emoji 打崩。

### 修复

- **视频 → WebM 全部失败**：此前对所有容器都使用 `libx264 + aac`，把 H.264 塞进 WebM 是非法组合，
  产出 0 字节文件。现在按容器选编码器（WebM 用 VP9 + Opus，AVI 用 mpeg4 + mp3，WMV 用 wmv2 + wmav2），
  并保留 VP9 不可用时回退 VP8 的兜底。
- **GIF 转换遗留临时文件**：两遍法生成的调色板文件用完即删（原先会留在输出目录）。
- **PDF 转图片缺依赖时产出坏文件**：旧实现会在缺少 PyMuPDF 时把文字写进 `.png` 文件；
  现在明确返回「缺少可选依赖 PyMuPDF」并给出安装命令，不产出坏文件。
- **嗅探器 RIFF 容器误判**：`RIFF` 在旧字典里被 WAV/WebP/AVI 反复覆盖，导致 WebP、AVI 被误判成 WAV；
  现在按偏移 8 的 FourCC 正确区分，并补齐 ISO-BMFF（MP4 / MOV / M4A）分支。
- **嗅探器 `_verify_magic` 形同虚设**：旧实现无论如何都返回 `True`；现在以魔数为准，改名文件能识别出来。
- **magic 表缺 `fLaC` / `\xff\xf3` 等分支**，纯音频文件靠扩展名兜底。
- **路径穿越**：上传文件名统一净化（`../../x.png` → `x.png`），保留中文与空格。
- **文本转换对不支持的方向静默拷贝**：现在返回 `format_not_supported` 或给出真实转换结果。
- **HTML → 文本**会先剥掉 `<script>` / `<style>` 内容，并正确反转义实体。

### 清理

- 删除硬编码的本机 FFmpeg 路径与调试脚本里的绝对路径（开源版必须能在别人机器上跑）。
- 删除重复实现：`cli.py` 与 `batch.py` 各有一份批量转换逻辑，现只保留一处。
- 清掉临时产物、`__pycache__`、`benchmarks/_work` 等中间文件；`.gitignore` 覆盖运行产物、
  日志、上传目录、打包产物与本机配置。
- 旧的图标（重做前的版本）与废弃的 `run_fconv.py` 一并移除。

### 已知限制

- 仅验证 Windows 10/11；macOS / Linux 未适配（路径与启动脚本按 Windows 写）。
- 音视频转换依赖外部 FFmpeg，本项目**不分发**其二进制。
- PDF → 图片需要 AGPL 许可的 PyMuPDF，默认不装。
- GIF 导出固定 10fps、宽 480，暂未做参数化。
- DOCX / XLSX / PPTX 能被识别（ZIP 型 Office 文档），但**不支持转换**，会明确返回不支持。
- 批量任务的进度是「已完成个数」，没有逐文件百分比（单文件转换已有）。
- 转换历史默认保留最近 2000 条（超出自动裁剪）。
- 扫描件 PDF 没有内嵌文字时，PDF → TXT 会得到空内容（仅给出提示，暂不内置 OCR）。

## [0.2.0] - 2026-09-20

### 图标

- **图标重制**：换成 X 风格（纯黑圆底 + 白色字母 f）。字形取自外部参考图，
  由 `scripts/make-icons.py` 自动完成「裁圆 → 换色 → 光学补偿 → 描摹矢量轮廓」，
  位图与 SVG 同源（轮廓一致度 0.978）。参考图存为 `assets/icon-source.webp`，可一键重建。

### 新增

- **Web 界面全面重构**：Build 极简风格，三步操作（拖入 → 选格式 → 转换下载）。
- **真实后端接入**：前端调用 Flask API（`/api/convert`、`/api/batch-convert`、`/api/tasks`、`/api/download`）。
- **批量转换**：并发处理 + ZIP 打包下载（`src/fconv/batch.py`）。
- **性能基准测试**：`benchmarks/benchmark.py`。
- **API 端到端测试**：`tests/api_e2e.py`。
- **全新图标**：SVG / 多尺寸 PNG / 多尺寸 ICO。
- **便携版入口套件**：`启动fconv.vbs`、`启动fconv.bat`、`启动fconv-最小化.bat`、
  `停止fconv.bat`、`安装到桌面.bat`、`下载最新版.bat`、`build-portable.bat`、`start.bat`。
- **图标 / 启动器生成脚本**：`scripts/make-icons.py`、`make_launchers.py`、`build_vbs.py`、`fix_encoding.py`。

### 修复

- 路由注册把 `target_formats` 当入口，导致 `html→txt` 被误路由到 PDF 转换器（报 `invalid pdf header`）。
- `converters/pdf.py` 混入的重复代码片段，重写 `_extract_to_html`。
- PDF 转 HTML 补齐 HTML 特殊字符转义。
- `pyproject.toml` 重复的 optional-dependencies 合并。
- benchmark 脚本编码问题（改用 ASCII 状态标记）。

### 变更

- Web 服务默认端口从 5000 改为 **8765**，支持 `FCONV_PORT` 环境变量覆盖。

## [0.1.0] - 初始版本

- 基础 CLI：图片 / 文档 / PDF / 音视频转换。
- 格式嗅探（魔数 + 扩展名）。
- 数据驱动路由表。
