import { useState, useEffect } from 'react'
import { Zap, Search, FolderOpen, ChevronDown } from 'lucide-react'
import type { AppConfig, GenerateRequest, DiscoverRequest } from '../types'
import { fetchConfig, startGenerate, startDiscover } from '../api'

interface Props {
  onJobStarted: (jobId: string, mode: 'generate' | 'discover') => void
  onDiscoveredUrls?: (urls: string[]) => void
  isRunning: boolean
  discoveredUrls?: string[]
}

const SOURCE_ICONS: Record<string, string> = {
  text: '📝', urls: '🌐', pdf: '📄',
  markdown: '📑', markdown_dir: '📁',
  auto_search: '🔍', auto_search_review: '🔎',
}

const SOURCE_PLACEHOLDERS: Record<string, string> = {
  text: 'Вставте технічні характеристики, опис, FAQ...',
  urls: 'https://example.com/product, https://store.com/item',
  pdf: 'C:\\docs\\spec.pdf, C:\\docs\\manual.pdf',
  markdown: 'C:\\docs\\spec.md',
  markdown_dir: 'C:\\docs\\product_folder',
  auto_search: '— поле не потрібне, агент шукатиме автоматично —',
  auto_search_review: 'Натисніть "Знайти URL" — результати з\'являться тут',
}

export function ConfigPanel({ onJobStarted, isRunning, discoveredUrls }: Props) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [productName, setProductName] = useState('')
  const [site, setSite] = useState('')
  const [category, setCategory] = useState('')
  const [sourceType, setSourceType] = useState('text')
  const [rawInput, setRawInput] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetchConfig().then((cfg) => {
      setConfig(cfg)
      if (cfg.sites.length > 0) setSite(cfg.sites[0].key)
      if (cfg.categories.length > 0) setCategory(cfg.categories[0])
    }).catch(() => setError('Не вдалося підключитися до API сервера'))
  }, [])

  // When HITL discovery returns URLs, auto-switch source to urls
  useEffect(() => {
    if (discoveredUrls && discoveredUrls.length > 0) {
      setSourceType('urls')
      setRawInput(discoveredUrls.join(', '))
    }
  }, [discoveredUrls])

  const selectedSite = config?.sites.find((s) => s.key === site)
  const isAutoSearch = sourceType === 'auto_search'
  const isHITL = sourceType === 'auto_search_review'

  const handleGenerate = async () => {
    if (!productName.trim()) { setError('Вкажіть назву продукту'); return }
    if (!site || !category) { setError('Оберіть магазин та категорію'); return }
    setError('')
    const req: GenerateRequest = {
      product_name: productName.trim(),
      site,
      category,
      source_type: sourceType,
      raw_input: rawInput.trim(),
    }
    const jobId = await startGenerate(req)
    onJobStarted(jobId, 'generate')
  }

  const handleDiscover = async () => {
    if (!productName.trim()) { setError('Вкажіть назву продукту'); return }
    setError('')
    const req: DiscoverRequest = { product_name: productName.trim(), site }
    const jobId = await startDiscover(req)
    onJobStarted(jobId, 'discover')
  }

  if (!config) {
    return (
      <div className="panel-glow p-6 flex items-center justify-center h-40">
        {error
          ? <p className="text-rose text-sm">{error}</p>
          : <div className="flex items-center gap-2 text-dim text-sm">
              <div className="live-dot" />
              <span>Завантаження конфігурації...</span>
            </div>
        }
      </div>
    )
  }

  return (
    <div className="panel-glow p-5 flex flex-col gap-5 animate-fade-in">

      {/* Header */}
      <div className="flex items-center gap-2 pb-3 border-b border-border">
        <div className="w-7 h-7 rounded-md bg-violet/20 flex items-center justify-center">
          <Zap className="w-3.5 h-3.5 text-violet-light" />
        </div>
        <span className="text-sm font-semibold text-ink">Параметри генерації</span>
      </div>

      {/* Product name */}
      <div>
        <label className="label">Назва продукту</label>
        <input
          className="input"
          placeholder="напр. Bambu Lab X1 Carbon"
          value={productName}
          onChange={(e) => setProductName(e.target.value)}
          disabled={isRunning}
        />
      </div>

      {/* Site selector */}
      <div>
        <label className="label">Магазин</label>
        <div className="relative">
          <select
            className="select pr-8"
            value={site}
            onChange={(e) => setSite(e.target.value)}
            disabled={isRunning}
          >
            {config.sites.map((s) => (
              <option key={s.key} value={s.key}>
                {s.key} · {s.country}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dim pointer-events-none" />
        </div>
        {selectedSite && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {selectedSite.languages.map((lang) => (
              <span key={lang} className="px-1.5 py-0.5 text-[10px] rounded bg-muted text-dim font-mono">
                {lang.toUpperCase()}
              </span>
            ))}
            <span className={`px-1.5 py-0.5 text-[10px] rounded font-mono ${
              selectedSite.ua_is_production ? 'bg-emerald/15 text-emerald' : 'bg-cyan/15 text-cyan'
            }`}>
              {selectedSite.ua_is_production ? 'UA=prod' : 'UA=review'}
            </span>
          </div>
        )}
      </div>

      {/* Category */}
      <div>
        <label className="label">Категорія продукту</label>
        <div className="relative">
          <select
            className="select pr-8"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={isRunning}
          >
            {config.categories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dim pointer-events-none" />
        </div>
      </div>

      {/* Source type */}
      <div>
        <label className="label">Джерело даних</label>
        <div className="grid grid-cols-2 gap-1.5">
          {config.source_types.map((st) => (
            <button
              key={st.value}
              onClick={() => !isRunning && setSourceType(st.value)}
              disabled={isRunning}
              className={`px-2.5 py-2 rounded-lg text-xs font-medium text-left transition-all duration-100 ${
                sourceType === st.value
                  ? 'bg-violet/20 border border-violet/50 text-violet-light'
                  : 'bg-surface border border-border text-dim hover:border-muted hover:text-ink'
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input textarea (hidden for pure auto_search) */}
      {!isAutoSearch && (
        <div>
          <label className="label">
            {isHITL ? 'URL для перевірки' : 'Вхідні дані'}
          </label>
          <textarea
            className="input resize-none font-mono text-xs"
            rows={isHITL ? 4 : 3}
            placeholder={SOURCE_PLACEHOLDERS[sourceType]}
            value={rawInput}
            onChange={(e) => setRawInput(e.target.value)}
            disabled={isRunning || isAutoSearch}
            readOnly={isHITL && !discoveredUrls}
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-rose text-xs py-2 px-3 rounded-lg bg-rose/10 border border-rose/20">
          {error}
        </p>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2 pt-1">
        {/* HITL discover button */}
        {isHITL && (
          <button
            className="btn-secondary w-full justify-center"
            onClick={handleDiscover}
            disabled={isRunning}
          >
            <Search className="w-4 h-4" />
            Знайти URL
          </button>
        )}

        {/* Main generate button */}
        <button
          className="btn-primary w-full justify-center"
          onClick={handleGenerate}
          disabled={isRunning}
        >
          {isRunning ? (
            <>
              <div className="live-dot" />
              Генерація...
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              Генерувати контент
            </>
          )}
        </button>
      </div>

    </div>
  )
}
