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
  outputFormat: 'png' | 'jpeg'
  retention: '30m' | '24h' | '7d'
  source: File
  target: File
  watermarkEnabled: boolean
}

export interface CreatedTask {
  expiresAt: string
  status: string
  taskId: string
}

export async function createTask(input: CreateTaskInput): Promise<CreatedTask> {
  const form = new FormData()
  form.set('source', input.source)
  form.set('target', input.target)
  form.set('authorization_confirmed', String(input.authorizationConfirmed))
  form.set('output_format', input.outputFormat)
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
    typeof payload.expires_at !== 'string'
  ) {
    throw new Error('后端返回了无效的任务信息。')
  }
  return {
    taskId: payload.task_id,
    status: payload.status,
    expiresAt: payload.expires_at,
  }
}
