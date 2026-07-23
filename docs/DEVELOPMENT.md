# 本地开发指南

本文档面向 Windows PowerShell。所有命令均在仓库根目录执行。

## 当前基线

- Python：3.14.6
- Python 环境：项目根目录 `.venv/`
- Python 依赖管理器：uv 0.10.6
- uv 本机审计 SHA-256：`F91929F6C38F9216A96DCD5E208D559BCC0354E9F08E73524889C8211B5DD1A4`
- 后端：FastAPI 0.139.2、Uvicorn 0.51.0

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

## 当前不包含的能力

这一骨架尚未安装人脸检测、身份向量、换脸模型、ONNX Runtime GPU 或 ComfyUI。健康检查成功只代表 Web 后端和工程打包链路正常，不代表换脸能力已经实现。
