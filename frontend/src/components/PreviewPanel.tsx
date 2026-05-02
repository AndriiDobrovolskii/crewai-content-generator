import { useState } from 'react'
import { Download, Eye, FileText } from 'lucide-react'
import { getDownloadUrl } from '../api'

interface Props {
  jobId: string | null
  files: Record<string, string>
  zipPath: string | null
  isRunning: boolean
}

function wrapPreview(html: string): string {
  return `
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 14px; line-height: 1.7; color: #1e293b;
          max-width: 860px; margin: 0 auto; padding: 24px;
          background: #fff;
        }
        table { border-collapse: collapse; width: 100%; }
        td, th { border: 1px solid #e2e8f0; padding: 8px 12px; }
        th { background: #f8fafc; font-weight: 600; }
        h2 { color: #1e293b; margin-top: 1.5em; }
        h3 { color: #334155; }
        .product-desc-wrap { max-width: 100%; }
      </style>
    </head>
    <body>${html}</body>
    </html>
  `
}

export function PreviewPanel({ jobId, files, zipPath, isRunning }: Props) {
  const langs = Object.keys(files)
  const [activeLang, setActiveLang] = useState<string | null>(null)

  // Auto-select first lang when files arrive
  const effectiveLang = activeLang && files[activeLang]
    ? activeLang
    : langs[0] ?? null

  const hasFiles = langs.length > 0

  return (
    <div className="panel-glow flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Eye className="w-3.5 h-3.5 text-dim" />
          <span className="text-xs font-medium text-dim uppercase tracking-wide">Preview</span>
        </div>

        {jobId && zipPath && (
          <a
            href={getDownloadUrl(jobId)}
            download
            className="btn-secondary !py-1 !px-3 !text-xs"
          >
            <Download className="w-3 h-3" />
            Завантажити ZIP
          </a>
        )}
      </div>

      {/* Language tabs */}
      {hasFiles && (
        <div className="flex items-center gap-1 px-3 py-2 border-b border-border overflow-x-auto flex-shrink-0">
          {langs.map((lang) => (
            <button
              key={lang}
              onClick={() => setActiveLang(lang)}
              className={`px-3 py-1 rounded text-xs font-mono font-medium whitespace-nowrap transition-all duration-100 ${
                effectiveLang === lang
                  ? 'bg-violet/25 text-violet-light border border-violet/40'
                  : 'text-dim hover:text-ink hover:bg-muted'
              }`}
            >
              {lang}
            </button>
          ))}
        </div>
      )}

      {/* Preview iframe or empty state */}
      <div className="flex-1 overflow-hidden min-h-0">
        {!hasFiles && !isRunning && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-ghost">
            <FileText className="w-8 h-8 opacity-30" />
            <span className="text-xs">Результат з'явиться після генерації</span>
          </div>
        )}

        {!hasFiles && isRunning && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-dim">
            <div className="live-dot w-3 h-3" />
            <span className="text-xs">Генерація в процесі...</span>
          </div>
        )}

        {hasFiles && effectiveLang && files[effectiveLang] && (
          <iframe
            key={effectiveLang}
            srcDoc={wrapPreview(files[effectiveLang])}
            className="w-full h-full border-0 bg-white animate-fade-in"
            sandbox="allow-same-origin"
            title={`Preview ${effectiveLang}`}
          />
        )}
      </div>
    </div>
  )
}
