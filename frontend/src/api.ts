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

export interface BackendCapabilities {
  advisories: CapabilityAdvisory[]
  executionProvider: 'not_loaded' | 'cuda' | 'cpu'
  modelFilesPresent: boolean
  modelIntegrityVerified: boolean
  researchOnly: boolean
  runtimeLoaded: boolean
  readiness: 'ready' | 'setup_required' | 'simulation'
  workflowBackend: 'comfyui' | 'native-research' | 'simulation'
}

export type CapabilityAdvisory =
  | 'cpu_fallback'
  | 'external_runtime_not_configured'
  | 'external_runtime_unverified'
  | 'integrity_check_pending'
  | 'model_files_missing'
  | 'research_only'
  | 'runtime_load_pending'
  | 'simulation_only'

const CAPABILITY_ADVISORIES = new Set<CapabilityAdvisory>([
  'cpu_fallback',
  'external_runtime_not_configured',
  'external_runtime_unverified',
  'integrity_check_pending',
  'model_files_missing',
  'research_only',
  'runtime_load_pending',
  'simulation_only',
])

export async function checkHealth(signal: AbortSignal): Promise<boolean> {
  const response = await fetch(`${API_ROOT}/health`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)
  return response.ok && isObject(payload) && payload.status === 'ok'
}

export async function getCapabilities(signal: AbortSignal): Promise<BackendCapabilities> {
  const response = await fetch(`${API_ROOT}/capabilities`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)
  if (
    !response.ok ||
    !isObject(payload) ||
    (payload.workflow_backend !== 'comfyui' &&
      payload.workflow_backend !== 'native-research' &&
      payload.workflow_backend !== 'simulation') ||
    typeof payload.model_files_present !== 'boolean' ||
    typeof payload.model_integrity_verified !== 'boolean' ||
    typeof payload.runtime_loaded !== 'boolean' ||
    (payload.execution_provider !== 'not_loaded' &&
      payload.execution_provider !== 'cuda' &&
      payload.execution_provider !== 'cpu') ||
    typeof payload.research_only !== 'boolean' ||
    (payload.readiness !== 'ready' &&
      payload.readiness !== 'setup_required' &&
      payload.readiness !== 'simulation') ||
    !Array.isArray(payload.advisories) ||
    !payload.advisories.every(
      (advisory): advisory is CapabilityAdvisory =>
        typeof advisory === 'string' &&
        CAPABILITY_ADVISORIES.has(advisory as CapabilityAdvisory),
    )
  ) {
    throw new Error('无法确认本地换脸能力是否就绪。')
  }
  return {
    workflowBackend: payload.workflow_backend,
    modelFilesPresent: payload.model_files_present,
    modelIntegrityVerified: payload.model_integrity_verified,
    runtimeLoaded: payload.runtime_loaded,
    executionProvider: payload.execution_provider,
    readiness: payload.readiness,
    advisories: payload.advisories,
    researchOnly: payload.research_only,
  }
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
  researchModelLicenseAccepted: boolean
  csrfToken: string
  jpegQuality: number
  outputFormat: 'png' | 'jpeg'
  qualityPreset: 'identity' | 'balanced'
  retention: '30m' | '1h' | '3h' | '6h' | '12h' | '24h'
  source: File
  sourceDetection: TaskFaceSelection
  target: File
  targetDetection: TaskFaceSelection
  watermarkEnabled: boolean
}

export interface TaskFaceSelection {
  detectionId: string
  revisionId: string
}

export interface CreatedTask {
  expiresAt: string
  jpegQuality: number
  qualityPreset: 'identity' | 'balanced'
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

export type FaceImageRole = 'source' | 'target'

export interface FacePoint {
  x: number
  y: number
}

export interface FaceBox {
  height: number
  width: number
  x: number
  y: number
}

export interface DetectedFace {
  box: FaceBox
  confidence: number
  detectionId: string
  landmarks: FacePoint[]
  ordinal: number
}

export interface FaceDetectionRevision {
  detectorId: string
  expiresAt: string
  faces: DetectedFace[]
  height: number
  revisionId: string
  role: FaceImageRole
  selectedDetectionId: string | null
  selectionRequired: boolean
  width: number
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

export type WorkflowNode =
  | 'validate'
  | 'prepare'
  | 'simulate'
  | 'swap'
  | 'inspect'
  | 'export'

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
  form.set('source_revision_id', input.sourceDetection.revisionId)
  form.set('source_detection_id', input.sourceDetection.detectionId)
  form.set('target_revision_id', input.targetDetection.revisionId)
  form.set('target_detection_id', input.targetDetection.detectionId)
  form.set('authorization_confirmed', String(input.authorizationConfirmed))
  form.set(
    'research_model_license_accepted',
    String(input.researchModelLicenseAccepted),
  )
  form.set('output_format', input.outputFormat)
  form.set('jpeg_quality', String(input.jpegQuality))
  form.set('quality_preset', input.qualityPreset)
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
    payload.jpeg_quality > 100 ||
    (payload.quality_preset !== 'identity' && payload.quality_preset !== 'balanced')
  ) {
    throw new Error('后端返回了无效的任务信息。')
  }
  return {
    taskId: payload.task_id,
    status: payload.status as TaskStatus,
    expiresAt: payload.expires_at,
    jpegQuality: payload.jpeg_quality,
    qualityPreset: payload.quality_preset,
    outputFormat: payload.output_format,
  }
}

export async function detectFaces(input: {
  csrfToken: string
  detectorId: string
  file: File
  researchLicenseAccepted: boolean
  role: FaceImageRole
  signal: AbortSignal
}): Promise<FaceDetectionRevision> {
  const form = new FormData()
  form.set('image', input.file)
  form.set('role', input.role)
  form.set('detector_id', input.detectorId)
  form.set('research_license_accepted', String(input.researchLicenseAccepted))
  const response = await fetch(`${API_ROOT}/face-detections`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { [CSRF_HEADER]: input.csrfToken },
    body: form,
    signal: input.signal,
  })
  const payload = await readJson(response)
  if (!response.ok) {
    throw new Error(apiErrorDetail(payload, '无法检测图片中的人物。'))
  }
  return parseDetectionRevision(payload)
}

export async function selectDetectedFace(input: {
  csrfToken: string
  detectionId: string
  revisionId: string
  signal: AbortSignal
}): Promise<FaceDetectionRevision> {
  const response = await fetch(
    `${API_ROOT}/face-detections/${encodeURIComponent(input.revisionId)}/selection`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER]: input.csrfToken,
      },
      body: JSON.stringify({ detection_id: input.detectionId }),
      signal: input.signal,
    },
  )
  const payload = await readJson(response)
  if (!response.ok) {
    throw new Error(apiErrorDetail(payload, '无法保存人物选择。'))
  }
  return parseDetectionRevision(payload)
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
  'swap',
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

function parseDetectionRevision(payload: unknown): FaceDetectionRevision {
  if (
    !isObject(payload) ||
    typeof payload.revision_id !== 'string' ||
    payload.revision_id.length < 16 ||
    (payload.role !== 'source' && payload.role !== 'target') ||
    typeof payload.detector_id !== 'string' ||
    payload.detector_id.length === 0 ||
    !isPositiveInteger(payload.width) ||
    !isPositiveInteger(payload.height) ||
    !Array.isArray(payload.faces) ||
    !(
      payload.selected_detection_id === null ||
      typeof payload.selected_detection_id === 'string'
    ) ||
    typeof payload.selection_required !== 'boolean' ||
    typeof payload.expires_at !== 'string' ||
    !Number.isFinite(Date.parse(payload.expires_at))
  ) {
    throw new Error('后端返回了无效的人脸检测信息。')
  }
  const faces = payload.faces.map(parseDetectedFace)
  const detectionIds = new Set(faces.map((face) => face.detectionId))
  if (
    (payload.selected_detection_id !== null &&
      !detectionIds.has(payload.selected_detection_id)) ||
    payload.selection_required !==
      (faces.length > 1 && payload.selected_detection_id === null)
  ) {
    throw new Error('后端返回了不一致的人脸选择信息。')
  }
  return {
    revisionId: payload.revision_id,
    role: payload.role,
    detectorId: payload.detector_id,
    width: payload.width,
    height: payload.height,
    faces,
    selectedDetectionId: payload.selected_detection_id,
    selectionRequired: payload.selection_required,
    expiresAt: payload.expires_at,
  }
}

function parseDetectedFace(value: unknown): DetectedFace {
  if (
    !isObject(value) ||
    typeof value.detection_id !== 'string' ||
    !value.detection_id.startsWith('face_') ||
    !isPositiveInteger(value.ordinal) ||
    !isObject(value.box) ||
    !isNonNegativeNumber(value.box.x) ||
    !isNonNegativeNumber(value.box.y) ||
    !isPositiveNumber(value.box.width) ||
    !isPositiveNumber(value.box.height) ||
    !Array.isArray(value.landmarks) ||
    value.landmarks.length !== 5 ||
    !isProbability(value.confidence)
  ) {
    throw new Error('后端返回了无效的人脸检测框。')
  }
  const landmarks = value.landmarks.map((point) => {
    if (
      !isObject(point) ||
      !isNonNegativeNumber(point.x) ||
      !isNonNegativeNumber(point.y)
    ) {
      throw new Error('后端返回了无效的人脸关键点。')
    }
    return { x: point.x, y: point.y }
  })
  return {
    detectionId: value.detection_id,
    ordinal: value.ordinal,
    box: {
      x: value.box.x,
      y: value.box.y,
      width: value.box.width,
      height: value.box.height,
    },
    landmarks,
    confidence: value.confidence,
  }
}

function apiErrorDetail(payload: unknown, fallback: string): string {
  return isObject(payload) && typeof payload.detail === 'string'
    ? payload.detail
    : fallback
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function isPositiveNumber(value: unknown): value is number {
  return isNonNegativeNumber(value) && value > 0
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && isPositiveNumber(value)
}

function isProbability(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
  )
}
