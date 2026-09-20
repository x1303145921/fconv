# 发布说明 · fconv

## 一键打包便携版

双击 **`build-portable.bat`**，产出 `dist-portable\fconv-portable-v<版本>.zip`。

- 版本号自动从 `pyproject.toml` 的 `version` 读取
- 打包内容：`src/`、`assets/`、`scripts/`、全部 `.bat` / `.vbs`、README / LICENSE / CHANGELOG 等
- 自动剔除 `src\uploads\`、`logs\` 与 `__pycache__`
- 若项目根有 `python\python.exe`（便携运行时），会一并打进包里，目标机免装 Python

## 发布流程（维护者清单）

1. 改版本号（**只有两处**）：`src/fconv/__init__.py` 的 `__version__` 与 `pyproject.toml` 的 `version`
2. 更新 `CHANGELOG.md`（新增一节；沿用 `新增` / `变更` / `修复` / `清理` / `已知限制` 的格式）
3. 跑发布前自检（一条命令就能告诉你“能不能发”）：
   ```bash
   python scripts/check_release.py --strict
   ```
4. 跑全量测试：
   ```bash
   python -m pytest tests/ -q
   python benchmarks/smoke_test.py --with-ffmpeg
   python benchmarks/benchmark.py
   ```
5. 双击 `build-portable.bat` 打包
6. 校验便携包：解压到空目录 → 双击 `启动fconv.vbs` → 转一次文件 → 双击 `安装到桌面.bat` 看看图标
7. 安全体检：搜密钥 / Token / 个人绝对路径；确认 `logs/`、`src/uploads/`、`dist-portable/` 未入库
8. 打 tag `v<版本>` 并推送；把 zip 传到 GitHub Releases，Release 说明直接用
   `docs/RELEASE_NOTES-v<版本>.md`

## 版本号在哪几处

| 位置 | 说明 |
|---|---|
| `src/fconv/__init__.py` | **唯一运行时来源**，CLI / Web / 界面页脚都读它 |
| `pyproject.toml` | 打包元数据（上表两处必须一致，`check_release.py` 会拦） |

CLI、`/api/health`、界面页脚、`build-portable.bat`、`下载最新版.bat` 都不再各写一份：
打包脚本与下载器都是**运行时**去 `pyproject.toml` 里读。

## 当前版本

| 项目 | 值 |
|---|---|
| 版本 | v1.0.0 |
| 便携包 | `fconv-portable-v1.0.0.zip` |
| 下载脚本 | `下载最新版.bat`（版本号运行时读 `pyproject.toml`） |
| 发行自检 | `python scripts/check_release.py --strict` |
| 验收报告 | `docs/验收报告-v1.0.0.md` |
| 仓库 | <https://github.com/x1303145921/fconv> |
| 发布说明 | `docs/RELEASE_NOTES-v1.0.0.md` |
