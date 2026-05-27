import { useState, useEffect, useRef } from 'react'
import { API_URL } from '../lib/config'

const FINANCE_FACTS = [
  { emoji:'💡', text:'People who track spending save 20% more on average than those who do not.' },
  { emoji:'📱', text:'The average person pays for 3 subscriptions they have not used in over a month.' },
  { emoji:'☕', text:'Cutting one $6 coffee per day adds up to $2,190 saved per year.' },
  { emoji:'🏦', text:'Automating savings increases the likelihood of reaching financial goals by 3x.' },
  { emoji:'🛒', text:'Grocery spending drops 23% on average when people track it consciously.' },
  { emoji:'💳', text:'The average American household carries $7,951 in credit card debt.' },
  { emoji:'📊', text:'Knowing where your money goes is the first step. Most people underestimate dining by 40%.' },
  { emoji:'🎯', text:'People with a written budget are 50% more likely to stick to their spending goals.' },
  { emoji:'✈️', text:'Travel spending planned in advance costs 30% less than last-minute bookings.' },
  { emoji:'🔄', text:'Subscription costs have grown 45% per household in the last 5 years.' },
]

const CATEGORIES = [
  'Uncategorized','Food & Dining','Groceries','Transport','Rent & Utilities',
  'Subscriptions','Health','Shopping','Entertainment','Travel',
  'Personal Care','Pets','Education','Salary','Transfer','Payment','Other'
]
const CURRENCIES = ['USD','EUR','GBP','INR','AUD','CAD','SGD','AED','JPY','CHF']
const TX_TYPES = ['expense','income','transfer','credit_card_payment','loan_payment','refund','excluded']

const EXCLUDED_TYPES = new Set(['credit_card_payment','loan_payment'])
const EXCLUDED_KEYWORDS = ['payment thank you','autopay payment','online payment','minimum payment']

function isAutoExcluded(tx) {
  if (EXCLUDED_TYPES.has(tx.transaction_type)) return true
  const desc = (tx.description || '').toLowerCase()
  return EXCLUDED_KEYWORDS.some(k => desc.includes(k))
}

const TYPE_COLORS = {
  expense:'#c81e1e', income:'#0d9268', transfer:'#8b5cf6',
  credit_card_payment:'#f59e0b', loan_payment:'#06b6d4',
  refund:'#10b981', excluded:'#4a4a6a', unknown:'#4a4a6a'
}
const TYPE_LABELS = {
  expense:'Expense', income:'Income', transfer:'Transfer',
  credit_card_payment:'Card Payment', loan_payment:'Loan Payment',
  refund:'Refund', excluded:'Excluded', unknown:'Unknown'
}
const CONF_COLORS = { high:'#0d9268', medium:'#e3a008', low:'#c81e1e' }

const emptyLine = {
  transaction_date: new Date().toISOString().split('T')[0],
  description:'', amount:'', currency:'USD',
  category:'Uncategorized', transaction_type:'expense',
}

const FILE_STATES = { waiting:'waiting', uploading:'uploading', done:'done', error:'error' }

// ── Fixed Expenses Review Card ──
function FixedReviewCard({ onDismiss }) {
  const [fixedSummary, setFixedSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [confirmed, setConfirmed] = useState(false)
  const [overrides, setOverrides] = useState({}) // merchant → true/false

  useState(() => {
    fetch(`${API_URL}/fixed-summary`)
      .then(r => r.json())
      .then(data => { setFixedSummary(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // Detect newly recurring — items that appear in last 2 months but weren't previously fixed
  const newRecurring = (fixedSummary?.fixed?.items || []).filter(item =>
    item.occurrences === 2 && !overrides[item.merchant]
  )

  const handleConfirm = async () => {
    const toUpdate = Object.entries(overrides)
    for (const [merchant, isFixed] of toUpdate) {
      await fetch(`${API_URL}/transactions/${merchant}/fixed`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_fixed: isFixed })
      }).catch(() => {})
    }
    setConfirmed(true)
    setTimeout(onDismiss, 1200)
  }

  if (loading) return null
  if (!fixedSummary?.fixed?.items?.length) return null
  if (confirmed) return (
    <div style={{ background:'rgba(16,185,129,0.08)', border:'1px solid rgba(16,185,129,0.2)', borderRadius:14, padding:'16px 20px', marginBottom:16, display:'flex', alignItems:'center', gap:10 }}>
      <span style={{ fontSize:18 }}>✓</span>
      <span style={{ color:'#10b981', fontSize:13, fontWeight:600 }}>Fixed expenses confirmed — they won't count toward your budget</span>
    </div>
  )

  const items = fixedSummary.fixed.items.slice(0, 6)
  const total = fixedSummary.fixed.total

  return (
    <div style={{ background:'#0f1117', border:'1px solid rgba(59,130,246,0.25)', borderRadius:16, padding:'20px 24px', marginBottom:20 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16 }}>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <span style={{ fontSize:16 }}>🔁</span>
            <span style={{ color:'#fff', fontSize:14, fontWeight:600 }}>We found your recurring expenses</span>
          </div>
          <p style={{ color:'#475569', fontSize:12 }}>
            These won't count toward your variable budget · {items.length} detected · ~${Math.round(total)}/mo
          </p>
        </div>
        <button onClick={onDismiss} style={{ background:'none', border:'none', color:'#475569', fontSize:16, cursor:'pointer', padding:0 }}>✕</button>
      </div>

      {/* Fixed items list */}
      <div style={{ display:'flex', flexDirection:'column', gap:6, marginBottom:16 }}>
        {items.map((item, i) => {
          const override = overrides[item.merchant]
          const isFixed = override !== undefined ? override : true
          return (
            <div key={i} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 14px', background:'#0a0d12', borderRadius:10 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <span style={{ fontSize:14 }}>
                  {item.merchant.toLowerCase().includes('netflix') ? '🎬' :
                   item.merchant.toLowerCase().includes('spotify') || item.merchant.toLowerCase().includes('apple') ? '🎵' :
                   item.merchant.toLowerCase().includes('hulu') || item.merchant.toLowerCase().includes('disney') ? '📺' :
                   item.merchant.toLowerCase().includes('gym') || item.merchant.toLowerCase().includes('fitness') ? '💪' :
                   item.merchant.toLowerCase().includes('insurance') || item.merchant.toLowerCase().includes('geico') ? '🛡️' :
                   item.merchant.toLowerCase().includes('rent') || item.merchant.toLowerCase().includes('hoa') ? '🏠' :
                   item.merchant.toLowerCase().includes('electric') || item.merchant.toLowerCase().includes('city light') ? '⚡' :
                   item.merchant.toLowerCase().includes('internet') || item.merchant.toLowerCase().includes('comcast') || item.merchant.toLowerCase().includes('xfinity') ? '📡' :
                   '🔒'}
                </span>
                <div>
                  <span style={{ color:'#e2e8f0', fontSize:13 }}>{item.merchant}</span>
                  {item.varies && <span style={{ color:'#64748b', fontSize:10, marginLeft:6 }}>~varies</span>}
                </div>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                <span style={{ color:'#64748b', fontSize:13, fontFamily:'monospace' }}>~${item.amount}/mo</span>
                {/* Toggle */}
                <div style={{ display:'flex', background:'#1e2030', borderRadius:8, overflow:'hidden' }}>
                  <button
                    onClick={() => setOverrides(p => ({...p, [item.merchant]: true}))}
                    style={{ padding:'4px 10px', fontSize:11, fontWeight:600, border:'none', cursor:'pointer', fontFamily:'inherit',
                      background: isFixed ? '#2563eb' : 'transparent',
                      color: isFixed ? '#fff' : '#475569' }}>
                    Fixed
                  </button>
                  <button
                    onClick={() => setOverrides(p => ({...p, [item.merchant]: false}))}
                    style={{ padding:'4px 10px', fontSize:11, fontWeight:600, border:'none', cursor:'pointer', fontFamily:'inherit',
                      background: !isFixed ? '#475569' : 'transparent',
                      color: !isFixed ? '#fff' : '#475569' }}>
                    Variable
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {fixedSummary.subscriptions?.count > 0 && (
        <div style={{ padding:'8px 14px', background:'rgba(139,92,246,0.06)', border:'1px solid rgba(139,92,246,0.15)', borderRadius:8, marginBottom:14, fontSize:12, color:'#94a3b8' }}>
          📱 {fixedSummary.subscriptions.count} subscriptions detected · ${Math.round(fixedSummary.subscriptions.total)}/mo
          <span style={{ color:'#64748b', marginLeft:6 }}>
            ({fixedSummary.subscriptions.items.slice(0,3).map(s => s.name).join(', ')}{fixedSummary.subscriptions.count > 3 ? ` +${fixedSummary.subscriptions.count - 3} more` : ''})
          </span>
        </div>
      )}

      {/* New recurring detected */}
      {newRecurring.length > 0 && (
        <div style={{ marginBottom:14, padding:'12px 16px', background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.15)', borderRadius:12 }}>
          <p style={{ color:'#f59e0b', fontSize:12, fontWeight:600, marginBottom:8 }}>🔁 New recurring expenses detected</p>
          {newRecurring.slice(0,3).map((item, i) => (
            <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'7px 0', borderBottom: i < newRecurring.slice(0,3).length-1 ? '1px solid rgba(245,158,11,0.1)' : 'none' }}>
              <span style={{ color:'#e2e8f0', fontSize:12 }}>{item.merchant}</span>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ color:'#64748b', fontSize:12, fontFamily:'monospace' }}>${item.amount}/mo</span>
                <button onClick={() => setOverrides(p => ({...p, [item.merchant]: true}))}
                  style={{ background:'rgba(245,158,11,0.1)', border:'1px solid rgba(245,158,11,0.3)', borderRadius:6, padding:'3px 8px', fontSize:11, color:'#f59e0b', cursor:'pointer', fontFamily:'DM Sans, Inter, sans-serif' }}>
                  Mark fixed
                </button>
                <button onClick={async () => {
                    setOverrides(p => ({...p, [item.merchant]: false}))
                    // Store dismissal so we never ask again for this merchant
                    await fetch(`${API_URL}/merchant-rules/dismiss`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ merchant: item.merchant })
                    }).catch(() => {})
                  }}
                  style={{ background:'none', border:'1px solid #1e2030', borderRadius:6, padding:'3px 8px', fontSize:11, color:'#475569', cursor:'pointer', fontFamily:'DM Sans, Inter, sans-serif' }}>
                  Not now
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display:'flex', gap:10 }}>
        <button onClick={handleConfirm}
          style={{ background:'#2563eb', color:'#fff', border:'none', borderRadius:10, padding:'9px 20px', fontSize:13, fontWeight:600, cursor:'pointer', fontFamily:'inherit' }}>
          ✓ Looks right
        </button>
        <button onClick={onDismiss}
          style={{ background:'none', border:'1px solid #1e2030', borderRadius:10, padding:'9px 16px', fontSize:13, color:'#475569', cursor:'pointer', fontFamily:'inherit' }}>
          Dismiss
        </button>
      </div>
    </div>
  )
}

export default function Upload() {
  const [tab, setTab] = useState('upload')

  const [fileQueue, setFileQueue] = useState([])
  const [drag, setDrag] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [allTx, setAllTx] = useState([])
  const [showExcluded, setShowExcluded] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editRow, setEditRow] = useState({})
  const [showFixedReview, setShowFixedReview] = useState(false)
  const [isFirstUpload, setIsFirstUpload] = useState(false)
  const [justSignedUp] = useState(() => {
    const val = localStorage.getItem('just_signed_up')
    if (val) localStorage.removeItem('just_signed_up')
    return val === 'true'
  })
  const [processingTime, setProcessingTime] = useState(0)
  const [factIndex, setFactIndex] = useState(0)
  const processingTimer = useRef(null)

  const [lines, setLines] = useState([{ ...emptyLine, id: Date.now() }])
  const [saving, setSaving] = useState(false)
  const [manualStatus, setManualStatus] = useState('')
  const [savedTx, setSavedTx] = useState([])
  const [manualBank, setManualBank] = useState('')

  const addLine = () => setLines(p => [...p, { ...emptyLine, id: Date.now() }])
  const updateLine = (id, f, v) => setLines(p => p.map(l => l.id === id ? {...l,[f]:v} : l))
  const removeLine = (id) => { if (lines.length > 1) setLines(p => p.filter(l => l.id !== id)) }

  const addFiles = (newFiles) => {
    const entries = Array.from(newFiles).map(file => ({
      id: Date.now() + Math.random(),
      file,
      status: FILE_STATES.waiting,
      bankName: '',
      result: null,
      error: null,
    }))
    setFileQueue(p => {
      const updated = [...p, ...entries]
      // Auto-start upload after short delay
      setTimeout(() => uploadAll(updated), 300)
      return updated
    })
  }

  // Start processing timer when uploading begins
  useEffect(() => {
    if (processing) {
      setProcessingTime(0)
      setFactIndex(0)
      processingTimer.current = setInterval(() => {
        setProcessingTime(t => {
          const next = t + 1
          if (next % 8 === 0) setFactIndex(i => (i + 1) % FINANCE_FACTS.length)
          return next
        })
      }, 1000)
    } else {
      if (processingTimer.current) clearInterval(processingTimer.current)
    }
    return () => { if (processingTimer.current) clearInterval(processingTimer.current) }
  }, [processing])

  const removeFile = (id) => setFileQueue(p => p.filter(f => f.id !== id))
  const updateFileBank = (id, bankName) => setFileQueue(p => p.map(f => f.id === id ? {...f, bankName} : f))

  const uploadSingle = async (entry) => {
    setFileQueue(p => p.map(f => f.id === entry.id ? {...f, status:FILE_STATES.uploading} : f))
    const fd = new FormData()
    fd.append('file', entry.file)
    const bank = entry.bankName.trim()
    const url = bank
      ? `${API_URL}/upload?bank_name=${encodeURIComponent(bank)}`
      : `${API_URL}/upload`
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 120000)  // 2 min timeout
      const res = await fetch(url, { method:'POST', body:fd })
      const data = await res.json()
      if (data.success) {
        setFileQueue(p => p.map(f => f.id === entry.id ? {...f, status:FILE_STATES.done, result:data} : f))
        return data.transactions || []
      } else {
        setFileQueue(p => p.map(f => f.id === entry.id ? {...f, status:FILE_STATES.error, error:data.error} : f))
        return []
      }
    } catch(e) {
      setFileQueue(p => p.map(f => f.id === entry.id ? {...f, status:FILE_STATES.error, error:'Upload timed out — but transactions may have been saved. Check your dashboard.'} : f))
      return []
    }
  }

  const uploadAll = async (queue) => {
    const currentQueue = queue || fileQueue
    const waiting = currentQueue.filter(f => f.status === FILE_STATES.waiting)
    if (!waiting.length) return
    // Check if this is the first upload ever
    try {
      const r = await fetch(`${API_URL}/transactions`)
      const existing = await r.json()
      if (Array.isArray(existing) && existing.length === 0) setIsFirstUpload(true)
    } catch {}
    setProcessing(true)
    setAllTx([])
    setShowFixedReview(false)

    for (const entry of waiting) {
      await uploadSingle(entry)
    }

    try {
      const res = await fetch(`${API_URL}/transactions`)
      const data = await res.json()
      const enriched = data.map(t => ({ ...t, excluded: isAutoExcluded(t) }))
      setAllTx(enriched)
      setShowFixedReview(true) // Show review card after upload
    } catch {}

    setProcessing(false)
  }

  const startEdit = (tx) => {
    setEditingId(tx.id)
    setEditRow({
      transaction_date: tx.transaction_date || tx.date || '',
      description: tx.description || '',
      amount: tx.amount || '',
      currency: tx.currency || 'USD',
      category: tx.category || 'Uncategorized',
      transaction_type: tx.transaction_type || 'expense',
      bank_source: tx.bank_source || '',
      notes: tx.notes || '',
    })
  }

  const cancelEdit = () => setEditingId(null)

  const saveEdit = async (id) => {
    try {
      await fetch(`${API_URL}/transactions/${id}`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          transaction_date: editRow.transaction_date,
          description: editRow.description,
          amount: parseFloat(editRow.amount),
          currency: editRow.currency,
          category: editRow.category,
          transaction_type: editRow.transaction_type,
          bank_source: editRow.bank_source,
          notes: editRow.notes,
        })
      })
      setAllTx(p => p.map(t => t.id === id ? {...t, ...editRow} : t))
      setSavedTx(p => p.map(t => t.id === id ? {...t, ...editRow} : t))
    } catch {}
    setEditingId(null)
  }

  const toggleExclude = (id) => setAllTx(p => p.map(t => t.id === id ? {...t, excluded: !t.excluded} : t))

  const handleSaveAll = async () => {
    const valid = lines.filter(l => l.description.trim() && l.amount && l.transaction_date)
    if (!valid.length) { setManualStatus('Fill in at least one complete row'); return }
    setSaving(true)
    setManualStatus('')
    const results = []
    for (const line of valid) {
      try {
        const res = await fetch(`${API_URL}/transactions/manual`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ ...line, amount: parseFloat(line.amount), bank_source: manualBank||'Manual Entry' })
        })
        const d = await res.json()
        if (d.success) results.push(d.transaction)
      } catch {}
    }
    setSaving(false)
    if (results.length) {
      setManualStatus(`✓ ${results.length} transaction${results.length>1?'s':''} saved`)
      setSavedTx(p => [...results, ...p])
      setLines([{ ...emptyLine, id: Date.now() }])
      setManualBank('')
    } else {
      setManualStatus('Failed to save.')
    }
  }

  const included = allTx.filter(t => !t.excluded)
  const excluded = allTx.filter(t => t.excluded)
  const displayList = showExcluded ? allTx : included

  const totalImported = fileQueue.reduce((s,f) => s + (f.result?.transactions_imported || 0), 0)
  const totalSkipped = fileQueue.reduce((s,f) => s + (f.result?.skipped_duplicates || 0), 0)
  const waitingCount = fileQueue.filter(f => f.status === FILE_STATES.waiting).length

  const S = {
    page: { padding:'32px 48px', maxWidth:1300, margin:'0 auto', fontFamily:'DM Sans, Inter, sans-serif', background:'#0a0a0f', minHeight:'100vh' },
    tabs: { display:'flex', gap:4, background:'#12121e', border:'1px solid #1e1e2e', borderRadius:14, padding:4, marginBottom:24, width:'fit-content' },
    tab: (a) => ({ padding:'9px 24px', borderRadius:10, fontSize:14, fontWeight:500, cursor:'pointer', border:'none', background:a?'#2563eb':'transparent', color:a?'#fff':'#6a6a8a', fontFamily:'inherit' }),
    card: { background:'#12121e', border:'1px solid #1e1e2e', borderRadius:18, padding:28 },
    label: { display:'block', color:'#6a6a8a', fontSize:11, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', marginBottom:8 },
    input: { width:'100%', background:'#0a0a0f', border:'1px solid #2a2a3a', borderRadius:10, padding:'11px 14px', color:'#fff', fontSize:14, outline:'none', boxSizing:'border-box', fontFamily:'inherit' },
    select: { width:'100%', background:'#0a0a0f', border:'1px solid #2a2a3a', borderRadius:10, padding:'11px 14px', color:'#fff', fontSize:14, outline:'none', boxSizing:'border-box', fontFamily:'inherit' },
    dropzone: (d) => ({ background:d?'rgba(37,99,235,0.06)':'#0a0a0f', border:`2px dashed ${d?'#2563eb':'#2a2a3a'}`, borderRadius:14, padding:'40px 32px', textAlign:'center', cursor:'pointer', transition:'all 0.2s', marginBottom:16 }),
    btn: { background:'#2563eb', color:'#fff', border:'none', borderRadius:12, padding:'12px 28px', fontSize:14, fontWeight:600, cursor:'pointer', fontFamily:'inherit' },
    btnSm: (color) => ({ background:'none', border:`1px solid ${color||'#2a2a3a'}`, borderRadius:7, padding:'4px 10px', fontSize:11, fontWeight:500, cursor:'pointer', fontFamily:'inherit', color:color||'#8888aa' }),
    editInput: { background:'#0a0a0f', border:'1px solid #3b82f6', borderRadius:6, padding:'5px 8px', color:'#fff', fontSize:12, outline:'none', fontFamily:'inherit', width:'100%' },
    editSelect: { background:'#0a0a0f', border:'1px solid #3b82f6', borderRadius:6, padding:'5px 8px', color:'#fff', fontSize:12, outline:'none', fontFamily:'inherit', width:'100%' },
    th: { padding:'9px 12px', color:'#4a4a6a', fontSize:10, fontWeight:600, textTransform:'uppercase', letterSpacing:1, whiteSpace:'nowrap' },
    td: { padding:'10px 12px', borderBottom:'1px solid #1a1a2a', verticalAlign:'middle' },
  }

  const statusIcon = { waiting:'⏳', uploading:'🔄', done:'✓', error:'✗' }
  const statusColor = { waiting:'#6a6a8a', uploading:'#3b82f6', done:'#0d9268', error:'#c81e1e' }

  return (
    <div style={S.page}>
      {justSignedUp && (
        <div style={{ background:'linear-gradient(135deg,rgba(16,185,129,0.1),rgba(59,130,246,0.1))', border:'1px solid rgba(16,185,129,0.2)', borderRadius:16, padding:'20px 24px', marginBottom:24, textAlign:'center' }}>
          <p style={{ fontSize:24, marginBottom:6 }}>🎉</p>
          <p style={{ color:'#10b981', fontSize:16, fontWeight:700, marginBottom:4 }}>You are in! Welcome to xspend</p>
          <p style={{ color:'#64748b', fontSize:13 }}>Now upload your first bank statement and see exactly where your money goes — in seconds.</p>
        </div>
      )}

      <div style={{ marginBottom:24 }}>
        <h1 style={{ fontSize:22, fontWeight:600, color:'#fff', marginBottom:4 }}>Upload your bank statement or transaction file</h1>
        <p style={{ color:'#6a6a8a', fontSize:13 }}>We support PDF, CSV, XLSX, OFX, and QFX · <span style={{color:'#3b82f6'}}>Best results: CSV, OFX, or QFX</span></p>
      </div>



      {tab === 'upload' && (
        <div style={S.card}>
          <p style={{ color:'#6a6a8a', fontSize:13, marginBottom:20 }}>
            Upload multiple files at once — CSV, PDF, XLSX or XLS. Mix different banks and formats in the same session.
          </p>

          <div
            style={S.dropzone(drag)}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }}
            onClick={() => document.getElementById('multiFileInput').click()}
          >
            <div style={{ fontSize:36, marginBottom:12 }}>📎</div>
            <p style={{ color:'#fff', fontWeight:600, fontSize:15, marginBottom:6 }}>Drop files here or click to browse</p>
            <p style={{ color:'#4a4a6a', fontSize:12, marginBottom:8 }}>PDF · CSV · XLSX · XLS · OFX · QFX</p>
            <p style={{ color:'#2563eb', fontSize:11, fontWeight:500 }}>Any bank · any format · we handle the rest</p>
            <input id="multiFileInput" type="file" accept=".pdf,.csv,.xlsx,.xls,.ofx,.qfx" multiple style={{ display:'none' }} onChange={e => addFiles(e.target.files)}/>
          </div>

          {fileQueue.length > 0 && (
            <div style={{ marginBottom:20 }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                <p style={{ color:'#8888aa', fontSize:12, fontWeight:500 }}>{fileQueue.length} file{fileQueue.length>1?'s':''} queued</p>
                {processing && <span style={{ color:'#3b82f6', fontSize:13, fontWeight:500 }}>⏳ Processing...</span>}
              </div>

              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {fileQueue.map(entry => (
                  <div key={entry.id} style={{ background:'#0a0a0f', border:'1px solid #1e1e2e', borderRadius:10, padding:'12px 16px', display:'flex', alignItems:'center', gap:12, flexWrap:'wrap' }}>
                    <span style={{ fontSize:16, color:statusColor[entry.status], flexShrink:0 }}>
                      {entry.status === 'uploading' ? '🔄' : statusIcon[entry.status]}
                    </span>
                    <div style={{ flex:1, minWidth:160 }}>
                      <p style={{ color:'#fff', fontSize:13, fontWeight:500, marginBottom:2 }}>{entry.file.name}</p>
                      <p style={{ color:'#4a4a6a', fontSize:11 }}>
                        {(entry.file.size/1024).toFixed(1)} KB · {entry.file.name.split('.').pop().toUpperCase()}
                        {entry.result && <span style={{ color:'#0d9268', marginLeft:8 }}>✓ {entry.result.transactions_imported} imported{entry.result.skipped_duplicates>0?`, ${entry.result.skipped_duplicates} duplicate${entry.result.skipped_duplicates>1?'s':''} skipped${entry.result.skipped_merchants?.length?' ('+entry.result.skipped_merchants.slice(0,2).join(', ')+(entry.result.skipped_merchants.length>2?'…':'')+')':''}`:''}</span>}
                        {entry.result?.bank_source && entry.result.bank_source !== 'Unknown Bank' && <span style={{ color:'#8888aa', marginLeft:8 }}>🏦 {entry.result.bank_source}</span>}
                        {entry.error && (
                          <span style={{ color:'#ef4444', marginLeft:8, display:'block', marginTop:4, fontSize:11, lineHeight:1.5 }}>
                            ✗ {entry.error}
                          </span>
                        )}
                      </p>
                    </div>
                    {entry.status === FILE_STATES.waiting && (
                      <input style={{ ...S.input, width:180, padding:'7px 10px', fontSize:12 }} placeholder="Bank (auto-detected)" value={entry.bankName} onChange={e => updateFileBank(entry.id, e.target.value)}/>
                    )}
                    {entry.status === FILE_STATES.uploading && (
                      <div style={{ width:120, height:4, background:'#1e1e2e', borderRadius:99, overflow:'hidden' }}>
                        <div style={{ height:'100%', background:'#3b82f6', width:'60%', borderRadius:99 }}/>
                      </div>
                    )}
                    {entry.status === FILE_STATES.waiting && (
                      <button onClick={() => removeFile(entry.id)} style={{ background:'none', border:'none', color:'#4a4a6a', fontSize:16, cursor:'pointer', padding:'0 4px' }}>✕</button>
                    )}
                  </div>
                ))}
              </div>

              {fileQueue.some(f => f.status === FILE_STATES.done) && !processing && (
                <div style={{ marginTop:12, background:'#0a0a0f', border:'1px solid #1e1e2e', borderRadius:10, padding:'10px 16px', display:'flex', gap:20, flexWrap:'wrap', alignItems:'center' }}>
                  <span style={{ color:'#0d9268', fontSize:13, fontWeight:600 }}>✓ {totalImported} transactions imported</span>
                  {totalSkipped > 0 && <span style={{ color:'#6a6a8a', fontSize:12 }}>{totalSkipped} duplicates skipped</span>}
                  <span style={{ color:'#6a6a8a', fontSize:12 }}>across {fileQueue.filter(f=>f.status===FILE_STATES.done).length} file{fileQueue.filter(f=>f.status===FILE_STATES.done).length>1?'s':''}</span>
                  {fileQueue.some(f => f.status === FILE_STATES.error) && (
                    <span style={{ color:'#f59e0b', fontSize:11, marginLeft:'auto' }}>
                      💡 Some files failed — try CSV or OFX for better results
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── FIRST UPLOAD CELEBRATION ── */}
          {isFirstUpload && !processing && fileQueue.some(f => f.status === FILE_STATES.done) && (
            <div style={{ background:'rgba(16,185,129,0.06)', border:'1px solid rgba(16,185,129,0.2)', borderRadius:14, padding:'16px 20px', marginBottom:16, display:'flex', alignItems:'center', gap:12 }}>
              <span style={{ fontSize:24 }}>🎉</span>
              <div>
                <p style={{ color:'#10b981', fontSize:14, fontWeight:700, marginBottom:2 }}>Amazing first step!</p>
                <p style={{ color:'#475569', fontSize:12 }}>Your spending data is ready. Head to your dashboard to see the full picture.</p>
              </div>
            </div>
          )}

          {/* ── FINANCE FACTS during long processing ── */}
          {processing && processingTime >= 10 && (
            <div style={{ background:'rgba(59,130,246,0.05)', border:'1px solid rgba(59,130,246,0.15)', borderRadius:14, padding:'18px 20px', marginBottom:16, transition:'all 0.5s' }}>
              <p style={{ color:'#334155', fontSize:10, fontWeight:600, textTransform:'uppercase', letterSpacing:'1px', marginBottom:8 }}>💭 While we process your data...</p>
              <p style={{ color:'#e2e8f0', fontSize:14, fontWeight:500, lineHeight:1.6 }}>
                {FINANCE_FACTS[factIndex].emoji} {FINANCE_FACTS[factIndex].text}
              </p>
            </div>
          )}

          {/* ── FIXED REVIEW CARD ── */}
          {showFixedReview && (
            <FixedReviewCard onDismiss={() => setShowFixedReview(false)} />
          )}

          {allTx.length > 0 && (
            <div style={{ marginTop:24, borderRadius:14, overflow:'hidden', border:'1px solid #1e1e2e' }}>
              <div style={{ padding:'12px 16px', borderBottom:'1px solid #1e1e2e', display:'flex', justifyContent:'space-between', alignItems:'center', background:'#0a0a0f', flexWrap:'wrap', gap:10 }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                  <p style={{ color:'#fff', fontWeight:600, fontSize:13 }}>All transactions — {allTx.length} total</p>
                  <span style={{ color:'#0d9268', fontSize:11, background:'rgba(13,146,104,0.1)', padding:'2px 8px', borderRadius:5 }}>✓ {included.length} in spending</span>
                  {excluded.length > 0 && <span style={{ color:'#6a6a8a', fontSize:11, background:'#1e1e2e', padding:'2px 8px', borderRadius:5 }}>{excluded.length} excluded</span>}
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ color:'#4a4a6a', fontSize:11 }}>Show excluded</span>
                  <div onClick={() => setShowExcluded(s => !s)}
                    style={{ width:36, height:20, borderRadius:99, cursor:'pointer', background:showExcluded?'#2563eb':'#2a2a3a', position:'relative', transition:'background 0.2s' }}>
                    <span style={{ position:'absolute', top:2, left:showExcluded?18:2, width:16, height:16, borderRadius:'50%', background:'#fff', transition:'left 0.2s', display:'block' }}/>
                  </div>
                </div>
              </div>

              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse', minWidth:860 }}>
                  <thead>
                    <tr style={{ background:'#0a0a0f', borderBottom:'1px solid #1e1e2e' }}>
                      {['Date','Description','Amount','Category','Type','Conf','Notes',''].map((h,i) => (
                        <th key={i} style={{ ...S.th, textAlign:i===2?'right':'left' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {displayList.map(tx => {
                      const isEditing = editingId !== null && editingId === tx.id
                      const excl = tx.excluded
                      const date = tx.transaction_date || tx.date || ''
                      const txType = tx.transaction_type || 'expense'
                      const conf = tx.classification_confidence || 'medium'
                      return (
                        <tr key={tx.id} style={{ borderBottom:'1px solid #1a1a2a', background:excl?'rgba(255,255,255,0.01)':'transparent', opacity:excl?0.55:1 }}>
                          <td style={S.td}>
                            {isEditing
                              ? <input type="date" style={{...S.editInput,width:120}} value={editRow.transaction_date} onChange={e=>setEditRow({...editRow,transaction_date:e.target.value})}/>
                              : <span style={{ color:'#6a6a8a', fontSize:12 }}>{date}</span>}
                          </td>
                          <td style={{...S.td, maxWidth:240}}>
                            {isEditing
                              ? <input style={S.editInput} value={editRow.description} onChange={e=>setEditRow({...editRow,description:e.target.value})}/>
                              : <div>
                                  <span style={{ color:excl?'#6a6a8a':'#fff', fontSize:13 }}>{tx.description}</span>
                                  {tx.is_fixed && !excl && <span style={{ marginLeft:6, fontSize:10, color:'#64748b', background:'#1e2030', padding:'1px 6px', borderRadius:4 }}>fixed</span>}
                                  {excl && <span style={{ marginLeft:7, fontSize:10, color:'#4a4a6a', background:'#1e1e2e', padding:'1px 6px', borderRadius:4 }}>excluded</span>}
                                  {tx.needs_review && !excl && <span style={{ marginLeft:6, fontSize:10, color:'#e3a008', background:'rgba(227,160,8,0.1)', padding:'1px 5px', borderRadius:3 }}>review</span>}
                                </div>}
                          </td>
                          <td style={{...S.td, textAlign:'right'}}>
                            {isEditing
                              ? <input type="number" style={{...S.editInput,width:90,textAlign:'right'}} value={editRow.amount} onChange={e=>setEditRow({...editRow,amount:e.target.value})}/>
                              : <span style={{ color:excl?'#4a4a6a':parseFloat(tx.amount)>=0?'#0d9268':'#c81e1e', fontWeight:600, fontSize:13, fontFamily:'monospace' }}>
                                  {parseFloat(tx.amount)>=0?'+':'-'}${Math.abs(parseFloat(tx.amount||0)).toFixed(2)}
                                </span>}
                          </td>
                          <td style={S.td}>
                            {isEditing
                              ? <select style={{...S.editSelect,width:140}} value={editRow.category} onChange={e=>setEditRow({...editRow,category:e.target.value})}>
                                  {CATEGORIES.map(c=><option key={c}>{c}</option>)}
                                </select>
                              : <span style={{ background:'#1e1e2e', color:excl?'#4a4a6a':'#8888aa', fontSize:11, padding:'3px 9px', borderRadius:5 }}>{tx.category}</span>}
                          </td>
                          <td style={S.td}>
                            {isEditing
                              ? <select style={{...S.editSelect,width:130}} value={editRow.transaction_type} onChange={e=>setEditRow({...editRow,transaction_type:e.target.value})}>
                                  {TX_TYPES.map(t=><option key={t}>{t}</option>)}
                                </select>
                              : <span style={{ fontSize:11, color:excl?'#4a4a6a':TYPE_COLORS[txType], background:`${TYPE_COLORS[txType]}15`, padding:'3px 8px', borderRadius:4 }}>
                                  {excl?'Excluded':TYPE_LABELS[txType]||txType}
                                </span>}
                          </td>
                          <td style={S.td}>
                            <span style={{ fontSize:11, color:CONF_COLORS[conf]||'#6a6a8a' }}>● {conf}</span>
                          </td>
                          <td style={{...S.td, minWidth:120}}>
                            {isEditing
                              ? <input style={S.editInput} placeholder="Note..." value={editRow.notes||''} onChange={e=>setEditRow({...editRow,notes:e.target.value})}/>
                              : <span style={{ color:'#4a4a6a', fontSize:11 }}>{tx.notes||'—'}</span>}
                          </td>
                          <td style={{...S.td, whiteSpace:'nowrap'}}>
                            {isEditing
                              ? <div style={{ display:'flex', gap:5 }}>
                                  <button onClick={()=>saveEdit(tx.id)} style={{ background:'#0d9268', color:'#fff', border:'none', borderRadius:7, padding:'5px 12px', fontSize:11, cursor:'pointer', fontWeight:600, fontFamily:'inherit' }}>Save</button>
                                  <button onClick={cancelEdit} style={S.btnSm()}>✕</button>
                                </div>
                              : <div style={{ display:'flex', gap:5 }}>
                                  <button onClick={()=>startEdit(tx)} style={S.btnSm('#4a4a6a')}>Edit</button>
                                  <button onClick={()=>toggleExclude(tx.id)} style={S.btnSm(excl?'#0d9268':'#6a6a8a')}>
                                    {excl?'Include':'Exclude'}
                                  </button>
                                </div>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div style={{ padding:'10px 16px', borderTop:'1px solid #1e1e2e', background:'#0a0a0f', display:'flex', justifyContent:'space-between' }}>
                <p style={{ color:'#4a4a6a', fontSize:11 }}>Payroll, Zelle, Venmo, wire and card payments excluded by default · always editable</p>
                <p style={{ color:'#4a4a6a', fontSize:11 }}>{included.length} in spending · {excluded.length} excluded</p>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'manual' && (
        <div style={S.card}>
          <p style={{ color:'#6a6a8a', fontSize:13, marginBottom:20 }}>
            Add transactions line by line. Click <strong style={{ color:'#fff' }}>+ Add Row</strong> for more entries.
          </p>
          <div style={{ marginBottom:16, maxWidth:320 }}>
            <label style={S.label}>Bank / Account <span style={{ textTransform:'none', letterSpacing:0, fontWeight:400, color:'#4a4a6a' }}>(optional)</span></label>
            <input style={S.input} placeholder="e.g. Chase, HDFC..." value={manualBank} onChange={e=>setManualBank(e.target.value)}/>
          </div>
          <div style={{ borderRadius:12, overflow:'hidden', border:'1px solid #1e1e2e', marginBottom:14 }}>
            <div style={{ display:'grid', gridTemplateColumns:'130px 1fr 110px 80px 160px 130px 28px', background:'#0a0a0f', borderBottom:'1px solid #1e1e2e' }}>
              {['Date','Description','Amount','Currency','Category','Type',''].map((h,i) => (
                <div key={i} style={{ padding:'9px 12px', color:'#4a4a6a', fontSize:10, fontWeight:600, textTransform:'uppercase', letterSpacing:1 }}>{h}</div>
              ))}
            </div>
            {lines.map((line, idx) => (
              <div key={line.id} style={{ display:'grid', gridTemplateColumns:'130px 1fr 110px 80px 160px 130px 28px', borderBottom:'1px solid #1a1a2a', background:idx%2===0?'#12121e':'#0f0f1a', alignItems:'center' }}>
                <div style={{ padding:'7px 10px' }}>
                  <input type="date" style={{...S.input,padding:'6px 8px',fontSize:11}} value={line.transaction_date} onChange={e=>updateLine(line.id,'transaction_date',e.target.value)}/>
                </div>
                <div style={{ padding:'7px 10px' }}>
                  <input style={{...S.input,padding:'6px 10px',fontSize:13}} placeholder="Merchant / description..." value={line.description} onChange={e=>updateLine(line.id,'description',e.target.value)}/>
                </div>
                <div style={{ padding:'7px 10px' }}>
                  <input type="number" style={{...S.input,padding:'6px 8px',fontSize:12}} placeholder="-45.99" value={line.amount} onChange={e=>updateLine(line.id,'amount',e.target.value)}/>
                </div>
                <div style={{ padding:'7px 6px' }}>
                  <select style={{...S.select,padding:'6px 6px',fontSize:11}} value={line.currency} onChange={e=>updateLine(line.id,'currency',e.target.value)}>
                    {CURRENCIES.map(c=><option key={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ padding:'7px 6px' }}>
                  <select style={{...S.select,padding:'6px 6px',fontSize:11}} value={line.category} onChange={e=>updateLine(line.id,'category',e.target.value)}>
                    {CATEGORIES.map(c=><option key={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ padding:'7px 6px' }}>
                  <select style={{...S.select,padding:'6px 6px',fontSize:11}} value={line.transaction_type} onChange={e=>updateLine(line.id,'transaction_type',e.target.value)}>
                    {TX_TYPES.map(t=><option key={t}>{t}</option>)}
                  </select>
                </div>
                <div style={{ padding:'7px 4px', textAlign:'center' }}>
                  <button onClick={()=>removeLine(line.id)} style={{ background:'none', border:'none', color:'#4a4a6a', fontSize:14, cursor:'pointer' }}>✕</button>
                </div>
              </div>
            ))}
          </div>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20 }}>
            <button onClick={addLine} style={{ background:'#1e1e2e', border:'1px solid #2a2a3a', borderRadius:8, padding:'6px 14px', fontSize:12, cursor:'pointer', color:'#8888aa', fontFamily:'inherit' }}>+ Add Row</button>
            <p style={{ color:'#4a4a6a', fontSize:11 }}>Use − for expenses and + for income</p>
          </div>
          <button onClick={handleSaveAll} disabled={saving} style={{ ...S.btn, opacity:saving?0.5:1 }}>
            {saving ? 'Saving...' : `💾 Save ${lines.filter(l=>l.description&&l.amount).length} Transaction${lines.filter(l=>l.description&&l.amount).length!==1?'s':''}`}
          </button>
          {manualStatus && (
            <p style={{ marginTop:12, fontSize:13, fontWeight:600, color:manualStatus.startsWith('✓')?'#0d9268':'#c81e1e' }}>{manualStatus}</p>
          )}
        </div>
      )}
    </div>
  )
}
