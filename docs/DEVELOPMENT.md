# 本地开发指南

本文档面向 Windows PowerShell。所有命令均在仓库根目录执行。

## 当前基线

- Python：3.14.6
- Python 环境：项目根目录 `.venv/`
- Python 依赖管理器：uv 0.10.6
- uv 本机审计 SHA-256：`F91929F6C38F9216A96DCD5E208D559BCC0354E9F08E73524889C8211B5DD1A4`
- 后端：FastAPI 0.139.2、Uvicorn 0.51.0
- Node.js：项目内便携版 24.18.0 LTS
- npm：11.16.0
- Node.js 官方 ZIP SHA-256：`0AE68406B42D7725661DA979B1403EC9926DA205C6770827F33AAC9D8F26E821`
- 前端：React 19.2.8、TypeScript 6.0.3、Vite 8.1.5

上述 uv 哈希只记录本次目标设备实际执行文件，不能替代官方发布来源校验。后续编写全新设备初始化脚本时，仍需从官方来源下载并校验其发布资产。

## 创建独立环境

确认 Python 版本：

```powershell
py -3.14 --version
```

使用本机 Python 创建项目虚拟环境。项目内缓存参数可规避用户级 uv 缓存异常，并避免污染其他项目：

```powershell
uv venv .venv --python "D:\Program Files\Python\Python314\python.exe" --no-managed-python --cache-dir .tools/uv-cache
```

这里的 Python 路径是当前目标设备的实测路径。其他设备应先执行 `py -0p` 查看实际安装路径，不应照抄不存在的绝对路径。后续初始化脚本会自动完成这一步。

## 按锁文件同步依赖

首次同步需要访问 PyPI：

```powershell
uv sync --locked --cache-dir .tools/uv-cache --no-managed-python --no-python-downloads
```

`uv.lock` 记录直接依赖和间接依赖的精确版本与包哈希。`--locked` 表示配置与锁文件不一致时立即失败，而不是静默改变版本。

缓存完整后可以验证离线重建能力：

```powershell
uv sync --locked --offline --cache-dir .tools/uv-cache --no-managed-python --no-python-downloads
```

## 运行后端诊断

```powershell
.\.venv\Scripts\python.exe scripts\verify_backend.py
```

预期输出：

```text
{"status":"ok"}
```

该脚本在 `127.0.0.1:8765` 上短暂启动服务、请求健康端点并自动关闭，不读取图片、模型或设备身份信息。

## 启动开发服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn localface_studio.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后可访问：

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 本地 API 文档：<http://127.0.0.1:8000/api/docs>
- OpenAPI 契约：<http://127.0.0.1:8000/api/openapi.json>

不要把 `--host` 改成 `0.0.0.0`。后者会让同一网络中的其他设备尝试访问服务；在项目完成身份验证与网络安全评审之前不允许这样运行。

停止服务时，在运行窗口按 `Ctrl+C`。

## 前端环境

Node.js 便携包来自官方地址：

<https://nodejs.org/dist/v24.18.0/node-v24.18.0-win-x64.zip>

安装前必须将 ZIP 的 SHA-256 与同目录官方清单进行比较：

<https://nodejs.org/dist/v24.18.0/SHASUMS256.txt>

校验通过后，Node.js 位于项目根目录的 `.tools/node/`。该目录不会提交到 Git；全新设备的自动下载与校验脚本将在阶段 1 的 Windows 启动入口小节补齐。

在当前 PowerShell 会话中启用项目内 Node.js：

```powershell
$nodeDir = (Resolve-Path ".tools\node").Path
$env:Path = "$nodeDir;$env:Path"
```

严格按照锁文件安装前端依赖：

```powershell
Set-Location frontend
& "$nodeDir\npm.cmd" ci --cache ..\.tools\npm-cache
```

`npm ci` 不会自行修改 `package-lock.json`，配置与锁文件不一致时会失败，适合本地复现和未来的 GitHub Actions。项目内缓存参数可以避免依赖用户级 npm 缓存权限。

缓存完整后可以验证离线重建：

```powershell
& "$nodeDir\npm.cmd" ci --offline --cache ..\.tools\npm-cache
```

运行前端静态检查、TypeScript 编译和生产构建：

```powershell
& "$nodeDir\npm.cmd" run check
```

启动前端开发服务：

```powershell
& "$nodeDir\npm.cmd" run dev
```

页面只监听 <http://127.0.0.1:5173>，并将 `/api` 请求代理到 <http://127.0.0.1:8000>。因此应先在另一个 PowerShell 窗口启动后端。

回到仓库根目录后，可以自动验证页面和 API 代理并确保临时进程被关闭：

```powershell
Set-Location ..
.\.venv\Scripts\python.exe scripts\verify_frontend.py
```

预期输出：

```text
{"frontend":"ok","api_proxy":"ok"}
```

## 当前不包含的能力

这一骨架尚未安装人脸检测、身份向量、换脸模型、ONNX Runtime GPU 或 ComfyUI。页面和健康检查成功只代表前后端工程链路正常，不代表换脸能力已经实现。
