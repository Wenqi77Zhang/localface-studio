import { type FormEvent, useEffect, useRef, useState } from 'react'
import './App.css'
import LocalResultGallery from './LocalResultGallery'
import PhotoPicker from './PhotoPicker'
import ResultPreview from './ResultPreview'
import {
  cancelTask,
  checkHealth,
  createTask,
  establishSession,
  fetchTaskResult,
  getTask,
  parseTaskEvent,
  taskEventsUrl,
  type CreatedTask,
  type TaskEvent,
  type WorkflowNode,
} from './api'

type ApiState = 'checking' | 'online' | 'offline'
type SessionState = 'checking' | 'ready' | 'unavailable'
type OutputFormat = 'png' | 'jpeg'
type Retention = '30m' | '1h' | '3h' | '6h' | '12h' | '24h'

const workflowStages = [
  { node: 'validate', number: '01', title: '文件校验', detail: '复核格式、尺寸和完整性' },
  { node: 'prepare', number: '02', title: '任务准备', detail: '建立隔离工作区和处理参数' },
  { node: 'simulate', number: '03', title: '模拟处理', detail: '生成明确标记的非换脸结果' },
  { node: 'inspect', number: '04', title: '输出检查', detail: '验证尺寸、编码和必要元数据' },
  { node: 'export', number: '05', title: '安全导出', detail: '原子写入最终结果文件' },
] as const

const workflowOrder = workflowStages.map((stage) => stage.node)
const terminalStatuses = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
  'expired',
  'deleted',
])
const COMPLETED_TASK_RESET_DELAY_MS = 3_000
const TASK_STATUS_POLL_INTERVAL_MS = 500
type NodeVisualState = 'pending' | 'active' | 'complete' | 'stopped'
const nodeStateLabels: Record<NodeVisualState, string> = {
  pending: '等待',
  active: '处理中',
  complete: '完成',
  stopped: '已停止',
}

function nodeDisplayState(
  taskEvent: TaskEvent | null,
  node: WorkflowNode,
): NodeVisualState {
  if (taskEvent === null || taskEvent.status === 'queued') {
    return 'pending'
  }
  if (taskEvent.status === 'succeeded') {
    return 'complete'
  }
  const nodeIndex = workflowOrder.indexOf(node)
  const currentIndex = taskEvent.currentNode === null
    ? -1
    : workflowOrder.indexOf(taskEvent.currentNode)
  if (nodeIndex < currentIndex) {
    return 'complete'
  }
  if (nodeIndex === currentIndex) {
    return taskEvent.status === 'running' ? 'active' : 'stopped'
  }
  return 'pending'
}

function App() {
  const [apiState, setApiState] = useState<ApiState>('checking')
  const [sessionState, setSessionState] = useState<SessionState>('checking')
  const [csrfToken, setCsrfToken] = useState<string | null>(null)
  const [sourcePhoto, setSourcePhoto] = useState<File | null>(null)
  const [targetPhoto, setTargetPhoto] = useState<File | null>(null)
  const [sourceRatio, setSourceRatio] = useState<number | null>(null)
  const [targetRatio, setTargetRatio] = useState<number | null>(null)
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(false)
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('png')
  const [jpegQuality, setJpegQuality] = useState(95)
  const [retention, setRetention] = useState<Retention>('30m')
  const [watermarkEnabled, setWatermarkEnabled] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [createdTask, setCreatedTask] = useState<CreatedTask | null>(null)
  const [taskEvent, setTaskEvent] = useState<TaskEvent | null>(null)
  const [eventError, setEventError] = useState<string | null>(null)
  const [workflowReset, setWorkflowReset] = useState(false)
  const [resultPreviewUrl, setResultPreviewUrl] = useState<string | null>(null)
  const [resultLoading, setResultLoading] = useState(false)
  const [resultError, setResultError] = useState<string | null>(null)
  const [validationAttempted, setValidationAttempted] = useState(false)
  const submitLock = useRef(false)

  useEffect(() => {
    const controller = new AbortController()

    async function initializeLocalApi() {
      try {
        const [healthy, csrf] = await Promise.all([
          checkHealth(controller.signal),
          establishSession(controller.signal),
        ])
        setApiState(healthy ? 'online' : 'offline')
        setCsrfToken(csrf)
        setSessionState('ready')
      } catch {
        if (!controller.signal.aborted) {
          setApiState('offline')
          setCsrfToken(null)
          setSessionState('unavailable')
        }
      }
    }

    void initializeLocalApi()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (createdTask === null) {
      return
    }
    const events = new EventSource(taskEventsUrl(createdTask.taskId))
    const receiveTaskEvent = (event: MessageEvent<string>) => {
      try {
        const nextEvent = parseTaskEvent(event.data)
        setTaskEvent((current) =>
          current === null || nextEvent.version > current.version ? nextEvent : current,
        )
        setEventError(null)
        if (terminalStatuses.has(nextEvent.status)) {
          setCancelling(false)
          events.close()
        }
      } catch (error) {
        setEventError(error instanceof Error ? error.message : '无法读取任务进度。')
        setCancelling(false)
        events.close()
      }
    }
    events.addEventListener('task', receiveTaskEvent)
    events.onerror = () => {
      setEventError('实时进度连接中断。')
      setCancelling(false)
      events.close()
    }
    return () => {
      events.removeEventListener('task', receiveTaskEvent)
      events.close()
    }
  }, [createdTask])

  const apiLabel =
    apiState === 'online' ? '在线' : apiState === 'offline' ? '未连接' : '检查中'
  const latestTaskStatus = taskEvent?.status ?? createdTask?.status ?? null
  const taskInProgress =
    latestTaskStatus !== null && !terminalStatuses.has(latestTaskStatus)
  const canSubmit =
    apiState === 'online' &&
    csrfToken !== null &&
    sourcePhoto !== null &&
    targetPhoto !== null &&
    authorizationConfirmed &&
    !taskInProgress &&
    !submitting
  const knownRatios = [sourceRatio, targetRatio].filter(
    (ratio): ratio is number => ratio !== null,
  )
  const sharedPreviewRatio = knownRatios.length === 0 ? 16 / 9 : Math.min(...knownRatios)
  const missingRequirements = [
    sourcePhoto === null ? '身份来源图' : null,
    targetPhoto === null ? '目标场景图' : null,
    !authorizationConfirmed ? '授权确认' : null,
    apiState !== 'online' || csrfToken === null ? '本地后端连接' : null,
  ].filter((requirement): requirement is string => requirement !== null)
  const validationMessage =
    missingRequirements.length === 0
      ? null
      : `请先完成：${missingRequirements.join('、')}。`
  const submitButtonState = canSubmit
    ? 'ready'
    : sourcePhoto === null && targetPhoto === null && !authorizationConfirmed
      ? 'pristine'
      : 'incomplete'

  useEffect(() => {
    if (createdTask === null || !taskInProgress) {
      return
    }
    let stopped = false
    const refreshTask = async () => {
      try {
        const snapshot = await getTask(createdTask.taskId)
        if (stopped) {
          return
        }
        setTaskEvent((current) =>
          current === null || snapshot.version >= current.version ? snapshot : current,
        )
        setEventError(null)
        if (terminalStatuses.has(snapshot.status)) {
          setCancelling(false)
        }
      } catch {
        if (!stopped) {
          setCancelling(false)
          setEventError('无法同步任务状态，请检查本地后端连接。')
        }
      }
    }
    void refreshTask()
    const interval = window.setInterval(
      () => void refreshTask(),
      TASK_STATUS_POLL_INTERVAL_MS,
    )
    return () => {
      stopped = true
      window.clearInterval(interval)
    }
  }, [createdTask, taskInProgress])

  useEffect(() => {
    if (createdTask === null || taskInProgress || authorizationConfirmed) {
      return
    }
    const timeout = window.setTimeout(() => {
      setWorkflowReset(true)
    }, COMPLETED_TASK_RESET_DELAY_MS)
    return () => window.clearTimeout(timeout)
  }, [authorizationConfirmed, createdTask, taskInProgress])

  useEffect(() => {
    if (createdTask === null || latestTaskStatus !== 'succeeded') {
      setResultLoading(false)
      setResultError(null)
      setResultPreviewUrl((current) => {
        if (current !== null) {
          URL.revokeObjectURL(current)
        }
        return null
      })
      return
    }
    const controller = new AbortController()
    let objectUrl: string | null = null
    setResultLoading(true)
    setResultError(null)
    const loadResult = async () => {
      try {
        const result = await fetchTaskResult(createdTask.taskId, controller.signal)
        objectUrl = URL.createObjectURL(result)
        setResultPreviewUrl(objectUrl)
      } catch (error) {
        if (!controller.signal.aborted) {
          setResultError(
            error instanceof Error ? error.message : '无法加载模拟结果。',
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setResultLoading(false)
        }
      }
    }
    void loadResult()
    return () => {
      controller.abort()
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [createdTask, latestTaskStatus])

  function changePhoto(role: 'source' | 'target', file: File | null) {
    if (role === 'source') {
      setSourcePhoto(file)
      setSourceRatio(null)
    } else {
      setTargetPhoto(file)
      setTargetRatio(null)
    }
    setAuthorizationConfirmed(false)
    setCreatedTask(null)
    setTaskEvent(null)
    setEventError(null)
    setSubmitError(null)
    setCancelling(false)
    setWorkflowReset(false)
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || taskInProgress || submitLock.current) {
      return
    }
    setValidationAttempted(true)
    if (
      !canSubmit ||
      csrfToken === null ||
      sourcePhoto === null ||
      targetPhoto === null
    ) {
      return
    }
    submitLock.current = true
    setSubmitting(true)
    setSubmitError(null)
    setCreatedTask(null)
    setTaskEvent(null)
    setEventError(null)
    setWorkflowReset(false)
    try {
      const task = await createTask({
        authorizationConfirmed,
        csrfToken,
        jpegQuality,
        outputFormat,
        retention,
        source: sourcePhoto,
        target: targetPhoto,
        watermarkEnabled,
      })
      setCreatedTask(task)
      setTaskEvent({
        taskId: task.taskId,
        version: -1,
        status: task.status,
        currentNode: null,
        errorCode: null,
      })
      setAuthorizationConfirmed(false)
      setValidationAttempted(false)
      setWorkflowReset(false)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '任务提交失败。')
    } finally {
      submitLock.current = false
      setSubmitting(false)
    }
  }

  function changeAuthorization(checked: boolean) {
    if (checked && createdTask !== null && !taskInProgress) {
      setWorkflowReset(true)
      setEventError(null)
      setSubmitError(null)
    }
    setAuthorizationConfirmed(checked)
  }

  async function requestCancellation() {
    if (
      cancelling ||
      !taskInProgress ||
      createdTask === null ||
      csrfToken === null
    ) {
      return
    }
    setCancelling(true)
    setSubmitError(null)
    setEventError(null)
    try {
      const cancellation = await cancelTask(createdTask.taskId, csrfToken)
      setTaskEvent((current) =>
        current === null || cancellation.version >= current.version
          ? cancellation
          : current,
      )
      if (terminalStatuses.has(cancellation.status)) {
        setCancelling(false)
      }
    } catch (error) {
      setCancelling(false)
      setSubmitError(error instanceof Error ? error.message : '无法取消当前任务。')
    }
  }

  function handleResultsDeleted(taskIds: string[]) {
    if (createdTask === null || !taskIds.includes(createdTask.taskId)) {
      return
    }
    setSourcePhoto(null)
    setTargetPhoto(null)
    setSourceRatio(null)
    setTargetRatio(null)
    setAuthorizationConfirmed(false)
    setCreatedTask(null)
    setTaskEvent(null)
    setEventError(null)
    setSubmitError(null)
    setCancelling(false)
    setWorkflowReset(false)
    setValidationAttempted(false)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="LocalFace Studio 首页">
          <span className="brand-mark" aria-hidden="true">LF</span>
          <span>
            <strong>LocalFace Studio</strong>
            <small>本地 AI 影像工作台</small>
          </span>
        </a>

        <div className="topbar-status" aria-live="polite">
          <span className={`status-dot status-dot--${apiState}`} />
          后端{apiLabel} · 会话
          {sessionState === 'ready'
            ? '已保护'
            : sessionState === 'unavailable'
              ? '不可用'
              : '建立中'}
        </div>
      </header>

      <main className="workspace">
        <aside className="project-panel" aria-label="项目说明">
          <span className="eyebrow">阶段 2 · 本地产品闭环</span>
          <h1>精准换脸，<br />数据留在本机。</h1>
          <p className="lead">
            先建立可审查的工作流边界，再逐步接入检测、选择、换脸与导出能力。
          </p>

          <div className="privacy-card">
            <span className="privacy-icon" aria-hidden="true">⌂</span>
            <div>
              <strong>隐私优先模式</strong>
              <p>服务仅监听 127.0.0.1；选择后的预览不会离开本机浏览器。</p>
            </div>
          </div>

          <dl className="project-facts">
            <div><dt>处理方式</dt><dd>本地</dd></div>
            <div><dt>目标选择</dt><dd>单人</dd></div>
            <div><dt>可见水印</dt><dd>默认开启</dd></div>
          </dl>

          <LocalResultGallery
            csrfToken={csrfToken}
            enabled={sessionState === 'ready'}
            onResultsDeleted={handleResultsDeleted}
            refreshKey={`${createdTask?.taskId ?? 'none'}:${latestTaskStatus ?? 'none'}`}
          />
        </aside>

        <div className="workflow-column">
          <form className="workflow-panel" aria-labelledby="workflow-title" onSubmit={submitTask}>
          <div className="workflow-heading">
            <div>
              <span className="eyebrow">Workflow preview</span>
              <h2 id="workflow-title">单张照片处理流程</h2>
            </div>
            <span className="draft-badge">本地模拟模式</span>
          </div>

          <div className="photo-grid" aria-label="图片输入">
            <PhotoPicker
              attentionMessage={
                validationAttempted && sourcePhoto === null ? '请上传身份来源图。' : null
              }
              label="身份来源图"
              detail="提供需要保留的身份特征"
              file={sourcePhoto}
              onChange={(file) => changePhoto('source', file)}
              onRatioChange={setSourceRatio}
              previewRatio={sharedPreviewRatio}
            />
            <PhotoPicker
              attentionMessage={
                validationAttempted && targetPhoto === null ? '请上传目标场景图。' : null
              }
              label="目标场景图"
              detail="提供姿态、背景与待替换人物"
              file={targetPhoto}
              onChange={(file) => changePhoto('target', file)}
              onRatioChange={setTargetRatio}
              previewRatio={sharedPreviewRatio}
            />
          </div>

          <label
            className={[
              'authorization',
              validationAttempted && !authorizationConfirmed
                ? 'authorization--attention'
                : '',
            ].join(' ')}
          >
            <input
              type="checkbox"
              checked={authorizationConfirmed}
              disabled={taskInProgress}
              onChange={(event) => changeAuthorization(event.currentTarget.checked)}
            />
            <span>
              我确认拥有处理这两张图片及其中人物肖像的合法授权，并知晓当前输出为明确标记的模拟结果。
              {validationAttempted && !authorizationConfirmed && (
                <strong className="attention-text">请先勾选确认知晓。</strong>
              )}
            </span>
          </label>

          <details className="advanced-settings">
            <summary>
              <span>高级设置</span>
              <small>（输出格式、JPEG 质量、本地保留、AI 水印）</small>
            </summary>
            <section className="task-options" aria-label="高级处理设置">
              <label>
                <span>输出格式</span>
                <select
                  value={outputFormat}
                  disabled={submitting || taskInProgress}
                  onChange={(event) =>
                    setOutputFormat(event.currentTarget.value as OutputFormat)
                  }
                >
                  <option value="png">PNG（推荐）</option>
                  <option value="jpeg">JPEG</option>
                </select>
              </label>
              {outputFormat === 'jpeg' && (
                <label className="quality-option">
                  <span>JPEG 质量</span>
                  <div className="quality-control">
                    <div className="quality-track">
                      <input
                        id="jpeg-quality"
                        type="range"
                        min="5"
                        max="100"
                        step="1"
                        value={jpegQuality}
                        disabled={submitting || taskInProgress}
                        aria-label="JPEG 质量"
                        onChange={(event) =>
                          setJpegQuality(Number(event.currentTarget.value))
                        }
                      />
                      <span className="quality-default-marker" aria-hidden="true" />
                    </div>
                    <output htmlFor="jpeg-quality">
                      {jpegQuality}%{jpegQuality === 95 ? '（默认）' : ''}
                    </output>
                  </div>
                </label>
              )}
              <label>
                <span>本地保留</span>
                <select
                  value={retention}
                  disabled={submitting || taskInProgress}
                  onChange={(event) =>
                    setRetention(event.currentTarget.value as Retention)
                  }
                >
                  <option value="30m">30 分钟（推荐）</option>
                  <option value="1h">1 小时</option>
                  <option value="3h">3 小时</option>
                  <option value="6h">6 小时</option>
                  <option value="12h">12 小时</option>
                  <option value="24h">24 小时（上限）</option>
                </select>
              </label>
              <label className="checkbox-option">
                <input
                  type="checkbox"
                  checked={watermarkEnabled}
                  disabled={submitting || taskInProgress}
                  onChange={(event) =>
                    setWatermarkEnabled(event.currentTarget.checked)
                  }
                />
                <span>显示 AI 编辑水印</span>
              </label>
            </section>
          </details>

          <div className="workflow-canvas">
            <div className="canvas-grid" aria-hidden="true" />
            <ol className="workflow-list">
              {workflowStages.map((stage, index) => {
                const nodeState = nodeDisplayState(
                  workflowReset ? null : taskEvent,
                  stage.node,
                )
                return (
                  <li className="workflow-step" key={stage.number}>
                    <article className={`workflow-node workflow-node--${nodeState}`}>
                      <span className="node-number">{stage.number}</span>
                      <div>
                        <h3>{stage.title}</h3>
                        <p>{stage.detail}</p>
                      </div>
                      <span className="node-state">{nodeStateLabels[nodeState]}</span>
                    </article>
                    {index < workflowStages.length - 1 && (
                      <span className="flow-link" aria-hidden="true">↓</span>
                    )}
                  </li>
                )
              })}
            </ol>
          </div>

          <footer className="workflow-footer">
            <div aria-live="polite">
              <p>
                {createdTask
                  ? `任务状态：${taskEvent?.status ?? createdTask.status}`
                  : sourcePhoto && targetPhoto
                    ? '两张图片已就绪，请确认授权后提交。'
                    : '请先选择身份来源图和目标场景图。'}
              </p>
              {submitError && <p className="submit-error">{submitError}</p>}
              {eventError && <p className="submit-error">{eventError}</p>}
            </div>
            <div className="submit-action">
              {validationAttempted && validationMessage && (
                <span className="submit-guidance" role="alert">
                  {validationMessage}
                </span>
              )}
              <div className="task-action-buttons">
                {taskInProgress && (
                  <button
                    className="cancel-task-button"
                    type="button"
                    disabled={cancelling}
                    onClick={() => void requestCancellation()}
                  >
                    {cancelling ? '正在等待任务停止…' : '取消当前任务'}
                  </button>
                )}
                <button
                  className={`submit-button--${submitButtonState}`}
                  type="submit"
                  disabled={submitting || taskInProgress}
                >
                  {submitting
                    ? '正在提交…'
                    : taskInProgress
                      ? '任务处理中'
                      : '开始模拟处理'}
                </button>
              </div>
            </div>
          </footer>
          </form>
          {createdTask !== null &&
            latestTaskStatus === 'succeeded' &&
            targetPhoto !== null && (
            <ResultPreview
              error={resultError}
              loading={resultLoading}
              originalFile={targetPhoto}
              outputFormat={createdTask.outputFormat}
              previewRatio={targetRatio ?? 16 / 9}
              previewUrl={resultPreviewUrl}
            />
          )}
        </div>
      </main>

      <footer className="legal-footer">
        <span>仅处理已获授权的影像</span>
        <span>AI 编辑元数据将始终写入导出文件</span>
      </footer>
    </div>
  )
}

export default App
