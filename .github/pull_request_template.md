## 这个 PR 做了什么

<!-- 一句话说清改动目标 -->

## 改动类型

- [ ] 修 bug
- [ ] 新功能
- [ ] 重构（行为不变）
- [ ] 文档
- [ ] 测试 / 构建 / 杂项

## 怎么验证的

<!-- 贴命令和结果；界面改动请附截图 -->

```bash
python -m pytest tests/ -q
python benchmarks/smoke_test.py
```

## 自检清单

- [ ] `python -m pytest tests/ -q` 全绿
- [ ] 新增/修改的行为有测试覆盖
- [ ] 用户可见文案是中文，且不带堆栈
- [ ] 没有提交密钥、Token、个人绝对路径
- [ ] 没有提交 `logs/`、`src/uploads/`、`dist-portable/` 等产物
- [ ] 若引入新依赖，已更新 `THIRD-PARTY-NOTICES.txt` 与 `requirements*.txt`
- [ ] 版本号只在 `src/fconv/__init__.py` 改（如涉及发版）

## 关联 issue

<!-- 例如 Closes #12 -->
