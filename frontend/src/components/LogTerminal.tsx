import { useEffect, useRef, useState } from 'react'
import { Terminal, Trash2 } from 'lucide-react'
import type { JobStatus } from '../types'
import { createSSEStream } from '../api'

interface Props {
  jobId: string | null
  status: JobStatus | null
  onDone: () => void
}

interface LogLine {
  id: number
  text: string
  type: 'info' | 'success' | 'error' | 'agent' | 'step'
}

let lineCounter = 0

function classifyLine(text: string): LogLine['type'] {
  if (text.includes('❌') || text.toLowerCase().includes('error') || text.toLowerCase().includes('помилка')) return 'error'
  if (text.includes('✅') || text.includes('завершен') || text.includes('DONE') || text.includes('✓')) return 'success'
  if (text.includes('🔍') || text.includes('⚙️') || text.includes('✍️') || text.includes('🌐') || text.includes('🏗️')) return 'agent'
  if (text.includes('►') || text.includes('→') || text.includes('•') || text.startsWith('   ')) return 'step'
  return 'info'
}

const LINE_COLORS: Record<LogLine['type'], string> = {
  info:    'text-dim',
  success: 'text-emerald',
  error:   'text-rose',
  agent:   'text-cyan',
  step:    'text-ink/70',
}

export function LogTerminal({ jobId, status, onDone }: Props) {
  const [lines, setLines] = useState<LogLine[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  // Start SSE stream when jobId changes
  useEffect(() => {
    if (!jobId) return

    // Close previous stream
    esRef.current?.close()
    setLines([])
    setIsStreaming(true)

    const es = createSSEStream(
      jobId,
      (rawLine) => {
        // Split on real newlines (restored from ↵)
        const parts = rawLine.split('\n').filter((l) => l.trim())
        setLines((prev) => [
          ...prev,
          ...parts.map((text) => ({
            id: ++lineCounter,
            text,
            type: classifyLine(text),
          })),
        ])
      },
      () => {
        setIsStreaming(false)
        onDone()
      },
    )

    esRef.current = es
    return () => { es.close() }
  }, [jobId])

  const handleClear = () => setLines([])

  return (
    <div className="panel-glow flex flex-col h-full min-h-0">
      {/* Terminal header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-dim" />
          <span className="text-xs font-medium text-dim uppercase tracking-wide">Pipeline Log</span>
          {isStreaming && (
            <div className="flex items-center gap-1.5 ml-1">
              <div className="live-dot" />
              <span className="text-[10px] text-cyan font-mono">LIVE</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-ghost">{lines.length} lines</span>
          <button onClick={handleClear} className="text-ghost hover:text-dim transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Log body */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed min-h-0">
        {lines.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-ghost">
            <Terminal className="w-8 h-8 opacity-30" />
            <span className="text-xs">Запустіть генерацію — логи з'являться тут</span>
          </div>
        )}

        {lines.map((line) => (
          <div
            key={line.id}
            className={`${LINE_COLORS[line.type]} animate-slide-in whitespace-pre-wrap break-all`}
          >
            {line.text}
          </div>
        ))}

        {isStreaming && (
          <span className="inline-block w-2 h-3.5 bg-cyan/70 animate-blink ml-0.5 align-middle" />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Status bar */}
      {status && (
        <div className={`px-4 py-2 border-t border-border flex-shrink-0 flex items-center gap-2 text-[10px] font-mono ${
          status === 'done'    ? 'text-emerald' :
          status === 'error'   ? 'text-rose' :
          status === 'running' ? 'text-cyan' : 'text-ghost'
        }`}>
          <div className={`w-1.5 h-1.5 rounded-full ${
            status === 'done'    ? 'bg-emerald' :
            status === 'error'   ? 'bg-rose' :
            status === 'running' ? 'bg-cyan animate-pulse' : 'bg-ghost'
          }`} />
          {status === 'done'    && 'PIPELINE COMPLETE'}
          {status === 'error'   && 'PIPELINE ERROR'}
          {status === 'running' && 'RUNNING...'}
          {status === 'pending' && 'PENDING'}
        </div>
      )}
    </div>
  )
}
