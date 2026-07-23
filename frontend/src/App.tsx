import { type FormEvent, useEffect, useRef, useState } from 'react'
import './App.css'
import PhotoPicker from './PhotoPicker'
import { checkHealth, createTask, establishSession, type CreatedTask } from './api'

type ApiState = 'checking' | 'online' | 'offline'
type SessionState = 'checking' | 'ready' | 'unavailable'
type OutputFormat = 'png' | 'jpeg'
type Retention = '30m' | '24h' | '7d'

const workflowStages = [
  { number: '01', title: '输入照片', detail: '身份来源图与目标场景图' },
  { number: '02', title: '检测多脸', detail: '定位人物，但不自动决定替换对象' },
  { number: '03', title: '选择目标', detail: '每次只选择并替换一名人物' },
  { number: '04', title: '精准换脸', detail: '原生 ONNX 后端，可替换为 ComfyUI' },
  { number: '05', title: '安全导出', detail: '写入 AI 元数据，默认显示可见水印' },
] as const

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
  const [retention, setRetention] = useState<Retention>('30m')
  const [watermarkEnabled, setWatermarkEnabled] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [createdTask, setCreatedTask] = useState<CreatedTask | null>(null)
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

  const apiLabel =
    apiState === 'online' ? '在线' : apiState === 'offline' ? '未连接' : '检查中'
  const canSubmit =
    apiState === 'online' &&
    csrfToken !== null &&
    sourcePhoto !== null &&
    targetPhoto !== null &&
    authorizationConfirmed &&
    !submitting
  const knownRatios = [sourceRatio, targetRatio].filter(
    (ratio): ratio is number => ratio !== null,
  )
  const sharedPreviewRatio = knownRatios.length === 0 ? 16 / 9 : Math.min(...knownRatios)

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
    setSubmitError(null)
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      submitLock.current ||
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
    try {
      const task = await createTask({
        authorizationConfirmed,
        csrfToken,
        outputFormat,
        retention,
        source: sourcePhoto,
        target: targetPhoto,
        watermarkEnabled,
      })
      setCreatedTask(task)
      setAuthorizationConfirmed(false)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '任务提交失败。')
    } finally {
      submitLock.current = false
      setSubmitting(false)
    }
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
        </aside>

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
              label="身份来源图"
              detail="提供需要保留的身份特征"
              file={sourcePhoto}
              onChange={(file) => changePhoto('source', file)}
              onRatioChange={setSourceRatio}
              previewRatio={sharedPreviewRatio}
            />
            <PhotoPicker
              label="目标场景图"
              detail="提供姿态、背景与待替换人物"
              file={targetPhoto}
              onChange={(file) => changePhoto('target', file)}
              onRatioChange={setTargetRatio}
              previewRatio={sharedPreviewRatio}
            />
          </div>

          <section className="task-options" aria-label="处理设置">
            <label>
              <span>输出格式</span>
              <select
                value={outputFormat}
                onChange={(event) => setOutputFormat(event.currentTarget.value as OutputFormat)}
              >
                <option value="png">PNG（推荐）</option>
                <option value="jpeg">JPEG</option>
              </select>
            </label>
            <label>
              <span>本地保留</span>
              <select
                value={retention}
                onChange={(event) => setRetention(event.currentTarget.value as Retention)}
              >
                <option value="30m">30 分钟（推荐）</option>
                <option value="24h">24 小时</option>
                <option value="7d">7 天（上限）</option>
              </select>
            </label>
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={watermarkEnabled}
                onChange={(event) => setWatermarkEnabled(event.currentTarget.checked)}
              />
              <span>显示 AI 编辑水印</span>
            </label>
          </section>

          <label className="authorization">
            <input
              type="checkbox"
              checked={authorizationConfirmed}
              onChange={(event) => setAuthorizationConfirmed(event.currentTarget.checked)}
            />
            <span>
              我确认拥有处理这两张图片及其中人物肖像的合法授权，并知晓当前输出为明确标记的模拟结果。
            </span>
          </label>

          <div className="workflow-canvas">
            <div className="canvas-grid" aria-hidden="true" />
            <ol className="workflow-list">
              {workflowStages.map((stage, index) => (
                <li className="workflow-step" key={stage.number}>
                  <article className="workflow-node">
                    <span className="node-number">{stage.number}</span>
                    <div>
                      <h3>{stage.title}</h3>
                      <p>{stage.detail}</p>
                    </div>
                    <span className="node-state">待接入</span>
                  </article>
                  {index < workflowStages.length - 1 && (
                    <span className="flow-link" aria-hidden="true">↓</span>
                  )}
                </li>
              ))}
            </ol>
          </div>

          <footer className="workflow-footer">
            <div aria-live="polite">
              <p>
                {createdTask
                  ? `任务已提交：${createdTask.status}`
                  : sourcePhoto && targetPhoto
                    ? '两张图片已就绪，请确认授权后提交。'
                    : '请先选择身份来源图和目标场景图。'}
              </p>
              {submitError && <p className="submit-error">{submitError}</p>}
            </div>
            <button type="submit" disabled={!canSubmit}>
              {submitting ? '正在提交…' : '开始模拟处理'}
            </button>
          </footer>
        </form>
      </main>

      <footer className="legal-footer">
        <span>仅处理已获授权的影像</span>
        <span>AI 编辑元数据将始终写入导出文件</span>
      </footer>
    </div>
  )
}

export default App
