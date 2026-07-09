import { useState, useEffect, useRef } from 'react'
import { API_URL } from '../lib/config'

const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December']

function prettyMonth(ym) {
  if (!ym || ym.length < 7) return ym || ''
  return `${MONTH_NAMES[parseInt(ym.slice(5, 7), 10) - 1]} ${ym.slice(0, 4)}`
}

const GREETING = "Hi, I'm xspend. I've analysed your transactions and I'm ready to help. " +
                 "Use the prompts below for insights into your spending. " +
                 "Free-form chat is disabled while we're in beta."

export default function Chat() {
  const [opts, setOpts] = useState({ prompts: [], months: [], used: 0, limit: 5 })
  const [messages, setMessages] = useState([{ role: 'assistant', text: GREETING }])
  const [active, setActive] = useState(null)
  const [month, setMonth] = useState('')
  const [amount, setAmount] = useState('')
  const [asking, setAsking] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    fetch(`${API_URL}/chat/options`)
      .then(r => r.json())
      .then(d => { setOpts(d); if (d.months?.length) setMonth(d.months[0].value) })
      .catch(() => setMessages(m => [...m, { role: 'assistant', text: 'Could not load your insights. Refresh to try again.' }]))
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, active])

  const remaining = Math.max(0, (opts.limit ?? 5) - (opts.used ?? 0))
  const capped = remaining <= 0
  const needs = (p, f) => (p?.needs || []).includes(f)

  const pick = (p) => {
    if (capped || asking) return
    if (!needs(p, 'month') && !needs(p, 'amount')) { run(p); return }
    setActive(p)
  }

  const run = async (p) => {
    if (capped || asking) return
    const label = needs(p, 'amount')
      ? `${p.label} ($${Number(amount).toLocaleString()})`
      : needs(p, 'month') ? `${p.label} — ${prettyMonth(month)}` : p.label

    setMessages(m => [...m, { role: 'user', text: label }])
    setActive(null)
    setAsking(true)

    const body = { prompt_id: p.id }
    if (needs(p, 'month')) body.month = month
    if (needs(p, 'amount')) body.amount = parseFloat(amount)

    try {
      const res = await fetch(`${API_URL}/chat/prompt`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await res.json()
      if (!d.success) {
        setMessages(m => [...m, { role: 'assistant', text: d.error || 'Something went wrong.' }])
      } else {
        setMessages(m => [...m, { role: 'assistant', text: d.answer, disclaimer: d.disclaimer }])
        setOpts(o => ({ ...o, used: d.used ?? o.used }))
      }
    } catch {
      setMessages(m => [...m, { role: 'assistant', text: 'Could not reach the server. Try again in a moment.' }])
    } finally {
      setAsking(false)
      setAmount('')
    }
  }

  const canSubmit = active && (!needs(active, 'amount') || parseFloat(amount) > 0)

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#1a1a1a] mb-1">Insights</h1>
          <p className="text-[#5a5a5a] text-sm">Precise answers from your own statements</p>
        </div>
        <span className={`text-sm whitespace-nowrap ${capped ? 'text-amber-700' : 'text-[#8a8a85]'}`}>
          {capped ? 'None left this month' : `${remaining} of ${opts.limit} left this month`}
        </span>
      </div>

      <div className="bg-white rounded-2xl flex flex-col h-[calc(100vh-230px)] min-h-[560px]"
           style={{ border: '1px solid rgba(0,0,0,0.08)' }}>

        {/* Thread */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-[#e85d3c] flex items-center justify-center text-white text-sm font-bold mr-3 mt-1 flex-shrink-0">x</div>
              )}
              <div className={`max-w-[82%] rounded-2xl px-5 py-4 ${
                msg.role === 'user'
                  ? 'bg-[#e85d3c] text-white'
                  : 'bg-[#faf9f5] text-[#1a1a1a]'
              }`} style={msg.role === 'assistant' ? { border: '1px solid rgba(0,0,0,0.06)' } : {}}>
                <p className="text-[17px] leading-[1.65] whitespace-pre-wrap">{msg.text}</p>
                {msg.disclaimer && (
                  <p className="text-[13.5px] leading-[1.6] text-[#8a8a85] mt-4 pt-3"
                     style={{ borderTop: '1px solid rgba(0,0,0,0.07)' }}>
                    {msg.disclaimer}
                  </p>
                )}
              </div>
            </div>
          ))}
          {asking && (
            <div className="flex justify-start">
              <div className="w-8 h-8 rounded-lg bg-[#e85d3c] flex items-center justify-center text-white text-sm font-bold mr-3 mt-1">x</div>
              <div className="bg-[#faf9f5] rounded-2xl px-5 py-4 text-[#8a8a85] text-[17px]"
                   style={{ border: '1px solid rgba(0,0,0,0.06)' }}>Working on it…</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Config row */}
        {active && (
          <div className="px-6 pb-4 pt-4" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
            <div className="flex gap-3 items-end flex-wrap">
              {needs(active, 'month') && (
                <label className="flex-1 min-w-[160px]">
                  <span className="block text-xs text-[#8a8a85] mb-1.5">Month</span>
                  <select value={month} onChange={e => setMonth(e.target.value)}
                    className="w-full bg-[#faf9f5] rounded-lg px-3 py-2.5 text-[15px] text-[#1a1a1a] outline-none"
                    style={{ border: '1px solid rgba(0,0,0,0.08)' }}>
                    {opts.months.map(m => <option key={m.value} value={m.value}>{prettyMonth(m.value)}</option>)}
                  </select>
                </label>
              )}
              {needs(active, 'amount') && (
                <label className="flex-1 min-w-[140px]">
                  <span className="block text-xs text-[#8a8a85] mb-1.5">How much?</span>
                  <input type="number" min="1" placeholder="500" value={amount} autoFocus
                    onChange={e => setAmount(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && canSubmit && run(active)}
                    className="w-full bg-[#faf9f5] rounded-lg px-3 py-2.5 text-[15px] text-[#1a1a1a] outline-none"
                    style={{ border: '1px solid rgba(0,0,0,0.08)' }} />
                </label>
              )}
              <button onClick={() => setActive(null)}
                className="px-4 py-2.5 rounded-lg text-[15px] text-[#5a5a5a]"
                style={{ border: '1px solid rgba(0,0,0,0.08)' }}>Cancel</button>
              <button onClick={() => run(active)} disabled={!canSubmit}
                className={`px-5 py-2.5 rounded-lg text-[15px] font-semibold text-white ${
                  canSubmit ? 'bg-[#e85d3c]' : 'bg-black/10 cursor-not-allowed'}`}>
                Show me
              </button>
            </div>
          </div>
        )}

        {/* Prompt chips */}
        {!active && (
          <div className="px-6 pb-5 pt-4" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
            <div className="flex flex-wrap gap-2.5">
              {opts.prompts.map(p => (
                <button key={p.id} onClick={() => pick(p)} disabled={capped || asking}
                  className={`px-4 py-2.5 rounded-xl text-[15px] transition ${
                    capped || asking
                      ? 'bg-[#faf9f5] text-[#b0b0a8] cursor-not-allowed'
                      : 'bg-[#faf9f5] text-[#1a1a1a] hover:border-[#e85d3c]'}`}
                  style={{ border: '1px solid rgba(0,0,0,0.08)' }}>
                  {p.label}
                </button>
              ))}
            </div>
            <p className="text-[13px] text-[#8a8a85] mt-3.5">
              {capped
                ? `You've used all ${opts.limit} insights this month. They reset on the 1st.`
                : `Free-form chat is coming soon — each prompt uses one of your ${opts.limit} monthly insights.`}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
