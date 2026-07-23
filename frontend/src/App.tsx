import { useEffect, useState } from 'react'
import './App.css'
import { checkHealth, establishSession } from './api'

type ApiState = 'checking' | 'online' | 'offline'
type SessionState = 'checking' | 'ready' | 'unavailable'

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
  const [, setCsrfToken] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function initializeLocalApi() {
      try {
        const [healthy, csrfToken] = await Promise.all([
          checkHealth(controller.signal),
          establishSession(controller.signal),
        ])
        setApiState(healthy ? 'online' : 'offline')
        setCsrfToken(csrfToken)
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
          <span className="eyebrow">阶段 1 · 工程骨架</span>
          <h1>精准换脸，<br />数据留在本机。</h1>
          <p className="lead">
            先建立可审查的工作流边界，再逐步接入检测、选择、换脸与导出能力。
          </p>

          <div className="privacy-card">
            <span className="privacy-icon" aria-hidden="true">⌂</span>
            <div>
              <strong>隐私优先模式</strong>
              <p>服务仅监听 127.0.0.1，当前不上传任何图片。</p>
            </div>
          </div>

          <dl className="project-facts">
            <div><dt>处理方式</dt><dd>本地</dd></div>
            <div><dt>目标选择</dt><dd>单人</dd></div>
            <div><dt>可见水印</dt><dd>默认开启</dd></div>
          </dl>
        </aside>

        <section className="workflow-panel" aria-labelledby="workflow-title">
          <div className="workflow-heading">
            <div>
              <span className="eyebrow">Workflow preview</span>
              <h2 id="workflow-title">单张照片处理流程</h2>
            </div>
            <span className="draft-badge">架构预览</span>
          </div>

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
            <p>当前仅验证前后端工程链路，不包含模型推理能力。</p>
            <button type="button" disabled title="将在模型阶段启用">
              开始处理
            </button>
          </footer>
        </section>
      </main>

      <footer className="legal-footer">
        <span>仅处理已获授权的影像</span>
        <span>AI 编辑元数据将始终写入导出文件</span>
      </footer>
    </div>
  )
}

export default App
