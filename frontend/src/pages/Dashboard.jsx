import React, { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, PieChart, Pie } from 'recharts'
import { API_URL } from '../lib/config'

const COLORS = ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ef4444','#64748b']
const CAT_ICONS = {
  // Core expense categories
  'Food & Dining':'🍽️','Groceries':'🛒','Transport':'🚗','Bills & Utilities':'⚡',
  'Subscriptions':'📱','Health':'💊','Shopping':'🛍️','Entertainment':'🎬',
  'Travel':'✈️','Personal Care':'💆','Pets':'🐾','Education':'📚',
  // Added in canonical 29
  'Alcohol & Liquor':'🍷','Baby & Kids':'🍼','Bank Fees':'🏦','Cash & ATM':'💵',
  'Gifts & Donations':'🎁','Government & Taxes':'🏛️','Home Improvement':'🔨',
  'Insurance':'🛡️','Professional Services':'💼',
  // Income, transfers, payments, misc
  'Salary':'💰','Other Income':'💵','Transfer':'↔️',
  'Credit Card Payment':'💳','Card Credit':'↩️','Loan Payment':'📉',
  'Refund':'↩️','Other':'📦',
  // Aliases / safety
  'Others':'📦','Payment':'💳','Uncategorized':'❓'
}
const FIXED_CATS = new Set(['bills & utilities','bills','utilities','rent','mortgage','insurance','loan payment','debt payment','credit card payment'])
const CARD_KEYWORDS = ['uber one credit','amex credit','credit applied','statement credit','annual credit','travel credit','hotel credit','reward credit','cash back','cashback','capital one credit','membership credit']

const isCardCredit = tx => tx.transaction_type === 'card_credit' || (CARD_KEYWORDS.some(k => (tx.description||'').toLowerCase().includes(k)) && tx.amount > 0)
const isFixed = tx => tx.is_fixed || FIXED_CATS.has((tx.category||'').toLowerCase())
const fmt = n => '$' + Math.round(Math.abs(n)||0).toLocaleString()
const pct = (a,b) => b > 0 ? Math.min(Math.round(a/b*100), 100) : 0
const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }

function detectMonths(txs) {
  return [...new Set(txs.map(t => t.transaction_date?.slice(0,7)).filter(Boolean))].sort()
}

function filterPeriod(txs, period, months, customStart, customEnd) {
  if (!period || period === 'all') return txs
  if (period === 'latest') { const m = months[months.length-1]; return txs.filter(t => t.transaction_date?.startsWith(m)) }
  if (period === '3m') { const last3 = months.slice(-3); return txs.filter(t => last3.some(m => t.transaction_date?.startsWith(m))) }
  if (period === 'custom' && customStart && customEnd) {
    // Compare as ISO date strings (YYYY-MM-DD sorts correctly lexically).
    // Avoids new Date() timezone shifts that dropped boundary days / whole ranges.
    return txs.filter(t => {
      const d = (t.transaction_date || '').slice(0, 10)
      return d && d >= customStart && d <= customEnd
    })
  }
  if (period?.match(/^\d{4}-\d{2}$/)) return txs.filter(t => t.transaction_date?.startsWith(period))
  return txs
}

function buildTrend(txs, months, acctFilter) {
  const rows = months.map(month => {
    const filtered = txs.filter(t => t.transaction_date?.startsWith(month) && (acctFilter === 'all' || t.bank_source === acctFilter))
    const exp = filtered.filter(t => t.transaction_type === 'expense' && t.amount < 0 && !isCardCredit(t) && t.exclusion_reason == null)
    const variable = exp.filter(t => !isFixed(t)).reduce((s,t) => s + Math.abs(t.amount), 0)
    const fixed = exp.filter(t => isFixed(t)).reduce((s,t) => s + Math.abs(t.amount), 0)
    return {
      label: new Date(month+'-02').toLocaleDateString('en-US',{month:'short',year:'2-digit'}),
      Variable: parseFloat(variable.toFixed(2)),
      Fixed: parseFloat(fixed.toFixed(2)),
      total: parseFloat((variable + fixed).toFixed(2)),
      month
    }
  })
  // Month-over-month % change of ENTIRE spending — only when the previous row
  // is the CALENDAR-CONSECUTIVE month AND both months have real spending.
  // (Avoids nonsense % across data gaps or near-empty months.)
  const MIN_TOTAL = 50
  const prevCalMonth = (ym) => {
    const [y, m] = ym.split('-').map(Number)
    const d = new Date(y, m - 2, 1)   // m is 1-based; m-2 -> previous month
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
  }
  for (let i = 0; i < rows.length; i++) {
    const prev = rows[i-1]
    const consecutive = prev && prev.month === prevCalMonth(rows[i].month)
    if (consecutive && prev.total > MIN_TOTAL && rows[i].total > MIN_TOTAL) {
      rows[i].pctChange = Math.round(((rows[i].total - prev.total) / prev.total) * 100)
    } else {
      rows[i].pctChange = null
    }
  }
  return rows
}

// Label drawn on top of each trend bar: +N% red (more), -N% green (less).
function MoMChangeLabel(props) {
  if (props.data && props.data.length > 8) return null
  const { x, y, width, index, data } = props
  const row = data && data[index]
  if (!row || row.pctChange == null) return null
  const up = row.pctChange > 0
  const flat = row.pctChange === 0
  const color = flat ? '#8a8a85' : (up ? '#ef4444' : '#10b981')
  const txt = (up ? '+' : '') + row.pctChange + '%'
  return (
    <text x={x + width/2} y={y - 6} textAnchor="middle" fontSize={12} fontWeight={700} fill={color}>
      {txt}
    </text>
  )
}

function detectPartialMonth(txs, month) {
  if (!month) return null
  const today = new Date()
  const currentMonth = today.toISOString().slice(0,7)
  if (month !== currentMonth) return null
  const monthTxs = txs.filter(t => t.transaction_date?.startsWith(month))
  if (!monthTxs.length) return null
  const dates = monthTxs.map(t => t.transaction_date).filter(Boolean).sort()
  const isPartial = dates[0] > month + '-01'
  return { isPartial, earliest: dates[0], latest: dates[dates.length-1] }
}

function DrillDown({ category, transactions, onClose }) {
  const txs = transactions.filter(t => t.category === category && t.transaction_type === 'expense' && t.amount < 0).sort((a,b) => a.amount - b.amount)
  const total = txs.reduce((s,t) => s + Math.abs(t.amount), 0)
  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.85)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,backdropFilter:'blur(4px)'}} onClick={onClose}>
      <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:24,padding:32,width:'100%',maxWidth:520,maxHeight:'78vh',overflow:'auto',boxShadow:'0 24px 64px rgba(0,0,0,0.25)'}} onClick={e=>e.stopPropagation()}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:24}}>
          <div>
            <h3 style={{color:'#1a1a1a',fontSize:20,fontWeight:700,marginBottom:4}}>{category}</h3>
            <p style={{color:'#8a8a85',fontSize:15}}>{txs.length} transactions · {fmt(total)}</p>
          </div>
          <button onClick={onClose} style={{background:'rgba(0,0,0,0.05)',border:'none',color:'#5a5a5a',width:32,height:32,borderRadius:8,cursor:'pointer',fontSize:16}}>✕</button>
        </div>
        {txs.map((t,i) => (
          <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'11px 14px',borderRadius:10,background:i%2===0?'rgba(0,0,0,0.03)':'transparent',marginBottom:2}}>
            <div>
              <p style={{color:'#1a1a1a',fontSize:15,marginBottom:2,fontWeight:500}}>{t.description}</p>
              <p style={{color:'#8a8a85',fontSize:13}}>{t.transaction_date} · {t.bank_source}</p>
            </div>
            <div style={{textAlign:'right'}}>
              <span style={{color:'#1a1a1a',fontWeight:700,fontSize:16}}>
                {t.credit_applied > 0 ? '$'+t.net_amount.toFixed(2) : '$'+Math.abs(t.amount).toFixed(2)}
              </span>
              {t.credit_applied > 0 && <div style={{fontSize:12,color:'#10b981'}}>✓ ${'{'}t.credit_applied.toFixed(2){'}'} credit applied</div>}
              {t.credit_applied > 0 && <div style={{fontSize:12,color:'#475569',textDecoration:'line-through'}}>${'{'}Math.abs(t.amount).toFixed(2){'}'}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const BarTip = ({ active, payload, label }) => !active||!payload?.length ? null : (
  <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.1)',borderRadius:10,padding:'10px 14px',boxShadow:'0 8px 24px rgba(0,0,0,0.12)'}}>
    <p style={{color:'#8a8a85',fontSize:13,marginBottom:6}}>{label}</p>
    {payload.map((p,i) => (
      <p key={i} style={{color:p.color,fontSize:14,fontWeight:700,marginBottom:2}}>
        {p.name}: {fmt(p.value)}
      </p>
    ))}
    <p style={{color:'#5a5a5a',fontSize:13,marginTop:4,borderTop:'1px solid rgba(0,0,0,0.08)',paddingTop:4}}>
      Total: {fmt(payload.reduce((s,p) => s+(p.value||0), 0))}
    </p>
  </div>
)

function SpendingExplanation({ expTotal, cardPmts, transfers, credits, acctFilter }) {
  const [open, setOpen] = useState(false)
  const cardTotal = cardPmts.reduce((s,t) => s + Math.abs(t.amount||0), 0)
  const transferTotal = transfers.reduce((s,t) => s + Math.abs(t.amount||0), 0)
  const creditTotal = credits.reduce((s,t) => s + Math.abs(t.amount||0), 0)
  return (
    <div style={{marginBottom:20}}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'9px 16px',background:'#ffffff',borderRadius:open?'12px 12px 0 0':'12px',border:'1px solid rgba(0,0,0,0.08)',cursor:'pointer'}} onClick={() => setOpen(o=>!o)}>
        <div style={{display:'flex',alignItems:'center',gap:6}}>
          {acctFilter !== 'all' && <span style={{fontSize:13,color:'#3b82f6',background:'rgba(59,130,246,0.1)',padding:'2px 8px',borderRadius:5}}>Filtered to {acctFilter}</span>}
          <span style={{color:'#8a8a85',fontSize:13}}>What's excluded? {open?'▲':'▼'}</span>
        </div>
      </div>
      {open && (
        <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderTop:'none',borderRadius:'0 0 12px 12px',padding:'14px 18px',display:'flex',flexDirection:'column',gap:8}}>
          {cardPmts.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#faf9f5',border:'1px solid rgba(0,0,0,0.06)',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{fontSize:17}}>🏦</span><div><div style={{color:'#5a5a5a',fontSize:15,fontWeight:600}}>Credit card payments excluded</div><div style={{color:'#8a8a85',fontSize:13,marginTop:1}}>Already counted at point of purchase</div></div></div>
            <span style={{color:'#8a8a85'}}>{fmt(cardTotal)}</span>
          </div>}
          {transfers.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#faf9f5',border:'1px solid rgba(0,0,0,0.06)',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{fontSize:17}}>↔️</span><div><div style={{color:'#5a5a5a',fontSize:15,fontWeight:600}}>Transfers excluded</div><div style={{color:'#8a8a85',fontSize:13,marginTop:1}}>Moving money between your own accounts</div></div></div>
            <span style={{color:'#8a8a85'}}>{fmt(transferTotal)}</span>
          </div>}
          {credits.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#faf9f5',border:'1px solid rgba(0,0,0,0.06)',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{fontSize:17}}>💳</span><div><div style={{color:'#5a5a5a',fontSize:15,fontWeight:600}}>Card credits excluded</div><div style={{color:'#8a8a85',fontSize:13,marginTop:1}}>Rewards, cashback and statement credits</div></div></div>
            <span style={{color:'#2d4a1d'}}>−{fmt(creditTotal)}</span>
          </div>}
          <p style={{color:'#8a8a85',fontSize:13,textAlign:'center',marginTop:2}}>All exclusions are automatic · <Link to="/app/upload" style={{color:'#5a5a5a',textDecoration:'none'}}>review transactions →</Link></p>
        </div>
      )}
    </div>
  )
}

function FixedSummaryCard({ totalFixedOverride, monthsCsv, account, multiMonth }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const params = new URLSearchParams()
    if (monthsCsv) params.set('months', monthsCsv)
    if (account && account !== 'all') params.set('account', account)
    const qs = params.toString() ? `?${params.toString()}` : ''
    fetch(`${API_URL}/fixed-summary${qs}`).then(r=>r.json()).then(setData).catch(()=>{})
  }, [monthsCsv, account])
  if (!data?.fixed?.items?.length) return null
  const { fixed, subscriptions } = data
  const ICONS = { netflix:'🎬',spotify:'🎵',hulu:'📺',disney:'📺',apple:'🍎',google:'▶️',youtube:'▶️',gym:'💪',fitness:'💪',geico:'🛡️',insurance:'🛡️',rent:'🏠',hoa:'🏠',mortgage:'🏠',electric:'⚡',light:'⚡',comcast:'📡',xfinity:'📡',internet:'📡',paddle:'🎮',runna:'🏃',walmart:'🛒',wmt:'🛒' }
  const getIcon = name => { const n = name.toLowerCase(); for (const [k,v] of Object.entries(ICONS)) if (n.includes(k)) return v; return '🔒' }
  return (
    <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:16,marginBottom:16}}>
      <button onClick={() => setOpen(o=>!o)} style={{width:'100%',background:'none',border:'none',cursor:'pointer',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'16px 22px',fontFamily:'DM Sans, Inter, sans-serif'}}>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <div style={{width:36,height:36,borderRadius:10,background:'rgba(0,0,0,0.04)',border:'1px solid rgba(0,0,0,0.08)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:18}}>🔒</div>
          <div style={{textAlign:'left'}}>
            <p style={{color:'#1a1a1a',fontSize:15,fontWeight:600,marginBottom:1}}>Fixed expenses</p>
            <p style={{color:'#8a8a85',fontSize:13}}>{fixed.items.length} fixed{subscriptions?.count>0?` · ${subscriptions.count} subscriptions`:''}</p>
          </div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <span style={{fontSize:17,fontWeight:700,color:'#1a1a1a'}}>{fmt(totalFixedOverride ?? data?.net_fixed_total ?? fixed.total)}/mo</span>
          <span style={{color:'#8a8a85',fontSize:13,transform:open?'rotate(180deg)':'none',transition:'transform 0.2s',display:'inline-block'}}>▼</span>
        </div>
      </button>
      {open && (
        <div style={{padding:'0 22px 18px'}}>
          {multiMonth && (
            <p style={{fontSize:12,color:'#8a8a85',paddingTop:12,marginBottom:2}}>
              Amounts are period totals (each merchant's real charges summed), not monthly.
            </p>
          )}
          <div style={{borderTop:'1px solid rgba(0,0,0,0.08)',paddingTop:14,display:'flex',flexDirection:'column',gap:6,marginBottom:12}}>
            {fixed.items.map((item,i) => (
              <div key={i} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 14px',background:'#faf9f5',borderRadius:10,border:'1px solid rgba(0,0,0,0.06)'}}>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <span style={{fontSize:16}}>{getIcon(item.merchant)}</span>
                  <p style={{color:'#1a1a1a',fontSize:14,fontWeight:500}}>{item.merchant}{multiMonth && item.occurrences>1?` · ${item.occurrences} charges`:''}{item.varies?' (varies)':''}</p>
                </div>
                <div style={{textAlign:'right'}}>
                  <p style={{color:item.credit_covered>=item.amount?'#2d4a1d':'#1a1a1a',fontSize:14,fontWeight:600}}>
                    {item.credit_covered>=item.amount?'Fully covered':fmt(item.net_amount||item.amount)}
                  </p>
                  {item.credit_covered>0&&item.credit_covered<item.amount&&<p style={{fontSize:12,color:'#10b981'}}>+{fmt(item.credit_covered)} covered by card</p>}
                  {item.credit_covered>=item.amount&&<p style={{fontSize:12,color:'#8a8a85'}}>{fmt(item.amount)} gross</p>}
                </div>
              </div>
            ))}
          </div>
          <a href="/app/transactions" style={{display:'inline-flex',alignItems:'center',gap:4,fontSize:13,color:'#6366f1',fontWeight:600,textDecoration:'none',marginBottom:12}}>
            Edit in Transactions →
          </a>
          {data?.credit_covered_total > 0 && (
            <div style={{padding:'10px 14px',background:'rgba(16,185,129,0.05)',border:'1px solid rgba(16,185,129,0.15)',borderRadius:10}}>
              <p style={{color:'#10b981',fontSize:14,fontWeight:600}}>
                ✓ {fmt(data.credit_covered_total)}/mo covered by card credits · {fmt(data.net_fixed_total)} actual cost
              </p>
              <p style={{color:'#475569',fontSize:13,marginTop:3}}>
                Fully covered items cost you nothing — focus on reducing the rest.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const F = 'DM Sans, Inter, sans-serif'
const card = { background:'#ffffff', border:'1px solid rgba(0,0,0,0.08)', borderRadius:16, padding:'22px 24px' }

export default function Dashboard() {
  const [txs, setTxs] = useState([])
  const [profile, setProfile] = useState({})
  const [loading, setLoading] = useState(true)
  const [insights, setInsights] = useState([])
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [budgetHistory, setBudgetHistory] = useState({})
  const [manualFixed, setManualFixed] = useState([])
  const [period, setPeriod] = useState('latest')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [drillCat, setDrillCat] = useState(null)
  const [acctFilter, setAcctFilter] = useState('all')
  const [catBudgets, setCatBudgets] = useState({})
  const [editBudget, setEditBudget] = useState(null)
  const [showAcctMenu, setShowAcctMenu] = useState(false)
  const [editingMonthlyBudget, setEditingMonthlyBudget] = useState(false)
  const [budgetInput, setBudgetInput] = useState('')
  const [summary, setSummary] = useState(null)
  const [expandedCats, setExpandedCats] = useState(new Set())
  const name = localStorage.getItem('user_name') || 'Your'

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/transactions`).then(r=>r.json()).catch(()=>[]),
      fetch(`${API_URL}/profile`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API_URL}/budget-history`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API_URL}/manual-fixed`).then(r=>r.json()).catch(()=>[]),
    ]).then(([t,p,bh,mf]) => {
      setTxs(Array.isArray(t)?t:[])
      setProfile(p||{})
      setBudgetHistory(bh||{})
      setManualFixed(Array.isArray(mf)?mf:[])
      if (p?.full_name) localStorage.setItem('user_name',p.full_name.split(' ')[0])
      setLoading(false)
    })
  }, [])

  const saveProfile = async (field, value) => {
    setProfile(p=>({...p,[field]:value}))
    await fetch(`${API_URL}/profile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[field]:value})}).catch(()=>{})
  }

  const months = useMemo(()=>detectMonths(txs),[txs])

  const accounts = useMemo(()=>[...new Set(txs.map(t=>t.bank_source).filter(Boolean))],[txs])

  // Measure the donut+trend (right) column so the categories list can be capped
  // to match its height exactly (level by construction, scrolls overflow).
  const rightColRef = useRef(null)
  const [rightColH, setRightColH] = useState(null)
  useEffect(() => {
    const el = rightColRef.current
    if (!el) return
    const ro = new ResizeObserver(es => { for (const e of es) setRightColH(e.contentRect.height) })
    ro.observe(el)
    setRightColH(el.getBoundingClientRect().height)
    return () => ro.disconnect()
  }, [])
  const CAT_CHROME = 78
  const catListMax = rightColH ? Math.max(160, rightColH - CAT_CHROME) : undefined

  const activePeriodMonth = useMemo(()=>{
    if (period==='latest') return months[months.length-1]
    if (period?.match(/^\d{4}-\d{2}$/)) return period
    return null
  },[period,months])

  // Resolve the active selection to a CSV of YYYY-MM, mirroring filterPeriod,
  // so the Fixed card scopes identically to the rest of the dashboard.
  const activeMonthsCsv = useMemo(()=>{
    if (period==='latest') return months[months.length-1] || ''
    if (period?.match(/^\d{4}-\d{2}$/)) return period
    if (period==='3m') return months.slice(-3).join(',')
    if (period==='all') return months.join(',')
    if (period==='custom' && customStart && customEnd) {
      return months.filter(m => m >= customStart.slice(0,7) && m <= customEnd.slice(0,7)).join(',')
    }
    return months.join(',')
  },[period,months,customStart,customEnd])
  const isMultiMonth = (activeMonthsCsv.match(/,/g) || []).length >= 1

  const periodLabel = useMemo(()=>{
    if (activePeriodMonth) return new Date(activePeriodMonth+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'})
    if (period==='3m') return 'Last 3 months'
    if (period==='all') return 'All uploaded data'
    if (period==='custom'&&customStart&&customEnd) return customStart+' → '+customEnd
    return 'Selected period'
  },[period,activePeriodMonth,customStart,customEnd])

  // Fetch insights when month changes — must be after activePeriodMonth is defined
  useEffect(() => {
    if (!activePeriodMonth) return
    setInsightsLoading(true)
    fetch(`${API_URL}/insights?month=${activePeriodMonth}`)
      .then(r => r.json())
      .then(data => { setInsights(Array.isArray(data) ? data : []); setInsightsLoading(false) })
      .catch(() => setInsightsLoading(false))
  }, [activePeriodMonth])

  const globalFiltered = useMemo(()=>filterPeriod(txs,period,months,customStart,customEnd),[txs,period,months,customStart,customEnd])
  const acctFiltered = useMemo(()=>acctFilter==='all'?globalFiltered:globalFiltered.filter(t=>t.bank_source===acctFilter),[globalFiltered,acctFilter])

  // Accounts present in the CURRENT period (derived from globalFiltered, which
  // is period-scoped but NOT account-scoped — deriving from acctFiltered would
  // be circular). Drives the account dropdown so it only lists accounts with
  // data in the selected month(s).
  const periodAccounts = useMemo(
    ()=>[...new Set(globalFiltered.map(t=>t.bank_source).filter(Boolean))],
    [globalFiltered]
  )
  // If the selected account has no data in the current period, fall back to all.
  useEffect(()=>{
    if (acctFilter !== 'all' && !periodAccounts.includes(acctFilter)) {
      setAcctFilter('all')
    }
  }, [periodAccounts, acctFilter])

  // For multi-month view, exclude partial months from AVG (< 20 days of data)
  const fullMonths = useMemo(() => {
    return months.filter(m => {
      const count = acctFiltered.filter(t => t.transaction_date?.startsWith(m)).length
      const dates = acctFiltered.filter(t => t.transaction_date?.startsWith(m)).map(t => t.transaction_date).filter(Boolean).sort()
      if (dates.length < 2) return count >= 5  // at least 5 transactions
      const firstDay = parseInt(dates[0].split('-')[2])
      const lastDay = parseInt(dates[dates.length-1].split('-')[2])
      return (lastDay - firstDay) >= 20  // at least 20 days span
    })
  }, [months, txs])

  const multiplier = period==='3m'?Math.min(3,fullMonths.length||months.length):period==='all'?Math.max(fullMonths.length||months.length,1):1
  const isMultiView = (period==='3m'||period==='all')&&multiplier>1

  // Use budget snapshot for selected month if available
  const monthlyBudget = useMemo(() => {
    if (activePeriodMonth && budgetHistory[activePeriodMonth]) {
      return budgetHistory[activePeriodMonth]
    }
    return profile?.monthly_budget || 0
  }, [activePeriodMonth, budgetHistory, profile])
  const allExp = acctFiltered.filter(t=>t.transaction_type==='expense'&&t.amount<0&&!isCardCredit(t)&&t.exclusion_reason==null)
  const totalExp = allExp.reduce((s,t)=>s+Math.abs(t.amount),0)
  const varExp = acctFiltered.filter(t=>t.transaction_type==='expense'&&t.amount<0&&!isCardCredit(t)&&t.exclusion_reason==null&&!isFixed(t))
  const fixedExp = acctFiltered.filter(t=>t.transaction_type==='expense'&&t.amount<0&&!isCardCredit(t)&&t.exclusion_reason==null&&isFixed(t))
  const totalVar = varExp.reduce((s,t)=>s+Math.abs(t.amount),0)
  const totalFixed = fixedExp.reduce((s,t)=>s+Math.abs(t.amount),0)
  const manualFixedTotal = manualFixed.reduce((s,i)=>s+i.amount,0)
  const totalFixedAll = totalFixed + manualFixedTotal

  const effectiveBudget = isMultiView?monthlyBudget*multiplier:monthlyBudget
  const leftToSpend = effectiveBudget>0?effectiveBudget-totalVar:null
  const budgetUsedPct = effectiveBudget>0?Math.min(pct(totalVar,effectiveBudget),100):0
  const isOverBudget = leftToSpend!==null&&leftToSpend<0
  const budgetBarColor = budgetUsedPct>=100?'#ef4444':budgetUsedPct>=80?'#f59e0b':'#10b981'

  const paceInfo = useMemo(()=>{
    if (!activePeriodMonth||!monthlyBudget) return null
    const today = new Date()
    if (activePeriodMonth!==today.toISOString().slice(0,7)) return null
    const daysInMonth = new Date(today.getFullYear(),today.getMonth()+1,0).getDate()
    const daysElapsed = today.getDate()
    const projectedTotal = (totalVar/daysElapsed)*daysInMonth
    const daysLeft = daysInMonth-daysElapsed
    return {projectedTotal,daysLeft,onTrack:totalVar<=(monthlyBudget/daysInMonth)*daysElapsed*1.1}
  },[activePeriodMonth,monthlyBudget,totalVar])

  const partialInfo = useMemo(()=>{
    if (!activePeriodMonth) return null
    return detectPartialMonth(acctFiltered,activePeriodMonth)
  },[txs,activePeriodMonth])

  const acctAllExp = acctFiltered.filter(t=>t.transaction_type==='expense'&&t.amount<0&&!isCardCredit(t)&&t.exclusion_reason==null)
  const acctTotal = acctAllExp.reduce((s,t)=>s+Math.abs(t.amount),0)

  const allSpendingIsFixed = acctAllExp.length > 0 && varExp.length === 0
  const varCatMap = varExp.reduce((acc,t)=>{const c=t.category||'Other';acc[c]=(acc[c]||0)+Math.abs(t.amount);return acc},{})
  const varCatEntries = Object.entries(varCatMap).map(([name,val])=>({name,val:parseFloat(val.toFixed(2))})).sort((a,b)=>b.val-a.val)
  const varTopCat = varCatEntries[0]

  useEffect(() => {
    const url = activePeriodMonth
      ? `${API_URL}/dashboard-summary?month=${activePeriodMonth}`
      : `${API_URL}/dashboard-summary`
    fetch(url).then(r=>r.json()).then(setSummary).catch(()=>setSummary(null))
  }, [activePeriodMonth])

  const comp = summary?.comparison
  const compStatus = comp?.status
  const compShow = compStatus === 'absolute' || compStatus === 'percentage'
  const compUnavailableShow = compStatus === 'unavailable' && comp?.reason !== 'not_enough_months'
  const compPrevShort = summary?.previous_month?.label?.split(' ')[0]?.slice(0,3) || 'prev'
  const compText = !comp ? null :
    compStatus === 'percentage' ? `${comp.delta_pct>0?'+':''}${Math.abs(comp.delta_pct).toFixed(0)}% vs ${compPrevShort}` :
    compStatus === 'absolute'   ? `${comp.delta_abs>0?'+':'−'}$${Math.abs(Math.round(comp.delta_abs))} vs ${compPrevShort}` :
    comp.message
  const compColor = compShow ? (comp.direction==='up'?'#ef4444':comp.direction==='down'?'#10b981':'#94a3b8') : '#64748b'
  const compBg    = compShow ? (comp.direction==='up'?'rgba(239,68,68,0.1)':comp.direction==='down'?'rgba(16,185,129,0.1)':'rgba(148,163,184,0.1)') : 'rgba(100,116,139,0.08)'
  const compArrow = compShow ? (comp.direction==='up'?'↑ ':comp.direction==='down'?'↓ ':'') : ''

  const prevMonth = months[months.indexOf(activePeriodMonth)-1]
  const prevExp = prevMonth?txs.filter(t=>t.transaction_date?.startsWith(prevMonth)&&t.transaction_type==='expense'&&t.amount<0&&!isCardCredit(t)&&t.exclusion_reason==null).reduce((s,t)=>s+Math.abs(t.amount),0):0
  const expChange = prevExp>0?((totalVar-prevExp)/prevExp*100):null
  // Hide MoM comparison for partial months — misleading when data is incomplete
  const showExpChange = expChange !== null && !partialInfo?.isPartial && allExp.length >= 10

  const credits = acctFiltered.filter(t=>t.transaction_type==='card_credit'||isCardCredit(t))

  // Detect if user only uploaded credit card statements (missing bank account)
  const isCCOnly = useMemo(() => {
    if (!txs.length) return false
    const CC_KEYWORDS = ['amex','american express','sapphire','freedom','venture',
      'quicksilver','double cash','discover','citi','synchrony','barclays']
    const sources = [...new Set(txs.map(t=>(t.bank_source||'').toLowerCase()))]
    const allCC = sources.every(s => CC_KEYWORDS.some(k => s.includes(k)))
    const hasRentMortgage = txs.some(t => {
      const d = (t.description||'').toLowerCase()
      return d.includes('rent') || d.includes('mortgage') || d.includes('car payment') ||
             d.includes('auto loan') || d.includes('hoa')
    })
    return allCC && !hasRentMortgage && sources.length > 0
  }, [txs])
  const transfers = acctFiltered.filter(t=>t.transaction_type==='transfer')
  const cardPmts = acctFiltered.filter(t=>t.transaction_type==='credit_card_payment')
  const trendData = useMemo(()=>buildTrend(txs,months,acctFilter),[txs,months,acctFilter])
  const top10 = [...allExp].sort((a,b)=>a.amount-b.amount).slice(0,10)

  if (loading) return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'100vh',background:'#fafaf5',fontFamily:F}}>
      <div style={{textAlign:'center'}}><div style={{fontSize:34,marginBottom:12}}>📊</div><p style={{color:'#8a8a85',fontSize:16}}>Loading your finances...</p></div>
    </div>
  )

  if (!txs.length) return (
    <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:'100vh',background:'#fafaf5',gap:0,fontFamily:F,padding:24}}>
      <div style={{textAlign:'center',maxWidth:480}}>
        <div style={{fontSize:50,marginBottom:20}}>📊</div>
        <h2 style={{color:'#1a1a1a',fontSize:24,fontWeight:800,marginBottom:8,letterSpacing:'-0.5px'}}>
          {name !== 'Your' ? `Welcome, ${name}!` : 'Your dashboard is ready'}
        </h2>
        {monthlyBudget > 0 ? (
          <p style={{color:'#475569',fontSize:16,marginBottom:8,lineHeight:1.7}}>
            You have a <span style={{color:'#3b82f6',fontWeight:700}}>{fmt(monthlyBudget)} budget</span> set for {new Date().toLocaleDateString('en-US',{month:'long'})}.
            <br/>Upload your bank statement to start tracking.
          </p>
        ) : (
          <p style={{color:'#475569',fontSize:16,marginBottom:8,lineHeight:1.7}}>
            Upload your first bank statement to see where your money is going.
          </p>
        )}
        <div style={{display:'flex',gap:12,justifyContent:'center',marginTop:24,flexWrap:'wrap'}}>
          <Link to="/app/upload" style={{background:'#3b82f6',color:'#fff',padding:'12px 28px',borderRadius:12,textDecoration:'none',fontWeight:700,fontSize:16}}>
            Upload statement →
          </Link>
        </div>
        {/* What you'll see preview */}
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10,marginTop:36}}>
          {[
            ['📊','Spending breakdown','See where every dollar goes by category'],
            ['🎯','Budget tracking','Know exactly how much you have left'],
            ['💡','Smart insights','Get personalized spending recommendations'],
          ].map(([icon,title,desc],i) => (
            <div key={i} style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:14,padding:'18px 16px',textAlign:'center'}}>
              <div style={{fontSize:26,marginBottom:8}}>{icon}</div>
              <p style={{color:'#1a1a1a',fontSize:14,fontWeight:600,marginBottom:4}}>{title}</p>
              <p style={{color:'#8a8a85',fontSize:13,lineHeight:1.5}}>{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <div style={{background:'#fafaf5',minHeight:'100vh',fontFamily:F,width:'100%',overflowX:'hidden'}}>
      <style>{`
        @media (max-width: 768px) {
          .kpi-grid { grid-template-columns: 1fr !important; }
          .breakdown-grid { grid-template-columns: 1fr !important; }
          .trend-grid { grid-template-columns: 1fr !important; }
          .dash-pad { padding: 16px 16px 60px !important; }
        }
        @media (max-width: 1024px) {
          .kpi-grid { grid-template-columns: 1fr 1fr !important; }
        }
      `}</style>
      <div style={{maxWidth:1280,margin:'0 auto',padding:'8px 8px 80px'}}>

        {/* HEADER — simplified */}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:28,flexWrap:'wrap',gap:12}}>
          <div>
            <p style={{fontSize:14,color:'#8a8a85',marginBottom:4}}>{greeting()}</p>
            <h1 style={{fontSize:26,fontWeight:800,color:'#1a1a1a',letterSpacing:'-0.5px',marginBottom:6}}>{name}'s spending</h1>
            <div style={{display:'flex',alignItems:'center',gap:8}}>
              <span style={{fontSize:14,color:'#5a5a5a',background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',padding:'3px 10px',borderRadius:7}}>{periodLabel}</span>
              <span style={{fontSize:13,color:'#8a8a85'}}>· {accounts.length} account{accounts.length!==1?'s':''}</span>
            </div>
          </div>

          <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
            <select value={period} onChange={e=>{setPeriod(e.target.value);setAcctFilter('all')}}
              style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.12)',borderRadius:10,padding:'8px 14px',color:'#1a1a1a',fontSize:15,outline:'none',fontFamily:F,cursor:'pointer'}}>
              <option value="latest">Latest · {months.length?new Date(months[months.length-1]+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'}):''}</option>
              {months.slice().reverse().filter(m=>m!==months[months.length-1]).map(m=>(
                <option key={m} value={m}>{new Date(m+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'})}</option>
              ))}
              {months.length>=3&&<option value="3m">Last 3 months</option>}
              {months.length>1&&<option value="all">All uploaded data</option>}
            </select>
            {periodAccounts.length>1&&(
              <div style={{position:'relative'}}>
                <button onClick={()=>setShowAcctMenu(s=>!s)} style={{background:'#ffffff',border:`1px solid ${acctFilter!=='all'?'#e85d3c':'rgba(0,0,0,0.12)'}`,borderRadius:10,padding:'8px 14px',color:acctFilter!=='all'?'#e85d3c':'#1a1a1a',fontSize:15,cursor:'pointer',fontFamily:F}}>
                  {acctFilter==='all'?'All accounts':acctFilter} ▾
                </button>
                {showAcctMenu&&(
                  <div style={{position:'absolute',top:'calc(100% + 6px)',right:0,background:'#ffffff',border:'1px solid rgba(0,0,0,0.12)',borderRadius:12,padding:6,minWidth:180,zIndex:100,boxShadow:'0 8px 32px rgba(0,0,0,0.15)'}}>
                    {['all',...periodAccounts].map(a=>(
                      <button key={a} onClick={()=>{setAcctFilter(a);setShowAcctMenu(false)}} style={{display:'block',width:'100%',textAlign:'left',padding:'9px 14px',borderRadius:8,border:'none',background:acctFilter===a?'#f4f3ec':'transparent',color:acctFilter===a?'#1a1a1a':'#5f5e5a',fontSize:15,cursor:'pointer',fontFamily:F}}>
                        {a==='all'?'All accounts':a}{acctFilter===a&&<span style={{float:'right',color:'#3b82f6'}}>✓</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>


        {/* CC-ONLY BANNER */}
        {isCCOnly && (
          <div style={{display:'flex',alignItems:'flex-start',gap:12,padding:'12px 18px',background:'rgba(59,130,246,0.05)',border:'1px solid rgba(59,130,246,0.15)',borderRadius:12,marginBottom:16}}>
            <span style={{fontSize:18,flexShrink:0}}>🏦</span>
            <div style={{flex:1}}>
              <p style={{color:'#93c5fd',fontSize:15,fontWeight:600,marginBottom:3}}>Looks like you uploaded credit card statements only</p>
              <p style={{color:'#475569',fontSize:14,lineHeight:1.6}}>Fixed expenses like rent, mortgage, and car payments are usually paid from a bank account. Upload your bank or debit statement for complete tracking.</p>
            </div>
            <Link to="/app/upload" style={{background:'rgba(59,130,246,0.1)',color:'#3b82f6',border:'1px solid rgba(59,130,246,0.2)',padding:'6px 14px',borderRadius:8,textDecoration:'none',fontWeight:600,fontSize:14,whiteSpace:'nowrap',flexShrink:0}}>Upload bank →</Link>
          </div>
        )}

        {/* ALL-FIXED EDGE CASE */}
        {allSpendingIsFixed && (
          <div style={{display:'flex',alignItems:'center',gap:10,padding:'10px 16px',background:'rgba(100,116,139,0.06)',border:'1px solid rgba(100,116,139,0.2)',borderRadius:10,marginBottom:16}}>
            <span style={{fontSize:16}}>ℹ️</span>
            <span style={{fontSize:14,color:'#8a8a85'}}>All detected spending this period is classified as fixed — no discretionary spend found. Your full budget of <strong>{fmt(monthlyBudget)}</strong> remains available.</span>
          </div>
        )}

        {/* ── ROW 1: SNAPSHOT (cream) ── */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:16,marginBottom:16}}>

          {/* Card 1: TOTAL SPENT */}
          <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:16,padding:'24px 26px'}}>
            <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginBottom:16}}>Total spent</p>
            <div style={{fontSize:42,fontWeight:800,color:'#1a1a1a',letterSpacing:'-1.5px',lineHeight:1,marginBottom:12}}>
              {fmt(totalExp)}
            </div>
            {compShow ? (
              <div style={{marginBottom:10}}>
                <span style={{fontSize:14,padding:'3px 9px',borderRadius:7,fontWeight:600,background:compBg,color:compColor,display:'inline-block'}}>
                  {compArrow}{compText}
                </span>
              </div>
            ) : (
              <div style={{height:6,marginBottom:10}}/>
            )}
            <p style={{fontSize:15,color:'#8a8a85',margin:0}}>
              {acctFilter!=='all'
                ? acctFilter + (periodLabel ? ' · ' + periodLabel : '')
                : (accounts.length>1 ? 'across ' + accounts.length + ' accounts' : '') + (periodLabel ? (accounts.length>1?' in ':'in ') + periodLabel : '')}
            </p>
          </div>

          {/* Card 2: TOP CATEGORY */}
          <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:16,padding:'24px 26px'}}>
            <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginBottom:16}}>Top category</p>
            {(() => {
              // Both computed from account+date filtered expense lists.
              const discByCat = {}
              varExp.forEach(t => {
                const c = t.category || 'Other'
                discByCat[c] = (discByCat[c] || 0) + Math.abs(t.amount)
              })
              const discEntries = Object.entries(discByCat).sort((a,b) => b[1]-a[1])
              const topDisc = discEntries.length ? { name: discEntries[0][0], amount: discEntries[0][1] } : null
              const fixedByCat = {}
              fixedExp.forEach(t => {
                const c = t.category || 'Other'
                fixedByCat[c] = (fixedByCat[c] || 0) + Math.abs(t.amount)
              })
              const fixedEntries = Object.entries(fixedByCat).sort((a,b) => b[1]-a[1])
              const topFixed = fixedEntries.length ? { name: fixedEntries[0][0], amount: fixedEntries[0][1] } : null
              if (!topDisc && !topFixed) {
                return <div style={{fontSize:16,color:'#8a8a85'}}>No spending this month</div>
              }
              return (
                <div style={{display:'flex',flexDirection:'column',gap:14}}>
                  {/* Discretionary */}
                  <div>
                    <div style={{fontSize:12,fontWeight:700,color:'#6366f1',textTransform:'uppercase',letterSpacing:'0.5px',marginBottom:4}}>Discretionary</div>
                    {topDisc ? (
                      <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between',gap:8}}>
                        <span style={{fontSize:20,fontWeight:700,color:'#1a1a1a',lineHeight:1.1}}>{topDisc.name}</span>
                        <span style={{fontSize:17,fontWeight:700,color:'#1a1a1a',flexShrink:0}}>{fmt(topDisc.amount)}</span>
                      </div>
                    ) : (
                      <div style={{fontSize:15,color:'#8a8a85'}}>None this month</div>
                    )}
                  </div>
                  {/* Fixed */}
                  <div style={{borderTop:'1px solid rgba(0,0,0,0.06)',paddingTop:12}}>
                    <div style={{fontSize:12,fontWeight:700,color:'#475569',textTransform:'uppercase',letterSpacing:'0.5px',marginBottom:4}}>Fixed</div>
                    {topFixed ? (
                      <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between',gap:8}}>
                        <span style={{fontSize:20,fontWeight:700,color:'#1a1a1a',lineHeight:1.1}}>{topFixed.name}</span>
                        <span style={{fontSize:17,fontWeight:700,color:'#1a1a1a',flexShrink:0}}>{fmt(topFixed.amount)}</span>
                      </div>
                    ) : (
                      <div style={{fontSize:15,color:'#8a8a85'}}>None this month</div>
                    )}
                  </div>
                </div>
              )
            })()}
          </div>

          {/* Card 3: LARGEST SINGLE PURCHASE */}
          <div style={{background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:16,padding:'24px 26px'}}>
            <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginBottom:16}}>Largest purchase <span style={{color:'#6366f1'}}>· discretionary</span></p>
            {(() => {
              const big = varExp.length ? [...varExp].sort((a,b)=>Math.abs(b.amount)-Math.abs(a.amount))[0] : null
              if (!big) return <div style={{fontSize:16,color:'#8a8a85'}}>No discretionary purchases this month</div>
              return (
              <>
                <div style={{fontSize:28,fontWeight:800,color:'#1a1a1a',letterSpacing:'-0.5px',lineHeight:1.1,marginBottom:12,wordBreak:'break-word'}}>
                  {big.merchant || big.description || 'Purchase'}
                </div>
                <div style={{fontSize:22,fontWeight:700,color:'#1a1a1a',marginBottom:10}}>
                  {fmt(Math.abs(big.amount))}
                </div>
                <p style={{fontSize:15,color:'#8a8a85',margin:0,display:'flex',alignItems:'center',gap:8}}>
                  {big.category && (
                    <span style={{background:'rgba(0,0,0,0.05)',padding:'2px 8px',borderRadius:6,fontSize:14}}>{big.category}</span>
                  )}
                  {big.transaction_date && new Date(big.transaction_date+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}
                </p>
              </>
              )
            })()}
          </div>

        </div>

        {/* ── ROW 2: Category (60%) | Donut + Trend (40%) ── */}
        <div className="breakdown-grid" style={{display:'grid',gridTemplateColumns:'1.6fr 1fr',gap:16,marginBottom:16,alignItems:'stretch'}}>
          <div style={{display:'flex',flexDirection:'column'}}>
        {/* SPENDING BY CATEGORY — client-side from acctAllExp (account+date filtered, ALL spending) */}
        {acctAllExp.length > 0 && (() => {
          // Group the account+date-filtered expenses by category.
          const _catMap = {}
          acctAllExp.forEach(t => {
            const name = t.category || 'Other'
            if (!_catMap[name]) _catMap[name] = { name, amount: 0, txn_count: 0, _txs: [] }
            _catMap[name].amount += Math.abs(t.amount)
            _catMap[name].txn_count += 1
            _catMap[name]._txs.push(t)
          })
          const _grand = acctAllExp.reduce((s,t)=>s+Math.abs(t.amount),0) || 1
          const cats = Object.values(_catMap).map(c => {
            const top_transactions = [...c._txs]
              .sort((a,b)=>Math.abs(b.amount)-Math.abs(a.amount))
              .slice(0,5)
              .map(t => ({
                date: t.transaction_date,
                merchant: t.merchant || t.description || 'Unknown',
                amount: Math.abs(t.amount),
              }))
            return {
              name: c.name,
              amount: c.amount,
              txn_count: c.txn_count,
              pct_of_flexible: Math.round((c.amount/_grand)*100),
              avg_amount: c.amount / (c.txn_count || 1),
              top_transactions,
              insight: null,
            }
          }).sort((a,b)=>b.amount-a.amount)
          const topAmount = cats[0]?.amount || 1
          return (
            <div style={{...card,marginBottom:16,flex:1,minHeight:0,display:'flex',flexDirection:'column'}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:18}}>
                <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px'}}>
                  Spending by category
                </p>
                <span style={{fontSize:14,color:'#8a8a85'}}>
                  {cats.length} categor{cats.length === 1 ? 'y' : 'ies'}
                </span>
              </div>

              <div style={{display:'flex',flexDirection:'column',gap:2,maxHeight:400,overflowY:'auto',paddingRight:4}}>
                {cats.map((c, i) => {
                  const barPct = Math.max(2, Math.round((c.amount / topAmount) * 100))
                  const icon = CAT_ICONS[c.name] || '📦'
                  return (
                    <React.Fragment key={c.name}>
                    <div
                      style={{
                        display:'grid',
                        gridTemplateColumns:'28px 1fr 90px 180px 20px',
                        gap:14,
                        alignItems:'center',
                        padding:'12px 8px',
                        borderRadius:10,
                        cursor:'pointer',
                        transition:'background 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = '#f4f3ec'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      onClick={() => {
                        setExpandedCats(prev => {
                          const next = new Set(prev)
                          if (next.has(c.name)) next.delete(c.name)
                          else next.add(c.name)
                          return next
                        })
                      }}
                    >
                      <span style={{fontSize:20}}>{icon}</span>
                      <span style={{fontSize:16,color:'#1a1a1a',fontWeight:500}}>{c.name}</span>
                      <span style={{fontSize:16,fontWeight:700,color:'#1a1a1a',textAlign:'right'}}>
                        {fmt(c.amount)}
                      </span>
                      <div style={{background:'rgba(0,0,0,0.06)',borderRadius:99,height:6,overflow:'hidden'}}>
                        <div style={{height:'100%',width:`${barPct}%`,background:'linear-gradient(90deg,#3b82f6,#6366f1)',transition:'width 0.5s'}}/>
                      </div>
                      <span style={{fontSize:16,color:'#8a8a85',textAlign:'center',transform:expandedCats.has(c.name)?'rotate(90deg)':'rotate(0deg)',transition:'transform 0.2s'}}>›</span>
                    </div>

                    {expandedCats.has(c.name) && (
                      <div style={{
                        padding:'12px 8px 18px 50px',
                        animation:'xspendFadeIn 150ms ease-out',
                      }}>
                        {/* Context line */}
                        <div style={{fontSize:14,color:'#8a8a85',marginBottom:6}}>
                          {c.txn_count} transaction{c.txn_count===1?'':'s'} · avg {fmt(c.avg_amount)}
                        </div>

                        {/* Interpretive insight */}
                        {c.insight?.text && (
                          <div style={{fontSize:15,color:'#5a5a5a',marginBottom:16,fontStyle:'italic'}}>
                            {c.insight.text}
                          </div>
                        )}

                        {/* Top transactions */}
                        {c.top_transactions && c.top_transactions.length > 0 && (
                          <>
                            <div style={{fontSize:12,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginBottom:8}}>
                              Top transactions
                            </div>
                            <div style={{display:'flex',flexDirection:'column',gap:4,marginBottom:14}}>
                              {c.top_transactions.map((tx, ti) => (
                                <div key={ti} style={{display:'grid',gridTemplateColumns:'70px 1fr 100px',gap:12,alignItems:'baseline',fontSize:15,padding:'4px 0'}}>
                                  <span style={{color:'#8a8a85'}}>
                                    {tx.date && new Date(tx.date+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'})}
                                  </span>
                                  <span style={{color:'#1a1a1a'}}>{tx.merchant}</span>
                                  <span style={{color:'#1a1a1a',textAlign:'right',fontWeight:600}}>
                                    {fmt(tx.amount)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {/* View all link */}
                        <a
                          href={`/transactions?category=${encodeURIComponent(c.name)}`}
                          style={{fontSize:14,color:'#e85d3c',textDecoration:'none',display:'inline-block',marginRight:18}}
                          onMouseEnter={e => e.currentTarget.style.textDecoration='underline'}
                          onMouseLeave={e => e.currentTarget.style.textDecoration='none'}
                        >
                          View all {c.name} transactions →
                        </a>

                        {/* Soft limit placeholder */}
                        <button
                          style={{
                            background:'transparent',
                            border:'1px dashed rgba(0,0,0,0.2)',
                            borderRadius:6,
                            padding:'4px 10px',
                            fontSize:14,
                            color:'#8a8a85',
                            cursor:'pointer',
                            fontFamily:'inherit',
                          }}
                          onClick={(e) => {
                            e.stopPropagation()
                            alert('Soft limits coming in Phase 4. We\'ll let you set a gentle target without enforcement.')
                          }}
                        >
                          + Set a soft limit
                        </button>
                      </div>
                    )}
                  </React.Fragment>
                  )
                })}
              </div>
            </div>
          )
        })()}

          </div>
          <div ref={rightColRef} style={{display:'flex',flexDirection:'column',gap:3}}>
        {/* DISCRETIONARY vs FIXED — donut (cream) */}
        {(() => {
          const cm = summary?.current_month || {}
          const total = totalExp || 0
          const disc = varExp.reduce((s,t)=>s+Math.abs(t.amount),0)
          const fix = fixedExp.reduce((s,t)=>s+Math.abs(t.amount),0)
          if (total <= 0) return null
          const dPct = Math.round((disc / total) * 100)
          const fPct = 100 - dPct
          const txnCount = allExp.length
          const donutSlices = [
            { name: 'Discretionary', value: disc, fill: '#6366f1' },
            { name: 'Fixed',         value: fix,  fill: '#475569' },
          ]
          return (
            <div style={{...card, marginBottom:16}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:20}}>
                <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px'}}>
                  Discretionary vs Fixed
                </p>
                <span style={{fontSize:14,color:'#8a8a85'}}>{periodLabel}</span>
              </div>

              <div style={{display:'flex',alignItems:'center',gap:32,flexWrap:'wrap'}}>
                {/* Donut */}
                <div style={{position:'relative',width:180,height:180,flexShrink:0}}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={donutSlices}
                        dataKey="value"
                        innerRadius={62}
                        outerRadius={86}
                        paddingAngle={2}
                        startAngle={90}
                        endAngle={-270}
                        stroke="none"
                      >
                        {donutSlices.map((s,i) => <Cell key={i} fill={s.fill} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{position:'absolute',inset:0,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',pointerEvents:'none'}}>
                    <span style={{fontSize:30,fontWeight:800,color:'#1a1a1a',letterSpacing:'-1px',lineHeight:1}}>{txnCount}</span>
                    <span style={{fontSize:12,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginTop:4}}>Transactions</span>
                  </div>
                </div>

                {/* Legend */}
                <div style={{flex:1,minWidth:180,display:'flex',flexDirection:'column',gap:18}}>
                  <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12}}>
                    <div style={{display:'flex',alignItems:'center',gap:10}}>
                      <span style={{width:10,height:10,borderRadius:3,background:'#6366f1',flexShrink:0}}/>
                      <div>
                        <div style={{fontSize:16,fontWeight:600,color:'#1a1a1a'}}>Discretionary</div>
                        <div style={{fontSize:22,fontWeight:700,color:'#1a1a1a',marginTop:2}}>{fmt(disc)}</div>
                      </div>
                    </div>
                    <span style={{fontSize:16,fontWeight:600,color:'#8a8a85'}}>{dPct}%</span>
                  </div>
                  <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12}}>
                    <div style={{display:'flex',alignItems:'center',gap:10}}>
                      <span style={{width:10,height:10,borderRadius:3,background:'#475569',flexShrink:0}}/>
                      <div>
                        <div style={{fontSize:16,fontWeight:600,color:'#1a1a1a'}}>Fixed</div>
                        <div style={{fontSize:22,fontWeight:700,color:'#1a1a1a',marginTop:2}}>{fmt(fix)}</div>
                      </div>
                    </div>
                    <span style={{fontSize:16,fontWeight:600,color:'#8a8a85'}}>{fPct}%</span>
                  </div>
                </div>
              </div>

            </div>
          )
        })()}


          {/* Trend — line chart */}
          <div style={{...card,display:'flex',flexDirection:'column',flex:1}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
              <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px'}}>Monthly trend</p>
              {compShow&&(
                <span style={{fontSize:14,fontWeight:700,color:compColor,background:compBg,padding:'4px 10px',borderRadius:8,border:`1px solid ${compShow?(comp.direction==='up'?'rgba(239,68,68,0.15)':comp.direction==='down'?'rgba(16,185,129,0.15)':'rgba(148,163,184,0.15)'):'rgba(100,116,139,0.15)'}`}}>
                  {compArrow}{compText}
                </span>
              )}
            </div>
            {summary?.trend_chart?.show && trendData.length>=2?(
              <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0}}>
                <div style={{display:'flex',gap:16,marginBottom:12}}>
                  <div style={{display:'flex',alignItems:'center',gap:6}}><div style={{width:10,height:10,borderRadius:2,background:'#475569'}}/><span style={{fontSize:13,color:'#8a8a85'}}>Fixed</span></div>
                  <div style={{display:'flex',alignItems:'center',gap:6}}><div style={{width:10,height:10,borderRadius:2,background:'#6366f1'}}/><span style={{fontSize:13,color:'#8a8a85'}}>Discretionary</span></div>
                </div>
                <ResponsiveContainer width="100%" height="100%" minHeight={140}>
                  <BarChart data={trendData} margin={{top:10,right:12,left:0,bottom:0}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" vertical={false}/>
                    <XAxis dataKey="label" tick={{fill:'#8a8a85',fontSize:14}} axisLine={false} tickLine={false}/>
                    <YAxis tick={{fill:'#8a8a85',fontSize:14,fontWeight:600}} axisLine={false} tickLine={false} tickFormatter={v=>'$'+Math.round(v/1000)+'k'} width={45}/>
                    <Tooltip content={<BarTip/>}/>
                    <Bar dataKey="Variable" name="Discretionary" stackId="a" fill="#6366f1" radius={[0,0,0,0]}/>
                    <Bar dataKey="Fixed" name="Fixed" stackId="a" fill="#475569" radius={[4,4,0,0]} label={<MoMChangeLabel data={trendData}/>}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ):(
              <div style={{height:160,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:10}}>
                <p style={{color:'#8a8a85',fontSize:15}}>Upload another month to see trends</p>
                <Link to="/app/upload" style={{color:'#e85d3c',fontSize:15,textDecoration:'none',fontWeight:600}}>Upload →</Link>
              </div>
            )}
          </div>
          </div>
        </div>

        {/* FIXED EXPENSES */}
        <FixedSummaryCard totalFixedOverride={totalFixed} monthsCsv={activeMonthsCsv} account={acctFilter} multiMonth={isMultiMonth}/>

        {/* ── ROW 3: INSIGHTS (full width) ── */}
          {/* Insights — beside trend */}
          <div style={{...card,display:'flex',flexDirection:'column',minHeight:320}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
              <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px'}}>Insights</p>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:10,overflowY:'auto',maxHeight:320,paddingRight:4}}>
              {insightsLoading && (
                <div style={{textAlign:'center',padding:'20px 0',color:'#8a8a85',fontSize:14}}>Analyzing your spending…</div>
              )}
              {!insightsLoading && insights.length === 0 && allExp.length === 0 && (
                <div style={{textAlign:'center',padding:'20px 0'}}>
                  <p style={{color:'#8a8a85',fontSize:14,marginBottom:8}}>Upload a statement to get started</p>
                  <Link to="/app/upload" style={{fontSize:13,color:'#e85d3c',textDecoration:'none',fontWeight:600}}>Upload now →</Link>
                </div>
              )}
              {!insightsLoading && insights.length === 0 && allExp.length > 0 && (
                <div style={{textAlign:'center',padding:'24px 12px'}}>
                  <p style={{color:'#8a8a85',fontSize:14,lineHeight:1.5}}>Nothing notable this period — your spending looks steady.</p>
                </div>
              )}
              {!insightsLoading && insights.map((ins,i) => (
                <div key={i} style={{display:'flex',gap:12,padding:'12px 14px',background:'#faf9f5',borderRadius:12,borderLeft:`3px solid ${ins.color}`,cursor:ins.action_filter?'pointer':'default'}}
                  onClick={() => ins.action_filter && window.location.assign('/app/transactions?cat='+ins.action_filter)}>
                  <span style={{fontSize:18,flexShrink:0}}>{ins.icon}</span>
                  <div style={{flex:1}}>
                    <p style={{fontSize:14,fontWeight:700,color:'#1a1a1a',marginBottom:3,lineHeight:1.3}}>{ins.title}</p>
                    <p style={{fontSize:13,color:'#5a5a5a',lineHeight:1.5}}>{ins.body}</p>
                    {ins.action && <p style={{fontSize:12,color:ins.color,marginTop:4,fontWeight:600}}>{ins.action} →</p>}
                  </div>
                </div>
              ))}
              {!insightsLoading && (summary?.months_available || 0) <= 1 && insights.length > 0 && (
                <div style={{padding:'10px 14px',background:'rgba(59,130,246,0.05)',border:'1px solid rgba(59,130,246,0.12)',borderRadius:10,textAlign:'center'}}>
                  <p style={{fontSize:13,color:'#475569',marginBottom:4}}>🔓 Upload 2-3 months to unlock trend insights</p>
                  <Link to="/app/upload" style={{fontSize:13,color:'#3b82f6',textDecoration:'none',fontWeight:600}}>Upload another month →</Link>
                </div>
              )}
            </div>
          </div>

        {/* ── MONEY IN & OUT ── */}
        {(() => {
          const cardCredits = acctFiltered.filter(t => t.transaction_type === 'card_credit')
          const transfers = acctFiltered.filter(t => t.transaction_type === 'transfer')
          const ccPayments = acctFiltered.filter(t => t.transaction_type === 'credit_card_payment')
          const refunds = acctFiltered.filter(t => t.transaction_type === 'refund')
          const creditTotal = cardCredits.reduce((s,t) => s + Math.abs(t.amount), 0)
          const transferTotal = transfers.reduce((s,t) => s + Math.abs(t.amount), 0)
          const ccTotal = ccPayments.reduce((s,t) => s + Math.abs(t.amount), 0)
          const refundTotal = refunds.reduce((s,t) => s + Math.abs(t.amount), 0)

          const items = [
            { icon:'💳', label:'Credits received', amount:creditTotal, color:'#10b981', show: creditTotal > 0,
              sub: cardCredits.length + ' benefit credit' + (cardCredits.length !== 1 ? 's' : '') },
            { icon:'↔️', label:'Transfers out', amount:transferTotal, color:'#8b5cf6', show: transferTotal > 0,
              sub: transfers.length + ' transfer' + (transfers.length !== 1 ? 's' : '') },
            { icon:'🏦', label:'Card payments', amount:ccTotal, color:'#3b82f6', show: ccTotal > 0,
              sub: ccPayments.length + ' payment' + (ccPayments.length !== 1 ? 's' : '') },
            { icon:'🔄', label:'Refunds', amount:refundTotal, color:'#f59e0b', show: refundTotal > 0,
              sub: refunds.length + ' refund' + (refunds.length !== 1 ? 's' : '') },
          ].filter(i => i.show)

          if (items.length === 0) return null
          return (
            <div style={{display:'flex', gap:12, marginBottom:14, flexWrap:'wrap'}}>
              {items.map((item, i) => (
                <div key={i} style={{...card, flex:1, minWidth:140, padding:'14px 18px', display:'flex', alignItems:'center', gap:12}}>
                  <span style={{fontSize:20}}>{item.icon}</span>
                  <div>
                    <p style={{fontSize:12, color:'#475569', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.8px', marginBottom:3}}>{item.label}</p>
                    <p style={{fontSize:18, fontWeight:800, color:item.color, fontFamily:'monospace', marginBottom:2}}>{fmt(item.amount)}</p>
                    {item.sub && <p style={{fontSize:12, color:'#334155', lineHeight:1.4}}>{item.sub}</p>}
                  </div>
                </div>
              ))}
            </div>
          )
        })()}

                {/* TOP TRANSACTIONS */}
        <div style={{...card,marginBottom:14}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:18}}>
            <div>
              <p style={{fontSize:13,fontWeight:700,color:'#8a8a85',textTransform:'uppercase',letterSpacing:'1px',marginBottom:3}}>Top transactions</p>
              <p style={{fontSize:14,color:'#8a8a85'}}>{periodLabel}</p>
            </div>
            <Link to="/app/transactions" style={{fontSize:14,color:'#e85d3c',textDecoration:'none',fontWeight:600}}>View all →</Link>
          </div>
          {top10.length>0?(
            <table style={{width:'100%',borderCollapse:'collapse'}}>
              <thead>
                <tr>
                  {['Date','Description','Category','Amount'].map((h,i)=>(
                    <th key={h} style={{padding:'8px 14px',color:'#8a8a85',fontSize:12,fontWeight:700,textTransform:'uppercase',letterSpacing:'1px',textAlign:i===3?'right':'left',borderBottom:'1px solid rgba(0,0,0,0.08)'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {top10.map((t,i)=>(
                  <tr key={i} style={{borderBottom:'1px solid rgba(0,0,0,0.05)',transition:'background 0.1s'}}
                    onMouseEnter={e=>e.currentTarget.style.background='rgba(0,0,0,0.02)'}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <td style={{padding:'11px 14px',color:'#8a8a85',fontSize:14}}>{t.transaction_date}</td>
                    <td style={{padding:'11px 14px',color:'#1a1a1a',fontSize:15,fontWeight:500,maxWidth:260}}>
                      <div style={{display:'flex',alignItems:'center',gap:6}}>
                        {t.description}
                        {t.is_fixed&&<span style={{fontSize:11,color:'#8a8a85',background:'rgba(0,0,0,0.05)',padding:'1px 5px',borderRadius:3,fontWeight:600,flexShrink:0}}>FIXED</span>}
                      </div>
                    </td>
                    <td style={{padding:'11px 14px'}}>
                      <span style={{background:'rgba(0,0,0,0.05)',color:'#5a5a5a',fontSize:13,padding:'3px 9px',borderRadius:6,cursor:'pointer'}} onClick={()=>setDrillCat(t.category)}>{t.category}</span>
                    </td>
                    <td style={{padding:'11px 14px',textAlign:'right'}}>
                      <div style={{fontWeight:800,color:'#1a1a1a',fontSize:16}}>
                        {t.credit_applied > 0 ? '-$'+t.net_amount.toFixed(2) : '$'+Math.abs(t.amount).toFixed(2)}
                      </div>
                      {t.credit_applied > 0 && <div style={{fontSize:12,color:'#8a8a85',textDecoration:'line-through'}}>${Math.abs(t.amount).toFixed(2)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ):(
            <div style={{textAlign:'center',padding:'40px 0',color:'#8a8a85',fontSize:15}}>No expense transactions in this period</div>
          )}
        </div>

        {/* GOALS LINK */}
        <div style={{padding:'18px 24px',background:'#ffffff',border:'1px solid rgba(0,0,0,0.08)',borderRadius:16,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
          <div>
            <p style={{fontSize:15,fontWeight:700,color:'#1a1a1a',marginBottom:3}}>Projects & custom tracking</p>
          </div>
          <Link to="/app/projects" style={{background:'#e85d3c',color:'#fff',border:'1px solid #e85d3c',padding:'9px 18px',borderRadius:10,textDecoration:'none',fontWeight:700,fontSize:15,whiteSpace:'nowrap'}}>Set up projects →</Link>
        </div>

      </div>
      {drillCat&&<DrillDown category={drillCat} transactions={acctFiltered} onClose={()=>setDrillCat(null)}/>}
    </div>
  )
}
