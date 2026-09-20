# fconv v1.0.0 发布说明

> 首个公开版本。本地运行、文件不上传的格式转换工具。
> 发布日期：2026-09-20

## 一句话

图片 / 文档 / 视频 / 音频 / PDF 一个入口互转，三步操作，文件全程不离开你的电脑。

## 亮点

- **201 个格式对全部实测通过** —— 不是「声明支持」，是每一个方向都跑过真实转换并校验了产物
- **转换历史持久化** —— 每次任务的源文件、转换方向、结果、耗时都记在本机，刷新页面不丢
- **错误提示说人话** —— 坏文件、空文件、不支持的方向、超大文件，都是明确中文提示，不给堆栈
- **自带便携入口套件** —— 无窗口启动 / 最小化启动 / 调试启动 / 停止 / 安装到桌面 / 下载新版 / 打包，双击即用
- **全程离线** —— 只监听 `127.0.0.1`，不联网、不上传、不埋点

## 主要修复

| 问题 | 影响 | 处理 |
|---|---|---|
| 视频 → WebM 全部失败 | 9 个转换方向产出 0 字节文件 | 按容器选编码器（WebM = VP9 + Opus），并保留 VP8 回退 |
| PDF 转图片缺依赖时写坏文件 | 把文字写进 `.png`，产物打不开 | 明确报「缺少可选依赖 PyMuPDF」并给安装命令 |
| RIFF 容器误判 | WebP / AVI 被识别成 WAV | 按偏移 8 的 FourCC 正确区分 |
| 改名文件识别不了 | `.png` 里其实是 JPEG 时判断错误 | 魔数优先，扩展名兜底 |
| 文本转换静默拷贝 | `txt → csv` 原样复制、扩展名与内容对不上 | 重写为中转表示，49 个方向各有真实实现 |
| 上传文件名未净化 | 存在路径穿越风险 | 统一净化，保留中文与空格 |

## 新增

- 转换历史与运行日志（`logs/history.jsonl`、`logs/fconv.log`）+ `GET /api/history`
- 界面底部「转换记录」面板
- `benchmarks/smoke_test.py`：201 个格式对真实转换矩阵
- `tests/test_web_api.py`：Flask 测试客户端 API 测试
- `src/fconv/ffmpeg.py`：FFmpeg 定位封装（环境变量 → 项目内 → PATH）
- `python -m fconv` 入口、`create_app()` 工厂函数
- 工程规范文件：`.gitattributes`、`CODE_OF_CONDUCT.md`、issue / PR 模板、CI 工作流

## 安装 / 升级

**便携版**：解压 `fconv-portable-v1.0.0.zip` → 双击 `启动fconv.vbs`。

**源码**：

```bash
git clone https://github.com/x1303145921/fconv.git
cd fconv
pip install -r requirements.txt
python src/web/server.py
```

从 0.2.0 升级：直接覆盖文件即可，版本号已统一到 `src/fconv/__init__.py` 一处。

## 环境要求

Windows 10/11 · Python 3.10+ · Pillow / pypdf / Flask
可选：PyYAML（YAML 方向）、PyMuPDF（PDF→图片，AGPL）、FFmpeg（音视频）

## 自检结果

| 项目 | 结果 |
|---|---|
| 单元测试 | 115 / 115 通过 |
| API 端到端 | 14 / 14 通过 |
| 浏览器交互 | 12 / 12 通过 |
| 格式对矩阵 | 201 / 201 通过 |
| 性能基准 | 图片 9/9 · 文本 8/8 · 音视频 7/7 · 批量 100% · 异常 4/4 |

## 已知限制

- 仅验证 Windows；macOS / Linux 未适配
- 音视频需要自备 FFmpeg（本项目不分发）
- PDF → 图片需要 AGPL 的 PyMuPDF（不随包分发）
- DOCX / XLSX / PPTX 可被识别但不支持转换
- 视频无法直接提取音轨（mp4 → mp3 不在支持范围内）
- GIF 导出固定 10fps / 宽 480
- 扫描件 PDF 无内嵌文字时，转 TXT 会得到空内容

## 许可证

MIT © 2026 fconv contributors
第三方组件见 `THIRD-PARTY-NOTICES.txt`。

## 校验

下载后建议核对 SHA256（发布时在 Release 页给出）。便携包不包含任何可执行二进制，
只有 Python 源码、脚本与图标资源。
