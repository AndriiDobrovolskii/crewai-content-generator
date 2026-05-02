export type JobStatus = 'pending' | 'running' | 'done' | 'error'

export interface SiteInfo {
  key: string
  label: string
  country: string
  languages: string[]
  ua_is_production: boolean
}

export interface SourceType {
  value: string
  label: string
}

export interface AppConfig {
  sites: SiteInfo[]
  categories: string[]
  source_types: SourceType[]
}

export interface JobState {
  job_id: string
  status: JobStatus
  files: Record<string, string>
  zip_path: string | null
  error: string | null
  discovered_urls: string[]
}

export interface GenerateRequest {
  product_name: string
  site: string
  category: string
  source_type: string
  raw_input: string
}

export interface DiscoverRequest {
  product_name: string
  site: string
}

// Pipeline stage for visual status indicator
export type StageStatus = 'waiting' | 'active' | 'done' | 'error'

export interface PipelineStage {
  id: string
  label: string
  emoji: string
}

export const PIPELINE_STAGES: PipelineStage[] = [
  { id: 'researcher',  label: 'Web Researcher',   emoji: '🔍' },
  { id: 'analyst',     label: 'Tech Analyst',      emoji: '⚙️' },
  { id: 'seo',         label: 'SEO Strategist',    emoji: '📊' },
  { id: 'copywriter',  label: 'Copywriter',         emoji: '✍️' },
  { id: 'qa',          label: 'QA Editor',          emoji: '✅' },
  { id: 'frontend',    label: 'HTML Architect',     emoji: '🏗️' },
  { id: 'localizer',   label: 'Localizer',          emoji: '🌐' },
]
