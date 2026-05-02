import { Check, Circle, Loader } from 'lucide-react'
import { PIPELINE_STAGES, type StageStatus } from '../types'

interface Props {
  logLines: string[]
  isRunning: boolean
  isDone: boolean
}

// Heuristic: map log keywords → agent stage
const STAGE_KEYWORDS: Record<string, string[]> = {
  researcher:  ['web researcher', 'researcher', 'url discovery', 'fetching url', 'знайдено'],
  analyst:     ['tech analyst', 'analyst', 'tech spec', 'extracting spec', 'характеристик'],
  seo:         ['seo strategist', 'seo', 'keyword', 'search intent'],
  copywriter:  ['copywriter', 'writing', 'marketing', 'generating content'],
  qa:          ['qa editor', 'editor', 'quality', 'перевірк'],
  frontend:    ['html architect', 'frontend', 'html integration', 'schema'],
  localizer:   ['localiz', 'translat', 'переклад', 'локалізац'],
}

function detectActiveStage(logLines: string[]): string | null {
  const recent = logLines.slice(-20).join(' ').toLowerCase()
  for (const [stageId, keywords] of Object.entries(STAGE_KEYWORDS)) {
    if (keywords.some((kw) => recent.includes(kw))) return stageId
  }
  return null
}

function buildStageStatuses(
  logLines: string[],
  isRunning: boolean,
  isDone: boolean,
): Record<string, StageStatus> {
  const statuses: Record<string, StageStatus> = {}
  const fullLog = logLines.join(' ').toLowerCase()
  const activeId = isRunning ? detectActiveStage(logLines) : null

  let foundActive = false
  for (const stage of PIPELINE_STAGES) {
    const hasKeyword = STAGE_KEYWORDS[stage.id]?.some((kw) => fullLog.includes(kw))

    if (isDone) {
      statuses[stage.id] = 'done'
    } else if (!isRunning) {
      statuses[stage.id] = hasKeyword ? 'done' : 'waiting'
    } else if (stage.id === activeId) {
      statuses[stage.id] = 'active'
      foundActive = true
    } else if (!foundActive && hasKeyword) {
      statuses[stage.id] = 'done'
    } else {
      statuses[stage.id] = 'waiting'
    }
  }

  return statuses
}

export function PipelineStatus({ logLines, isRunning, isDone }: Props) {
  const statuses = buildStageStatuses(logLines, isRunning, isDone)

  return (
    <div className="panel-glow p-4">
      <p className="text-[10px] font-medium text-dim uppercase tracking-wide mb-3">Pipeline Stages</p>
      <div className="flex flex-col gap-1">
        {PIPELINE_STAGES.map((stage, idx) => {
          const status = statuses[stage.id] ?? 'waiting'
          return (
            <div
              key={stage.id}
              className={`flex items-center gap-2.5 py-1.5 px-2 rounded-lg transition-all duration-300 ${
                status === 'active' ? 'bg-cyan/8 border border-cyan/20' :
                status === 'done'   ? 'opacity-60' : 'opacity-30'
              }`}
            >
              {/* Connector line */}
              <div className="flex flex-col items-center gap-0">
                <div className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 ${
                  status === 'done'    ? 'bg-emerald/20 text-emerald' :
                  status === 'active'  ? 'bg-cyan/20 text-cyan' :
                  status === 'error'   ? 'bg-rose/20 text-rose' :
                                         'bg-ghost/20 text-ghost'
                }`}>
                  {status === 'done'   && <Check className="w-2.5 h-2.5" />}
                  {status === 'active' && <Loader className="w-2.5 h-2.5 animate-spin" />}
                  {status === 'waiting' && <Circle className="w-2.5 h-2.5" />}
                </div>
              </div>

              <span className="text-xs font-ui">{stage.emoji} {stage.label}</span>

              {status === 'active' && (
                <span className="ml-auto text-[10px] text-cyan font-mono animate-pulse">running</span>
              )}
              {status === 'done' && (
                <span className="ml-auto text-[10px] text-emerald font-mono">done</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
