import { useEffect, useState } from 'react'
import { fetchTaskResult, getResultArtifacts, type ResultArtifacts, type ResultVariant } from './api'

interface ResultState {
  taskId: string
  loading: boolean
  error: string | null
  artifacts: ResultArtifacts | null
  urls: Partial<Record<ResultVariant, string>>
}

export function useTaskResults(taskId: string, expiresAt: string) {
  const [state, setState] = useState<ResultState>({
    taskId, loading: true, error: null, artifacts: null, urls: {},
  })
  useEffect(() => {
    const controller = new AbortController()
    const urls: string[] = []
    const release = () => urls.splice(0).forEach(URL.revokeObjectURL)
    const expiryTimer = window.setTimeout(() => {
      controller.abort()
      release()
      setState({ taskId, loading: false, artifacts: null, urls: {},
        error: '结果已到期，预览与下载已关闭。已另存的文件不受影响。' })
    }, Math.max(0, Date.parse(expiresAt) - Date.now()))
    async function load() {
      try {
        const artifacts = await getResultArtifacts(taskId, controller.signal)
        const entries = await Promise.all(artifacts.variants.map(async (variant) => {
          const blob = await fetchTaskResult(taskId, controller.signal, variant)
          if (controller.signal.aborted) return [variant, undefined] as const
          const url = URL.createObjectURL(blob)
          urls.push(url)
          return [variant, url] as const
        }))
        if (!controller.signal.aborted) {
          setState({ taskId, loading: false, error: null, artifacts,
            urls: Object.fromEntries(entries) })
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          controller.abort()
          release()
          setState({ taskId, loading: false, artifacts: null, urls: {},
            error: error instanceof Error ? error.message : '无法读取处理结果。' })
        }
      }
    }
    void load()
    return () => {
      controller.abort()
      window.clearTimeout(expiryTimer)
      release()
    }
  }, [taskId, expiresAt])
  return state.taskId === taskId ? state : {
    taskId, loading: true, error: null, artifacts: null, urls: {},
  }
}
