const API_ROOT = '/api/v1'
const CSRF_HEADER = 'X-CSRF-Token'

type JsonObject = Record<string, unknown>

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new Error('后端返回了无法识别的数据。')
  }
}

export async function checkHealth(signal: AbortSignal): Promise<boolean> {
  const response = await fetch(`${API_ROOT}/health`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)
  return response.ok && isObject(payload) && payload.status === 'ok'
}

export async function establishSession(signal: AbortSignal): Promise<string> {
  const response = await fetch(`${API_ROOT}/session`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)
  if (
    !response.ok ||
    !isObject(payload) ||
    typeof payload.csrf_token !== 'string' ||
    payload.csrf_token.length < 32
  ) {
    throw new Error('无法建立受保护的本地会话。')
  }
  return payload.csrf_token
}

export interface CreateTaskInput {
  authorizationConfirmed: boolean
  csrfToken: string
  jpegQuality: number
  outputFormat: 'png' | 'jpeg'
  retention: '30m' | '1h' | '3h' | '6h' | '12h' | '24h'
  source: File
  target: File
  watermarkEnabled: boolean
}

export interface CreatedTask {
  expiresAt: string
  jpegQuality: number
  outputFormat: 'png' | 'jpeg'
  status: TaskStatus
  taskId: string
}

export interface AvailableResult {
  completedAt: string
  expiresAt: string
  outputFormat: 'png' | 'jpeg'
  taskId: string
}

export type TaskStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'timed_out'
  | 'expired'
  | 'deleted'

export type WorkflowNode = 'validate' | 'prepare' | 'simulate' | 'inspect' | 'export'

export interface TaskEvent {
  currentNode: WorkflowNode | null
  errorCode: string | null
  status: TaskStatus
  taskId: string
  version: number
}

export async function createTask(input: CreateTaskInput): Promise<CreatedTask> {
  const form = new FormData()
  form.set('source', input.source)
  form.set('target', input.target)
  form.set('authorization_confirmed', String(input.authorizationConfirmed))
  form.set('output_format', input.outputFormat)
  form.set('jpeg_quality', String(input.jpegQuality))
  form.set('watermark_enabled', String(input.watermarkEnabled))
  form.set('retention', input.retention)

  const response = await fetch(`${API_ROOT}/tasks`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { [CSRF_HEADER]: input.csrfToken },
    body: form,
  })
  const payload = await readJson(response)
  if (!response.ok) {
    const detail =
      isObject(payload) && typeof payload.detail === 'string'
        ? payload.detail
        : '任务提交失败，请检查图片与处理选项。'
    throw new Error(detail)
  }
  if (
    !isObject(payload) ||
    typeof payload.task_id !== 'string' ||
    typeof payload.status !== 'string' ||
    !TASK_STATUSES.has(payload.status as TaskStatus) ||
    typeof payload.expires_at !== 'string' ||
    (payload.output_format !== 'png' && payload.output_format !== 'jpeg') ||
    typeof payload.jpeg_quality !== 'number' ||
    !Number.isInteger(payload.jpeg_quality) ||
    payload.jpeg_quality < 5 ||
    payload.jpeg_quality > 100
  ) {
    throw new Error('后端返回了无效的任务信息。')
  }
  return {
    taskId: payload.task_id,
    status: payload.status as TaskStatus,
    expiresAt: payload.expires_at,
    jpegQuality: payload.jpeg_quality,
    outputFormat: payload.output_format,
  }
}

const TASK_STATUSES = new Set<TaskStatus>([
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
  'expired',
  'deleted',
])
const WORKFLOW_NODES = new Set<WorkflowNode>([
  'validate',
  'prepare',
  'simulate',
  'inspect',
  'export',
])

export function parseTaskEvent(serialized: string): TaskEvent {
  let payload: unknown
  try {
    payload = JSON.parse(serialized)
  } catch {
    throw new Error('任务事件不是有效的 JSON。')
  }
  return parseTaskState(payload, '任务事件结构无效。')
}

function parseTaskState(payload: unknown, invalidMessage: string): TaskEvent {
  if (
    !isObject(payload) ||
    typeof payload.task_id !== 'string' ||
    typeof payload.version !== 'number' ||
    typeof payload.status !== 'string' ||
    !TASK_STATUSES.has(payload.status as TaskStatus) ||
    !(
      payload.current_node === null ||
      (typeof payload.current_node === 'string' &&
        WORKFLOW_NODES.has(payload.current_node as WorkflowNode))
    ) ||
    !(payload.error_code === null || typeof payload.error_code === 'string')
  ) {
    throw new Error(invalidMessage)
  }
  return {
    taskId: payload.task_id,
    version: payload.version,
    status: payload.status as TaskStatus,
    currentNode: payload.current_node as WorkflowNode | null,
    errorCode: payload.error_code,
  }
}

export async function cancelTask(
  taskId: string,
  csrfToken: string,
): Promise<TaskEvent> {
  const response = await fetch(
    `${API_ROOT}/tasks/${encodeURIComponent(taskId)}/cancel`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        [CSRF_HEADER]: csrfToken,
      },
    },
  )
  const payload = await readJson(response)
  if (!response.ok) {
    const detail =
      isObject(payload) && typeof payload.detail === 'string'
        ? payload.detail
        : '无法取消当前任务。'
    throw new Error(detail)
  }
  return parseTaskState(payload, '后端返回了无效的取消状态。')
}

export async function getTask(taskId: string): Promise<TaskEvent> {
  const response = await fetch(`${API_ROOT}/tasks/${encodeURIComponent(taskId)}`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  const payload = await readJson(response)
  if (!response.ok) {
    const detail =
      isObject(payload) && typeof payload.detail === 'string'
        ? payload.detail
        : '无法确认任务状态。'
    throw new Error(detail)
  }
  return parseTaskState(payload, '后端返回了无效的任务状态。')
}

export async function fetchTaskResult(
  taskId: string,
  signal: AbortSignal,
): Promise<Blob> {
  const response = await fetch(
    `${API_ROOT}/tasks/${encodeURIComponent(taskId)}/result`,
    {
      credentials: 'same-origin',
      headers: { Accept: 'image/png,image/jpeg' },
      signal,
    },
  )
  if (!response.ok) {
    const payload = await readJson(response)
    const detail =
      isObject(payload) && typeof payload.detail === 'string'
        ? payload.detail
        : '结果暂时不可用。'
    throw new Error(detail)
  }
  const contentType = response.headers.get('Content-Type')?.split(';', 1)[0]
  if (contentType !== 'image/png' && contentType !== 'image/jpeg') {
    throw new Error('后端返回了无法预览的结果格式。')
  }
  const result = await response.blob()
  if (result.size === 0) {
    throw new Error('后端返回了空的结果文件。')
  }
  return result
}

export async function listAvailableResults(
  signal?: AbortSignal,
): Promise<AvailableResult[]> {
  const response = await fetch(`${API_ROOT}/tasks/results`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)
  if (!response.ok) {
    throw new Error('无法读取本地结果列表。')
  }
  if (!Array.isArray(payload)) {
    throw new Error('后端返回了无效的结果列表。')
  }
  return payload.map((item) => {
    if (
      !isObject(item) ||
      typeof item.task_id !== 'string' ||
      item.task_id.length === 0 ||
      typeof item.completed_at !== 'string' ||
      !Number.isFinite(Date.parse(item.completed_at)) ||
      typeof item.expires_at !== 'string' ||
      !Number.isFinite(Date.parse(item.expires_at)) ||
      (item.output_format !== 'png' && item.output_format !== 'jpeg')
    ) {
      throw new Error('后端返回了无效的结果条目。')
    }
    return {
      taskId: item.task_id,
      completedAt: item.completed_at,
      expiresAt: item.expires_at,
      outputFormat: item.output_format,
    }
  })
}

export async function deleteTaskResult(
  taskId: string,
  csrfToken: string,
): Promise<void> {
  const response = await fetch(`${API_ROOT}/tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      [CSRF_HEADER]: csrfToken,
    },
  })
  if (response.ok) {
    return
  }
  const payload = await readJson(response)
  const detail =
    isObject(payload) && typeof payload.detail === 'string'
      ? payload.detail
      : '无法清除本地图片与结果。'
  throw new Error(detail)
}

export function taskResultUrl(taskId: string): string {
  return `${API_ROOT}/tasks/${encodeURIComponent(taskId)}/result`
}

export function taskEventsUrl(taskId: string): string {
  return `${API_ROOT}/tasks/${encodeURIComponent(taskId)}/events`
}
