import type { AppConfig, GenerateRequest, DiscoverRequest, JobState } from './types'

const BASE = '/api'

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch(`${BASE}/config`)
  if (!res.ok) throw new Error('Failed to fetch config')
  return res.json()
}

export async function startGenerate(req: GenerateRequest): Promise<string> {
  const res = await fetch(`${BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error('Failed to start generation')
  const data = await res.json()
  return data.job_id as string
}

export async function startDiscover(req: DiscoverRequest): Promise<string> {
  const res = await fetch(`${BASE}/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error('Failed to start discovery')
  const data = await res.json()
  return data.job_id as string
}

export async function fetchJobState(jobId: string): Promise<JobState> {
  const res = await fetch(`${BASE}/jobs/${jobId}`)
  if (!res.ok) throw new Error('Failed to fetch job state')
  return res.json()
}

export function getDownloadUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/download`
}

export function createSSEStream(
  jobId: string,
  onMessage: (line: string) => void,
  onDone: () => void,
): EventSource {
  const es = new EventSource(`${BASE}/jobs/${jobId}/stream`)
  es.onmessage = (e) => {
    if (e.data === '[DONE]') {
      onDone()
      es.close()
    } else {
      // Restore newlines escaped by SSE protocol
      onMessage(e.data.replace(/↵/g, '\n'))
    }
  }
  es.onerror = () => {
    onDone()
    es.close()
  }
  return es
}
