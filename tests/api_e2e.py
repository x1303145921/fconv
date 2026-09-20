"""端到端 API 验收测试：起服务后跑本脚本。"""
import io
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Windows 控制台窄编码（cp1252 / cp936 等）编不出 UTF-8 中文，先统一改成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - 非文本流时跳过
        pass

BASE = "http://127.0.0.1:8765"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return r.status, r.read()


def post_files(path, files, fields=None):
    """files: list of (fieldname, filename, bytes)"""
    boundary = "----fconvboundary" + str(int(time.time() * 1000))
    body = io.BytesIO()
    for name, value in (fields or {}).items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(f"{value}\r\n".encode())
    for field, filename, data in files:
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
        )
        body.write(b"Content-Type: application/octet-stream\r\n\r\n")
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        BASE + path,
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def make_png(w=120, h=90, color=(220, 40, 40)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def main():
    results = []

    # --- 0. 静态资源 ---
    for path in ["/", "/assets/icon.svg", "/assets/icon.png", "/favicon.ico", "/assets/favicon-32x32.png"]:
        try:
            st, data = get(path)
            results.append((f"GET {path}", st == 200 and len(data) > 0, f"{st}, {len(data)}B"))
        except Exception as e:
            results.append((f"GET {path}", False, str(e)))

    # --- 1. 单文件转换 png -> jpg ---
    st, data = post_files("/api/convert", [("file", "demo.png", make_png())], {"format": "jpg"})
    ok = st == 200
    task_id = None
    if ok:
        task_id = json.loads(data)["task_id"]
    results.append(("POST /api/convert (png->jpg)", ok, f"HTTP {st}, task={task_id}"))

    # 轮询
    final = None
    if task_id:
        for _ in range(60):
            time.sleep(0.3)
            st, data = get(f"/api/tasks/{task_id}")
            final = json.loads(data)
            if final["status"] in ("completed", "failed"):
                break
        good = final and final["status"] == "completed" and final["result"]["ok"]
        detail = "completed" if good else json.dumps(final, ensure_ascii=False)[:200]
        results.append(("轮询 /api/tasks/<id>", bool(good), detail))

        # 下载
        st, data = get(f"/api/download/{task_id}")
        results.append(("GET /api/download/<id>", st == 200 and len(data) > 100, f"{st}, {len(data)}B"))

    # --- 2. 文本转换 json -> csv ---
    js = json.dumps([{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}]).encode()
    st, data = post_files("/api/convert", [("file", "data.json", js)], {"format": "csv"})
    tid2 = json.loads(data)["task_id"] if st == 200 else None
    if tid2:
        for _ in range(60):
            time.sleep(0.3)
            st, data = get(f"/api/tasks/{tid2}")
            final = json.loads(data)
            if final["status"] in ("completed", "failed"):
                break
        st, dl = get(f"/api/download/{tid2}")
        text = dl.decode("utf-8", "replace")
        ok = final["status"] == "completed" and "name,age" in text and "Alice,25" in text
        results.append(("json->csv 内容校验", ok, text.strip().replace("\r\n", " | ")[:120]))

    # --- 3. 批量转换 ---
    files = [("files", f"b{i}.png", make_png(color=(20 + i * 20, 60, 200))) for i in range(4)]
    st, data = post_files("/api/batch-convert", files, {"format": "jpg"})
    ok = st in (200, 207)
    payload = json.loads(data) if ok else {}
    summary = payload.get("summary", {})
    dl = payload.get("download")
    results.append((
        "POST /api/batch-convert",
        ok and summary.get("success") == 4,
        f"HTTP {st}, {json.dumps(summary, ensure_ascii=False)}",
    ))
    if dl:
        st, data = get("/api/download-batch/" + dl["filename"])
        results.append(("GET /api/download-batch/<zip>", st == 200 and data[:2] == b"PK", f"{st}, {len(data)}B"))

    # --- 4. 异常处理 ---
    st, data = post_files("/api/convert", [], {})
    results.append(("空请求应被拒", st == 400, f"HTTP {st}"))

    bad = b"this is definitely not an image"
    st, data = post_files("/api/convert", [("file", "broken.jpg", bad)], {"format": "png"})
    tid = json.loads(data)["task_id"] if st == 200 else None
    if tid:
        for _ in range(60):
            time.sleep(0.3)
            st, data = get(f"/api/tasks/{tid}")
            final = json.loads(data)
            if final["status"] in ("completed", "failed"):
                break
        results.append((
            "损坏文件应失败且不崩",
            final["status"] == "failed" and bool(final.get("error")),
            (final.get("error") or "")[:80],
        ))

    # --- 5. 性能基准接口 ---
    st, data = post_files("/api/benchmark", [], {})
    if st == 200:
        bench = json.loads(data)
        s = bench["summary"]
        results.append(("POST /api/benchmark", s["failed"] == 0, json.dumps(s, ensure_ascii=False)))
    else:
        results.append(("POST /api/benchmark", False, f"HTTP {st}"))

    # 汇总
    print("=" * 72)
    print("fconv API 端到端验收")
    print("=" * 72)
    passed = 0
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} | {detail}")
        passed += 1 if ok else 0
    print("-" * 72)
    print(f"  合计：{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
