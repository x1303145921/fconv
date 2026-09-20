============================================================
 fconv  v1.0.0  文件格式转换工具（便携版 · 本地运行 · 不上传）
============================================================

【怎么用】
  1. 解压整个压缩包（不要只解一个文件）
  2. 双击「启动fconv.vbs」—— 没有黑窗口，自动打开浏览器
  3. 拖入文件 → 选目标格式 → 点转换 → 下载
  4. （可选）双击「安装到桌面.bat」在桌面生成带图标的快捷方式

【运行要求】
  Windows 10 / 11
  Python 3.10 及以上（如果包里有 python 文件夹，则免装）
  首次启动会自动补装依赖 Pillow / pypdf / Flask（需要联网一次）
  视频、音频转换还需要 FFmpeg（没装也不影响图片和文档转换）

【入口一览】
  启动fconv.vbs          无窗口启动（推荐日常使用）
  启动fconv-最小化.bat   最小化启动，保留一个可查看的小窗口
  启动fconv.bat          调试窗口启动，出问题看这里
  停止fconv.bat          停止后台服务，释放 8765 端口
  安装到桌面.bat         创建桌面快捷方式（带新图标）
  下载最新版.bat         从 GitHub 拉取最新便携包（三镜像自动切换）
  build-portable.bat     自己重新打包一份便携版
  start.bat              英文启动脚本

【常见问题】
  Q: 双击没反应 / 浏览器没打开？
  A: 改双击「启动fconv.bat」，错误信息会显示在黑窗口里。
     多半是没装 Python，或依赖没装上。

  Q: 提示「未找到 FFmpeg」？
  A: 音视频转换需要 FFmpeg。任选一种：
     ① 装好并加入 PATH；② 设置环境变量 FCONV_FFMPEG 指向 ffmpeg.exe；
     ③ 把 ffmpeg 放到本目录的 tools\ffmpeg\bin\ 下。
     图片和文档转换不受影响。

  Q: 提示「8765 端口被占用」？
  A: 启动脚本会自动清理占用该端口的旧进程；也可以先双击
     「停止fconv.bat」。想换端口：设置环境变量 FCONV_PORT=9000。

  Q: PDF 转图片报缺依赖？
  A: 需要可选依赖 PyMuPDF：pip install pymupdf
     （注意 PyMuPDF 是 AGPL-3.0 许可，本项目不分发它）

  Q: 转换记录在哪？
  A: 本目录下 logs\history.jsonl（运行日志 logs\fconv.log）。
     上传和产物放在 src\uploads\，默认 24 小时自动清理。

【隐私】
  服务只监听 127.0.0.1，只在本机浏览器可访问；不联网、不上传、不埋点。

【更多文档】
  README.md            完整说明（功能 / 安装 / 用法 / 接口 / 常见问题）
  CHANGELOG.md         版本更新记录
  THIRD-PARTY-NOTICES.txt  第三方组件与许可
  LICENSE               MIT 许可证

【项目主页】
  https://github.com/x1303145921/fconv
