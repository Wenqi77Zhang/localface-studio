# 可选 ComfyUI 适配器

阶段 8 增加了默认关闭的进程外 ComfyUI 适配器。它通过 ComfyUI 官方 HTTP 路由上传输入、提交 API 格式工作流、轮询历史并取回结果；LocalFace Studio 不导入 ComfyUI 模块、不安装自定义节点，也不把 ComfyUI 或第三方模型打进默认应用。

官方协议依据：

- [ComfyUI OpenAPI](https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml)
- [ComfyUI 官方 API 示例](https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example_ws_images.py)

## 安全前提

启用前必须同时满足：

1. ComfyUI 只监听同机回环地址，例如 `http://127.0.0.1:8188`。
2. 每个自定义节点、模型和工作流均已单独核验来源、许可证和是否联网。
3. 使用 ComfyUI 的“保存为 API 格式”导出工作流，不使用普通 UI 工作流 JSON。
4. 工作流不包含下载器、命令执行器、任意脚本或需要网络访问的节点。
5. LocalFace Studio 进程对 ComfyUI 的 `input` 和 `output` 目录拥有读写与删除权限，以便任务结束后清理交换文件。

适配器只接受 `http` 回环地址，拒绝 HTTPS、公网、局域网、凭据、查询参数和非根路径。工作流包必须声明 `license_reviewed: true`、`network_access_required: false`，并列出允许的全部节点类。该声明是操作员审查记录，不是自动许可证证明。

## 准备工作流

复制 `config/comfyui-workflow.example.json` 为被 Git 忽略的 `config/comfyui-workflow.json`，然后：

1. 用实际 API 工作流替换 `prompt`。
2. 把来源图加载节点的文件值替换为 `__LOCALFACE_SOURCE_IMAGE__`。
3. 把目标图加载节点的文件值替换为 `__LOCALFACE_TARGET_IMAGE__`。
4. 把最终 `SaveImage` 节点的 `filename_prefix` 替换为 `__LOCALFACE_OUTPUT_PREFIX__`。
5. 将最终 `SaveImage` 节点 ID 写入 `result_node_id`。
6. 把实际出现的每一种 `class_type` 写入 `allowed_node_classes`。
7. 完成节点和模型许可证审查后，才保留 `license_reviewed: true`。

三个占位符必须各出现一次。适配器还会要求结果位于当前任务的隔离子目录、大小不超过 25 MB、可被安全解码且尺寸与目标图完全一致。

## 启用

在未提交的 `.env` 中配置：

```dotenv
LOCALFACE_WORKFLOW_BACKEND=comfyui
LOCALFACE_COMFYUI_URL=http://127.0.0.1:8188
LOCALFACE_COMFYUI_WORKFLOW_PATH=config/comfyui-workflow.json
LOCALFACE_COMFYUI_INPUT_DIRECTORY=D:\ComfyUI\input
LOCALFACE_COMFYUI_OUTPUT_DIRECTORY=D:\ComfyUI\output
```

重新启动 LocalFace Studio 后，`/api/v1/capabilities` 会显示 `workflow_backend` 为 `comfyui`。`model_integrity_verified` 始终为 `false`，因为 LocalFace Studio 无权替外部进程证明其模型完整性；工作流和交换目录就绪只反映为 `model_files_present: true`。

## 生命周期与失败行为

- 每个任务使用 `localface/<随机任务 ID>` 交换目录，不使用用户文件名。
- 结果下载回 LocalFace Studio 后重新写入 AI 编辑元数据，并按用户选择添加可见水印。
- 无论成功、失败或取消，适配器都会尝试删除 ComfyUI 队列/历史记录，并清除输入、输出交换目录。
- ComfyUI 断线、超时、节点拒绝、越界结果、超限结果、错误尺寸或非图片输出统一变为稳定错误 `comfyui_workflow_failed`，不会返回伪成功文件。
- ComfyUI 不存在或配置不完整时，LocalFace Studio API 仍能启动；默认原生后端完全不受影响。

## 当前验证边界

适配器已通过模拟 ComfyUI 协议的自动集成测试，包括占位符渲染、输出发布、元数据、水印和双侧交换目录清理。本仓库不附带 ComfyUI、自定义换脸节点或相应模型，因此不能声称任意第三方工作流已经通过真人画质或许可证验收。每引入一个具体工作流，都必须单独登记和复测。
