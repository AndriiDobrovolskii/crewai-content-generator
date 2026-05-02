import { useState, useCallback } from 'react'
import { Cpu, Github } from 'lucide-react'
import type { JobStatus } from './types'
import { fetchJobState } from './api'
import { ConfigPanel } from './components/ConfigPanel'
import { LogTerminal } from './components/LogTerminal'
import { PipelineStatus } from './components/PipelineStatus'
import { PreviewPanel } from './components/PreviewPanel'

interface JobResult {
  id: string
  status: JobStatus
  files: Record<string, string>
  zipPath: string | null
  error: string | null
  discoveredUrls: string[]
}

export default function App() {
  const [job, setJob] = useState<JobResult | null>(null)
  const [logLines, setLogLines] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [mode, setMode] = useState<'generate' | 'discover'>('generate')

  const handleJobStarted = useCallback((jobId: string, jobMode: 'generate' | 'discover') => {
    setMode(jobMode)
    setIsRunning(true)
    setLogLines([])
    setJob({
      id: jobId,
      status: 'running',
      files: {},
      zipPath: null,
      error: null,
      discoveredUrls: [],
    })
  }, [])

  const handleLogLine = useCallback((line: string) => {
    setLogLines((prev) => [...prev, line])
  }, [])

  const handleStreamDone = useCallback(async () => {
    setIsRunning(false)
    if (!job) return
    try {
      const state = await fetchJobState(job.id)
      setJob({
        id: state.job_id,
        status: state.status,
        files: state.files ?? {},
        zipPath: state.zip_path,
        error: state.error,
        discoveredUrls: state.discovered_urls ?? [],
      })
    } catch (e) {
      console.error('Failed to fetch final job state:', e)
    }
  }, [job])

  const isDone = job?.status === 'done'

  return (
    <div className="h-screen flex flex-col bg-void overflow-hidden">

      {/* Top navigation bar */}
      <header className="flex-shrink-0 h-14 flex items-center justify-between px-6 border-b border-border bg-surface/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="w-7 h-7 rounded-lg bg-violet flex items-center justify-center" style={{ boxShadow: '0 0 12px rgba(124,58,237,0.5)' }}>
            <Cpu className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-ink leading-none">GEO Content Generator</h1>
            <p className="text-[10px] text-ghost mt-0.5">CrewAI Multi-Agent Pipeline · E-Commerce</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Live indicator */}
          {isRunning && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-cyan/10 border border-cyan/20">
              <div className="live-dot" />
              <span className="text-[11px] text-cyan font-medium">
                {mode === 'discover' ? 'Пошук URL...' : 'Генерація...'}
              </span>
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald/10 border border-emerald/20">
              <div className="w-2 h-2 rounded-full bg-emerald" />
              <span className="text-[11px] text-emerald font-medium">Завершено</span>
            </div>
          )}
          {job?.status === 'error' && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-rose/10 border border-rose/20">
              <div className="w-2 h-2 rounded-full bg-rose" />
              <span className="text-[11px] text-rose font-medium">Помилка</span>
            </div>
          )}

          <span className="text-[10px] font-mono text-ghost">v2.0</span>
        </div>
      </header>

      {/* Main content — 3-column layout */}
      <main className="flex-1 grid gap-3 p-3 overflow-hidden min-h-0" style={{
        gridTemplateColumns: '300px 1fr 1fr',
        gridTemplateRows: '1fr',
      }}>

        {/* Column 1: Config */}
        <div className="overflow-y-auto min-h-0">
          <ConfigPanel
            onJobStarted={handleJobStarted}
            isRunning={isRunning}
            discoveredUrls={job?.discoveredUrls}
          />

          {/* Pipeline stages — below config */}
          <div className="mt-3">
            <PipelineStatus
              logLines={logLines}
              isRunning={isRunning}
              isDone={isDone ?? false}
            />
          </div>
        </div>

        {/* Column 2: Log terminal */}
        <div className="min-h-0">
          <LogTerminal
            jobId={job?.id ?? null}
            status={job?.status ?? null}
            onDone={handleStreamDone}
          />
        </div>

        {/* Column 3: Preview */}
        <div className="min-h-0">
          <PreviewPanel
            jobId={job?.id ?? null}
            files={job?.files ?? {}}
            zipPath={job?.zipPath ?? null}
            isRunning={isRunning}
          />
        </div>
      </main>

      {/* Bottom status bar */}
      <footer className="flex-shrink-0 h-6 flex items-center px-4 border-t border-border bg-surface/60 text-[10px] font-mono text-ghost gap-4">
        <span>GEO Content Generator · FastAPI + React</span>
        <span className="ml-auto">Backend: localhost:8000</span>
      </footer>
    </div>
  )
}
