# 第三方组件声明

本文件记录 LocalFace Studio 源码安装路径中的直接依赖与独立可选组件。精确版本以 `uv.lock` 和 `frontend/package-lock.json` 为准；本摘要不替代各上游许可证全文。

## Python 运行依赖

| 组件 | 锁定版本 | 许可证 | 上游 |
| --- | ---: | --- | --- |
| FastAPI | 0.139.2 | MIT | https://github.com/fastapi/fastapi |
| HTTPX | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| OpenCV Python Headless | 5.0.0.93 | Apache-2.0 | https://github.com/opencv/opencv-python |
| Pillow | 12.3.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| pydantic-settings | 2.14.2 | MIT | https://github.com/pydantic/pydantic-settings |
| python-multipart | 0.0.32 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Uvicorn | 0.51.0 | BSD-3-Clause | https://github.com/Kludex/uvicorn |

## 可选原生研究依赖

| 组件 | 锁定版本 | 代码许可证 | 额外限制 |
| --- | ---: | --- | --- |
| InsightFace | 1.0.1 | MIT | 官方预训练权重不是 MIT；本项目使用的权重仅限非商业研究 |
| ONNX Runtime GPU | 1.26.0 | MIT | NVIDIA CUDA/cuDNN 组件适用各自许可证 |

## 前端直接依赖

| 组件 | 锁定版本 | 许可证 | 上游 |
| --- | ---: | --- | --- |
| React | 19.2.8 | MIT | https://github.com/facebook/react |
| React DOM | 19.2.8 | MIT | https://github.com/facebook/react |
| TypeScript | 6.0.3 | Apache-2.0 | https://github.com/microsoft/TypeScript |
| Vite | 8.1.5 | MIT | https://github.com/vitejs/vite |
| OxcLint | 1.75.0 | MIT | https://github.com/oxc-project/oxc |

前端锁文件还包含传递依赖，许可证集合包括 MIT、Apache-2.0、MPL-2.0、ISC、BSD-3-Clause 与 0BSD。若未来分发编译产物或安装包，必须随包保留完整的锁定版本许可证文本，特别复核 MPL-2.0 的 Lightning CSS 平台二进制。

## 独立组件与模型

- ComfyUI 是独立进程，官方代码为 GPL-3.0；默认应用不打包或导入它。自定义节点和模型必须逐项审查。
- YuNet 权重按 OpenCV Zoo 对应目录的 MIT 声明单独取得。
- SCRFD、ArcFace 与 InSwapper 官方预训练权重仅限非商业研究，且不会进入 Git、源码发布或安装包。
- Node.js 便携运行时当前只下载到被忽略的 `.tools/`，不进入仓库发行资产；若未来随安装包分发，必须附带 Node.js 自带许可证与第三方声明。

完整的模型文件名、来源、大小、SHA-256 和限制见[许可证与资产清单](../LICENSE_INVENTORY.md)。
