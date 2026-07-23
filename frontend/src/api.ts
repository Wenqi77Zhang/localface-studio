const API_ROOT = '/api/v1'

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
