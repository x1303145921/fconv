# 贡献指南

感谢你愿意花时间改进 fconv！这份文档说明怎么提问题、怎么改代码、怎么加格式。

## 目录

- [报告问题](#报告问题)
- [开发环境](#开发环境)
- [开发流程](#开发流程)
- [代码风格](#代码风格)
- [添加一种新格式](#添加一种新格式)
- [提交前的自检清单](#提交前的自检清单)
- [行为准则](#行为准则)

## 报告问题

提 issue 前请先：

1. 搜索现有 issue，避免重复；
2. 确认是 bug 而不是用法问题（README 的「常见问题」先扫一眼）；
3. 提供可复现信息：
   - fconv 版本（界面页脚 / `fconv version` / `GET /api/health`）
   - 操作系统与 Python 版本
   - 源文件格式与目标格式
   - 报错原文（`logs/fconv.log` 里的相关几行最好）
   - **如果涉及文件内容，请先脱敏**——不要上传包含隐私的原始文件

## 开发环境

```bash
git clone https://github.com/x1303145921/fconv.git
cd fconv
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"
python -m pytest tests/ -q         # 应全绿
```

起服务看界面：

```bash
python src/web/server.py           # http://127.0.0.1:8765
```

## 开发流程

1. 从 `main` 开分支：`git checkout -b fix/pdf-fallback`
2. 改代码 + **补测试**（行为变更必须有测试覆盖）
3. 本地跑通：
   ```bash
   python -m pytest tests/ -q
   python benchmarks/smoke_test.py          # 有 FFmpeg 就加 --with-ffmpeg
   ```
4. 提交（见下面的提交信息约定）
5. 推送并开 PR，PR 描述里写清楚：改了什么、为什么、怎么验证的

### 提交信息约定

沿用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 前缀：

| 前缀 | 用途 |
|---|---|
| `feat:` | 新功能 |
| `fix:` | 修 bug |
| `docs:` | 只改文档 |
| `refactor:` | 重构，行为不变 |
| `test:` | 只改测试 |
| `chore:` | 构建 / 依赖 / 杂项 |

例：`fix: 视频转 webm 时改用 VP9+Opus，避免产出空文件`

## 代码风格

- 遵循 **PEP 8**，行宽 100 以内
- 全部使用 **type hints**（`from __future__ import annotations`）
- 面向用户的文案用**中文**、面向代码的标识符用英文
- 日志用 `logging`，不要 `print`（CLI 的用户输出除外）
- 异常不要穿透转换器：一律 `return ConvertResult.failure(ErrorCode.XXX, "中文原因")`
- 不要硬编码本机路径；需要外部程序时走 `fconv/ffmpeg.py` 那样的「环境变量 → 项目内 → PATH」查找

## 添加一种新格式

fconv 的格式路由是数据驱动的，加格式通常只要三步：

1. **写转换器**：在 `src/fconv/converters/` 下新增或扩展一个类，声明
   ```python
   class DocxConverter(Converter):
       source_formats = ["docx"]
       target_formats = ["txt", "html"]
   ```
   实现 `convert(self, src, dst, **options) -> ConvertResult`。
2. **注册**：在 `src/fconv/router.py` 的 `_register_builtin()` 里加上新类。
3. **测试**：在 `tests/` 补用例，并更新 README 的「支持的格式」表。

如果该格式需要新的外部依赖，请在 `THIRD-PARTY-NOTICES.txt` 里补一条许可说明——
**这一步不能省**，尤其是 AGPL / GPL 这类有传染性的许可。

## 提交前的自检清单

- [ ] `python -m pytest tests/ -q` 全绿
- [ ] 新增/修改的行为有对应测试
- [ ] `python benchmarks/smoke_test.py --with-ffmpeg` 无 FAIL
- [ ] 没有提交密钥、Token、个人绝对路径（搜一下 `C:\Users`、`D:\`）
- [ ] 没有提交 `logs/`、`src/uploads/`、`dist-portable/` 等运行产物
- [ ] 用户可见的文案是中文，且不带堆栈
- [ ] 版本号只在 `src/fconv/__init__.py` 改一处，别处引用

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)：
尊重他人、对事不对人、接受建设性批评。

---

再次感谢你的贡献！
