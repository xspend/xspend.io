import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { API_URL } from '../lib/config'

const fmt = n => '$' + Math.round(Math.abs(n) || 0).toLocaleString()
const fmtD = n => '$' + Math.abs(n).toFixed(2)
const F = 'DM Sans, Inter, sans-serif'

const CATEGORY_COLORS = {
  'Food & Dining': '#f59e0b',
  'Groceries': '#10b981',
  'Transport': '#3b82f6',
  'Rent & Utilities': '#6366f1',
  'Subscriptions': '#8b5cf6',
  'Health': '#ec4899',
  'Shopping': '#f97316',
  'Entertainment': '#14b8a6',
  'Travel': '#06b6d4',
  'Personal Care': '#e879f9',
  'Pets': '#84cc16',
  'Education': '#f59e0b',
  'Other': '#64748b',
}

// ── Project Card ──────────────────────────────────────────────────────────────
function ProjectCard({ project, onDelete, allTransactions }) {
  const [open, setOpen] = useState(false)

  const projectTxs = allTransactions.filter(t =>
    t.project_id === project.id &&
    t.transaction_type === 'expense' &&
    t.amount < 0
  )

  const total = projectTxs.reduce((s, t) => s + Math.abs(t.amount), 0)
  const count = projectTxs.length

  // Category breakdown
  const catMap = projectTxs.reduce((acc, t) => {
    const c = t.category || 'Other'
    acc[c] = (acc[c] || 0) + Math.abs(t.amount)
    return acc
  }, {})

  const topCats = Object.entries(catMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([name, val]) => ({ name, val, pct: Math.round(val / total * 100) }))

  const QUICK_EMOJIS = {
    'trip': '✈️', 'travel': '✈️', 'vacation': '🏖️',
    'home': '🏠', 'house': '🏠', 'reno': '🔨', 'renovation': '🔨',
    'wedding': '💍', 'baby': '👶', 'kids': '👶',
    'car': '🚗', 'vehicle': '🚗',
    'work': '💼', 'business': '💼',
    'health': '💊', 'medical': '💊',
    'gift': '🎁', 'birthday': '🎂',
    'food': '🍽️', 'dining': '🍽️',
  }

  const getEmoji = name => {
    const n = name.toLowerCase()
    for (const [k, v] of Object.entries(QUICK_EMOJIS)) {
      if (n.includes(k)) return v
    }
    return '📁'
  }

  return (
    <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:18, overflow:'hidden', transition:'transform 0.15s' }}
      onMouseEnter={e => e.currentTarget.style.transform='translateY(-2px)'}
      onMouseLeave={e => e.currentTarget.style.transform='none'}>

      {/* Header */}
      <div style={{ padding:'20px 22px 16px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:42, height:42, borderRadius:12, background:'rgba(99,102,241,0.1)', border:'1px solid rgba(99,102,241,0.2)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>
              {getEmoji(project.name)}
            </div>
            <div>
              <p style={{ color:'#f1f5f9', fontSize:15, fontWeight:700, marginBottom:2 }}>{project.name}</p>
              <p style={{ color:'#334155', fontSize:11 }}>{count} transaction{count !== 1 ? 's' : ''} tagged</p>
            </div>
          </div>
          <button onClick={() => onDelete(project.id)}
            style={{ background:'none', border:'none', color:'#283244', cursor:'pointer', fontSize:16, padding:'4px' }}>✕</button>
        </div>

        {/* Total */}
        <p style={{ fontSize:32, fontWeight:800, color: count > 0 ? '#f1f5f9' : '#283244', fontFamily:'monospace', letterSpacing:'-1px', marginBottom:12 }}>
          {fmt(total)}
        </p>

        {/* Category breakdown bar */}
        {topCats.length > 0 && (
          <div>
            <div style={{ display:'flex', height:6, borderRadius:99, overflow:'hidden', gap:1, marginBottom:10 }}>
              {topCats.map((c, i) => (
                <div key={i} style={{ width: c.pct + '%', background: CATEGORY_COLORS[c.name] || '#64748b', borderRadius:99, transition:'width 0.5s' }}/>
              ))}
            </div>
            <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
              {topCats.map((c, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:4 }}>
                  <div style={{ width:7, height:7, borderRadius:2, background: CATEGORY_COLORS[c.name] || '#64748b', flexShrink:0 }}/>
                  <span style={{ fontSize:11, color:'#475569' }}>{c.name} {c.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {count === 0 && (
          <p style={{ fontSize:12, color:'#283244', marginTop:4 }}>
            Tag transactions from the <Link to="/app/transactions" style={{ color:'#3b82f6', textDecoration:'none' }}>Transactions</Link> page
          </p>
        )}
      </div>
    </div>
  )
}

// ── Create Project Modal ──────────────────────────────────────────────────────
function CreateProjectModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  const EXAMPLES = [
    { label:'✈️ Trip', name:'Trip' },
    { label:'🏠 Home', name:'Home' },
    { label:'💍 Wedding', name:'Wedding' },
    { label:'🛍️ Big Purchase', name:'Big Purchase' },
    { label:'🔨 Renovation', name:'Renovation' },
    { label:'👶 Baby', name:'Baby' },
  ]

  const submit = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      await fetch(`${API_URL}/projects`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type: 'custom', target_amount: null, target_date: null })
      })
      onCreated(); onClose()
    } catch(e) { console.error(e) }
    finally { setSaving(false) }
  }

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.8)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:1000, backdropFilter:'blur(4px)' }} onClick={onClose}>
      <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:20, padding:32, width:440, fontFamily:F }} onClick={e => e.stopPropagation()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:24 }}>
          <div>
            <h2 style={{ color:'#f1f5f9', fontSize:18, fontWeight:700, margin:0, marginBottom:4 }}>New project</h2>
            <p style={{ color:'#475569', fontSize:12, margin:0 }}>Track spending for anything that matters to you</p>
          </div>
          <button onClick={onClose} style={{ background:'none', border:'none', color:'#475569', fontSize:18, cursor:'pointer' }}>✕</button>
        </div>

        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:'#475569', fontWeight:600, letterSpacing:'1px', textTransform:'uppercase', marginBottom:8 }}>Name</div>
          <input style={{ background:'#0a0d12', border:'1px solid #1e2030', borderRadius:10, padding:'11px 14px', color:'#fff', fontSize:14, outline:'none', width:'100%', fontFamily:F, boxSizing:'border-box' }}
            placeholder="e.g. Japan Trip" autoFocus value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && name && submit()}/>
        </div>

        <div style={{ marginBottom:28 }}>
          <div style={{ fontSize:11, color:'#334155', marginBottom:10 }}>Quick start</div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
            {EXAMPLES.map(ex => (
              <button key={ex.name} onClick={() => setName(ex.name)}
                style={{ background: name === ex.name ? 'rgba(99,102,241,0.15)' : '#0a0d12', border: `1px solid ${name === ex.name ? '#6366f1' : '#1e2030'}`, borderRadius:10, padding:'8px 14px', fontSize:13, color: name === ex.name ? '#818cf8' : '#64748b', cursor:'pointer', fontFamily:F }}>
                {ex.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ background:'rgba(99,102,241,0.06)', border:'1px solid rgba(99,102,241,0.15)', borderRadius:10, padding:'12px 16px', marginBottom:24 }}>
          <p style={{ color:'#64748b', fontSize:12, lineHeight:1.6, margin:0 }}>
            Categories show <em>what</em> you spent. Projects show <em>why</em> — like adding songs to a playlist.
          </p>
        </div>

        <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
          <button onClick={onClose} style={{ background:'none', border:'1px solid #1e2030', borderRadius:10, padding:'11px 16px', fontSize:13, color:'#475569', cursor:'pointer', fontFamily:F }}>Cancel</button>
          <button onClick={submit} disabled={!name.trim() || saving}
            style={{ background:'#6366f1', color:'#fff', border:'none', borderRadius:10, padding:'11px 20px', fontSize:13, fontWeight:700, cursor:'pointer', fontFamily:F, opacity: !name.trim() || saving ? 0.5 : 1 }}>
            {saving ? 'Creating…' : 'Create project'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Spending Impact (replaces What-If Calculator) ─────────────────────────────
function SpendingImpact({ profile, expenses, topCategories }) {
  const [open, setOpen] = useState(false)
  const income = profile?.income_amount || 0
  const savings = profile?.savings_goal_monthly || 0
  const extra = profile?.extra_payment_monthly || 0

  const insights = []
  const top1 = topCategories[0]
  const top2 = topCategories[1]

  if (top1 && top1.val > 50) {
    const save20 = Math.round(top1.val * 0.2)
    insights.push({
      icon: '💡',
      text: `You spent ${fmt(top1.val)} on ${top1.name} — cutting 20% saves ~${fmt(save20)}/mo`
    })
  }

  // Subscription count
  const subTotal = topCategories.find(c => c.name === 'Subscriptions')?.val || 0
  if (subTotal > 30) {
    insights.push({
      icon: '📱',
      text: `Subscriptions total ${fmt(subTotal)}/mo — auditing unused ones is quick savings`
    })
  }

  // Fixed ratio
  if (income > 0 && expenses > 0) {
    const fixedPct = Math.round((expenses / income) * 100)
    insights.push({
      icon: '📊',
      text: `Your spending is ${fixedPct}% of take-home pay this month`
    })
  }

  if (top2 && top1) {
    const combined = top1.val + top2.val
    insights.push({
      icon: '🎯',
      text: `${top1.name} + ${top2.name} make up most of your flexible spending — ${fmt(combined)}/mo`
    })
  }

  const shown = insights.slice(0, 3)
  if (shown.length === 0) return null

  return (
    <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:18, overflow:'hidden', marginBottom:20 }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ width:'100%', background:'none', border:'none', cursor:'pointer', display:'flex', justifyContent:'space-between', alignItems:'center', padding:'16px 22px', fontFamily:F }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <span style={{ fontSize:16 }}>💡</span>
          <div style={{ textAlign:'left' }}>
            <p style={{ color:'#f1f5f9', fontSize:13, fontWeight:600, marginBottom:1 }}>Spending impact</p>
            <p style={{ color:'#475569', fontSize:11 }}>How your spending habits affect your savings</p>
          </div>
        </div>
        <span style={{ color:'#334155', fontSize:11, transform: open ? 'rotate(180deg)' : 'none', transition:'transform 0.2s', display:'inline-block' }}>▼</span>
      </button>

      {open && (
        <div style={{ padding:'0 22px 20px', borderTop:'1px solid #1e2030' }}>
          <div style={{ display:'flex', flexDirection:'column', gap:10, paddingTop:16 }}>
            {shown.map((ins, i) => (
              <div key={i} style={{ display:'flex', gap:10, padding:'12px 14px', background:'#080b0f', borderRadius:10 }}>
                <span style={{ fontSize:16, flexShrink:0 }}>{ins.icon}</span>
                <p style={{ color:'#94a3b8', fontSize:13, lineHeight:1.5 }}>{ins.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Monthly Commitments ───────────────────────────────────────────────────────
function MonthlyCommitments() {
  const [items, setItems] = useState([])
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', amount: '', frequency: 'monthly' })

  useEffect(() => {
    fetch(`${API_URL}/manual-fixed`).then(r => r.json()).then(setItems).catch(() => {})
  }, [])

  const add = async () => {
    if (!form.name || !form.amount) return
    await fetch(`${API_URL}/manual-fixed`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: form.name, amount: parseFloat(form.amount), frequency: form.frequency })
    })
    setForm({ name: '', amount: '', frequency: 'monthly' })
    setAdding(false)
    fetch(`${API_URL}/manual-fixed`).then(r => r.json()).then(setItems)
  }

  const remove = async id => {
    await fetch(`${API_URL}/manual-fixed/${id}`, { method: 'DELETE' })
    setItems(p => p.filter(i => i.id !== id))
  }

  const total = items.reduce((s, i) => s + i.amount, 0)

  return (
    <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:18, overflow:'hidden', marginBottom:20 }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ width:'100%', background:'none', border:'none', cursor:'pointer', display:'flex', justifyContent:'space-between', alignItems:'center', padding:'16px 22px', fontFamily:F }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <span style={{ fontSize:16 }}>🏠</span>
          <div style={{ textAlign:'left' }}>
            <p style={{ color:'#f1f5f9', fontSize:13, fontWeight:600, marginBottom:1 }}>
              Monthly commitments
              {total > 0 && <span style={{ color:'#475569', fontWeight:400, marginLeft:8, fontSize:12 }}>{fmt(total)}/mo</span>}
            </p>
            <p style={{ color:'#475569', fontSize:11 }}>Rent, mortgage, car payments from accounts not uploaded</p>
          </div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <button onClick={e => { e.stopPropagation(); setAdding(a => !a); setOpen(true) }}
            style={{ background:'none', border:'1px solid #1e2030', borderRadius:7, padding:'4px 10px', fontSize:11, color:'#64748b', cursor:'pointer', fontFamily:F }}>
            + Add
          </button>
          <span style={{ color:'#334155', fontSize:11, transform: open ? 'rotate(180deg)' : 'none', transition:'transform 0.2s', display:'inline-block' }}>▼</span>
        </div>
      </button>

      {open && (
        <div style={{ borderTop:'1px solid #1e2030' }}>
          {items.map(item => (
            <div key={item.id} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 22px', borderBottom:'1px solid #0a0d12' }}>
              <span style={{ color:'#94a3b8', fontSize:13 }}>{item.name}</span>
              <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                <span style={{ color:'#64748b', fontSize:13, fontFamily:'monospace' }}>
                  {fmt(item.amount)}{item.frequency === 'monthly' ? '/mo' : item.frequency === 'bimonthly' ? ' every 2mo' : item.frequency === 'quarterly' ? '/qtr' : '/yr'}
                </span>
                <button onClick={() => remove(item.id)} style={{ background:'none', border:'none', color:'#334155', cursor:'pointer', fontSize:13 }}>✕</button>
              </div>
            </div>
          ))}

          {adding && (
            <div style={{ padding:'12px 22px', display:'flex', gap:8, alignItems:'center', background:'#0a0d12' }}>
              <input placeholder="e.g. Rent" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} autoFocus
                style={{ flex:1, background:'#0f1117', border:'1px solid #1e2030', borderRadius:8, padding:'8px 12px', color:'#fff', fontSize:13, outline:'none', fontFamily:F }}/>
              <div style={{ position:'relative' }}>
                <span style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'#475569' }}>$</span>
                <input type="number" placeholder="1500" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && add()}
                  style={{ width:90, background:'#0f1117', border:'1px solid #1e2030', borderRadius:8, padding:'8px 12px 8px 24px', color:'#fff', fontSize:13, outline:'none', fontFamily:'monospace' }}/>
              </div>
              <select value={form.frequency} onChange={e => setForm({ ...form, frequency: e.target.value })}
                style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:8, padding:'8px 10px', color:'#94a3b8', fontSize:12, outline:'none', fontFamily:F, cursor:'pointer' }}>
                <option value="monthly">Monthly</option>
                <option value="bimonthly">Every 2mo</option>
                <option value="quarterly">Quarterly</option>
                <option value="annual">Annual</option>
              </select>
              <button onClick={add} disabled={!form.name || !form.amount}
                style={{ background:'#6366f1', border:'none', borderRadius:8, padding:'8px 14px', color:'#fff', fontSize:12, cursor:'pointer', fontWeight:600, fontFamily:F, opacity: !form.name || !form.amount ? 0.5 : 1 }}>Add</button>
            </div>
          )}

          {items.length === 0 && !adding && (
            <div style={{ padding:'16px 22px' }}>
              <p style={{ color:'#283244', fontSize:12 }}>None added — add rent, mortgage, or car payments from accounts not uploaded.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Spending Context Field ────────────────────────────────────────────────────
function ContextField({ fieldKey, label, color, value, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState('')
  return (
    <div style={{ background:'#080b0f', borderRadius:12, padding:'14px 16px' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
        <span style={{ fontSize:11, color:'#334155', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.6px' }}>{label}</span>
        <button onClick={() => { setEditing(true); setVal(value ? String(value) : '') }}
          style={{ background:'none', border:'none', color:'#334155', fontSize:11, cursor:'pointer', fontFamily:F }}>edit</button>
      </div>
      {editing ? (
        <div style={{ display:'flex', gap:4 }}>
          <span style={{ color:'#475569', fontSize:13 }}>$</span>
          <input autoFocus type="number" value={val}
            onChange={e => setVal(e.target.value)}
            onKeyDown={e => { if(e.key==='Enter') { onSave(fieldKey, parseFloat(val)||0); setEditing(false) } if(e.key==='Escape') setEditing(false) }}
            style={{ background:'#1e2030', border:'1px solid #3b82f6', borderRadius:6, padding:'4px 8px', color:'#fff', fontSize:14, outline:'none', fontFamily:'monospace', width:'100%' }}/>
        </div>
      ) : (
        <p style={{ fontSize:20, fontWeight:800, color: value > 0 ? color : '#283244', fontFamily:'monospace' }}>
          {value > 0 ? fmt(value) : '—'}
        </p>
      )}
    </div>
  )
}

// ── Spending Context (lightweight) ────────────────────────────────────────────
function SpendingContext({ profile, onSave }) {
  const [open, setOpen] = useState(false)
  const hasAny = (profile?.income_amount > 0) || (profile?.savings_goal_monthly > 0) || (profile?.extra_payment_monthly > 0)

  return (
    <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:18, overflow:'hidden', marginBottom:20 }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ width:'100%', background:'none', border:'none', cursor:'pointer', display:'flex', justifyContent:'space-between', alignItems:'center', padding:'16px 22px', fontFamily:F }}>
        <div style={{ textAlign:'left' }}>
          <p style={{ color:'#64748b', fontSize:12, fontWeight:600, marginBottom:1 }}>
            Spending context
            {!hasAny && <span style={{ color:'#283244', fontWeight:400, marginLeft:8, fontSize:11 }}>optional</span>}
          </p>
          <p style={{ color:'#334155', fontSize:11 }}>Helps generate smarter insights — not required</p>
        </div>
        <span style={{ color:'#283244', fontSize:11, transform: open ? 'rotate(180deg)' : 'none', transition:'transform 0.2s', display:'inline-block' }}>▼</span>
      </button>
      {open && (
        <div style={{ borderTop:'1px solid #0a0d12', padding:'16px 22px' }}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10 }}>
            <ContextField fieldKey="income_amount" label="Take-home pay" color="#10b981" value={profile?.income_amount||0} onSave={onSave}/>
            <ContextField fieldKey="savings_goal_monthly" label="What you set aside" color="#3b82f6" value={profile?.savings_goal_monthly||0} onSave={onSave}/>
            <ContextField fieldKey="extra_payment_monthly" label="Extra toward debt" color="#8b5cf6" value={profile?.extra_payment_monthly||0} onSave={onSave}/>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Goals() {
  const [projects, setProjects] = useState([])
  const [profile, setProfile] = useState({})
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [expenses, setExpenses] = useState(0)
  const [topCategories, setTopCategories] = useState([])
  const [allTransactions, setAllTransactions] = useState([])

  const load = () => {
    Promise.all([
      fetch(`${API_URL}/projects`).then(r => r.json()).catch(() => []),
      fetch(`${API_URL}/profile`).then(r => r.json()).catch(() => ({})),
      fetch(`${API_URL}/transactions`).then(r => r.json()).catch(() => []),
    ]).then(([p, prof, txs]) => {
      setProjects(Array.isArray(p) ? p : [])
      setProfile(prof || {})
      setAllTransactions(Array.isArray(txs) ? txs : [])

      const thisMonth = new Date().toISOString().slice(0, 7)
      const monthTxs = (Array.isArray(txs) ? txs : []).filter(t =>
        t.transaction_type === 'expense' && t.amount < 0 &&
        t.transaction_date?.startsWith(thisMonth) && !t.is_fixed
      )
      setExpenses(monthTxs.reduce((s, t) => s + Math.abs(t.amount), 0))

      const catMap = monthTxs.reduce((acc, t) => {
        const c = t.category || 'Other'
        acc[c] = (acc[c] || 0) + Math.abs(t.amount)
        return acc
      }, {})
      setTopCategories(
        Object.entries(catMap)
          .map(([name, val]) => ({ name, val: Math.round(val) }))
          .filter(c => !['Transfer', 'Payment', 'Other', 'Income'].includes(c.name))
          .sort((a, b) => b.val - a.val)
          .slice(0, 6)
      )
      setLoading(false)
    })
  }

  useEffect(() => {
    load()
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  const handleDelete = async id => {
    await fetch(`${API_URL}/projects/${id}`, { method: 'DELETE' })
    setProjects(p => p.filter(x => x.id !== id))
  }

  const saveProfile = async (field, value) => {
    setProfile(p => ({ ...p, [field]: value }))
    await fetch(`${API_URL}/profile`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value })
    }).catch(() => {})
  }

  return (
    <div style={{ padding:'32px 48px 64px', maxWidth:1200, margin:'0 auto', fontFamily:F, background:'#080b0f', minHeight:'100vh' }}>

      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:32 }}>
        <div>
          <h1 style={{ fontSize:26, fontWeight:800, color:'#f1f5f9', letterSpacing:'-0.5px', marginBottom:6 }}>Projects</h1>
          <p style={{ color:'#475569', fontSize:13 }}>
            Categories show <em>what</em> you spent. Projects show <em>why</em>.
          </p>
        </div>
        <button onClick={() => setShowModal(true)}
          style={{ background:'#6366f1', color:'#fff', border:'none', borderRadius:10, padding:'10px 20px', fontSize:13, fontWeight:700, cursor:'pointer', fontFamily:F }}>
          + New project
        </button>
      </div>

      {/* Projects — MAIN FOCUS */}
      {loading ? (
        <div style={{ color:'#475569', fontSize:13, marginBottom:32 }}>Loading…</div>
      ) : projects.length === 0 ? (
        <div style={{ background:'#0f1117', border:'1px solid #1e2030', borderRadius:20, padding:'56px 32px', textAlign:'center', marginBottom:24 }}>
          <div style={{ fontSize:48, marginBottom:16 }}>📁</div>
          <h2 style={{ color:'#f1f5f9', fontSize:20, fontWeight:700, marginBottom:8 }}>Track spending with purpose</h2>
          <p style={{ color:'#475569', fontSize:14, marginBottom:8, maxWidth:400, margin:'0 auto 16px' }}>
            Create a project for anything that matters — a trip, home renovation, wedding, or big purchase.
          </p>
          <p style={{ color:'#334155', fontSize:12, marginBottom:28 }}>
            Tag transactions to a project — like adding songs to a playlist.
          </p>
          <div style={{ display:'flex', gap:10, justifyContent:'center', flexWrap:'wrap', marginBottom:28 }}>
            {['✈️ Trip', '🏠 Home', '💍 Wedding', '🛍️ Big Purchase'].map(ex => (
              <span key={ex} style={{ background:'#0a0d12', border:'1px solid #1e2030', borderRadius:10, padding:'8px 16px', fontSize:13, color:'#64748b' }}>{ex}</span>
            ))}
          </div>
          <button onClick={() => setShowModal(true)}
            style={{ background:'#6366f1', color:'#fff', border:'none', borderRadius:12, padding:'12px 28px', fontSize:14, fontWeight:700, cursor:'pointer', fontFamily:F }}>
            + Create your first project
          </button>
        </div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(320px,1fr))', gap:14, marginBottom:28 }}>
          {projects.map(p => (
            <ProjectCard key={p.id} project={p} onDelete={handleDelete} allTransactions={allTransactions} />
          ))}
          <button onClick={() => setShowModal(true)}
            style={{ background:'transparent', border:'2px dashed #1e2030', borderRadius:18, padding:'32px', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:8, cursor:'pointer', color:'#334155', fontFamily:F, transition:'border-color 0.2s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor='#6366f1'}
            onMouseLeave={e => e.currentTarget.style.borderColor='#1e2030'}>
            <span style={{ fontSize:24 }}>+</span>
            <span style={{ fontSize:13 }}>New project</span>
          </button>
        </div>
      )}

      {/* Spending Impact */}
      <SpendingImpact profile={profile} expenses={expenses} topCategories={topCategories} allTransactions={allTransactions} />

      {/* Monthly Commitments */}
      <MonthlyCommitments />

      {/* Spending Context */}
      <SpendingContext profile={profile} onSave={saveProfile} />

      {showModal && <CreateProjectModal onClose={() => setShowModal(false)} onCreated={load} />}
    </div>
  )
}
