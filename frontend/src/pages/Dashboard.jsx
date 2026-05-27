import React, { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, PieChart, Pie } from 'recharts'
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
    const s = new Date(customStart), e = new Date(customEnd)
    return txs.filter(t => { if(!t.transaction_date) return false; const d = new Date(t.transaction_date); return d >= s && d <= e })
  }
  if (period?.match(/^\d{4}-\d{2}$/)) return txs.filter(t => t.transaction_date?.startsWith(period))
  return txs
}

function buildTrend(txs, months, acctFilter) {
  return months.map(month => {
    const filtered = txs.filter(t => t.transaction_date?.startsWith(month) && (acctFilter === 'all' || t.bank_source === acctFilter))
    const exp = filtered.filter(t => t.transaction_type === 'expense' && t.amount < 0 && !isCardCredit(t) && t.exclusion_reason == null)
    const variable = exp.filter(t => !isFixed(t)).reduce((s,t) => s + Math.abs(t.amount), 0)
    const fixed = exp.filter(t => isFixed(t)).reduce((s,t) => s + Math.abs(t.amount), 0)
    return {
      label: new Date(month+'-02').toLocaleDateString('en-US',{month:'short',year:'2-digit'}),
      Variable: parseFloat(variable.toFixed(2)),
      Fixed: parseFloat(fixed.toFixed(2)),
      month
    }
  })
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
      <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:24,padding:32,width:'100%',maxWidth:520,maxHeight:'78vh',overflow:'auto',boxShadow:'0 24px 64px rgba(0,0,0,0.6)'}} onClick={e=>e.stopPropagation()}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:24}}>
          <div>
            <h3 style={{color:'#f1f5f9',fontSize:18,fontWeight:700,marginBottom:4}}>{category}</h3>
            <p style={{color:'#475569',fontSize:13}}>{txs.length} transactions · {fmt(total)}</p>
          </div>
          <button onClick={onClose} style={{background:'#1e2030',border:'none',color:'#64748b',width:32,height:32,borderRadius:8,cursor:'pointer',fontSize:14}}>✕</button>
        </div>
        {txs.map((t,i) => (
          <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'11px 14px',borderRadius:10,background:i%2===0?'#151720':'transparent',marginBottom:2}}>
            <div>
              <p style={{color:'#e2e8f0',fontSize:13,marginBottom:2,fontWeight:500}}>{t.description}</p>
              <p style={{color:'#334155',fontSize:11}}>{t.transaction_date} · {t.bank_source}</p>
            </div>
            <div style={{textAlign:'right'}}>
              <span style={{color:'#ef4444',fontWeight:700,fontSize:14,fontFamily:'monospace'}}>
                {t.credit_applied > 0 ? '$'+t.net_amount.toFixed(2) : '$'+Math.abs(t.amount).toFixed(2)}
              </span>
              {t.credit_applied > 0 && <div style={{fontSize:10,color:'#10b981'}}>✓ ${'{'}t.credit_applied.toFixed(2){'}'} credit applied</div>}
              {t.credit_applied > 0 && <div style={{fontSize:10,color:'#475569',textDecoration:'line-through'}}>${'{'}Math.abs(t.amount).toFixed(2){'}'}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const BarTip = ({ active, payload, label }) => !active||!payload?.length ? null : (
  <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:10,padding:'10px 14px'}}>
    <p style={{color:'#475569',fontSize:11,marginBottom:6}}>{label}</p>
    {payload.map((p,i) => (
      <p key={i} style={{color:p.color,fontSize:12,fontWeight:700,marginBottom:2}}>
        {p.name}: {fmt(p.value)}
      </p>
    ))}
    <p style={{color:'#94a3b8',fontSize:11,marginTop:4,borderTop:'1px solid #1e2030',paddingTop:4}}>
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
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'9px 16px',background:'#0a0d12',borderRadius:open?'12px 12px 0 0':'12px',border:'1px solid #1e2030',cursor:'pointer'}} onClick={() => setOpen(o=>!o)}>
        <span style={{fontSize:12,color:'#475569'}}>Showing real spending only · <span style={{color:'#334155',fontSize:11}}>transfers & card payments excluded</span></span>
        <div style={{display:'flex',alignItems:'center',gap:6}}>
          {acctFilter !== 'all' && <span style={{fontSize:11,color:'#3b82f6',background:'rgba(59,130,246,0.1)',padding:'2px 8px',borderRadius:5}}>Filtered to {acctFilter}</span>}
          <span style={{color:'#334155',fontSize:11}}>What's excluded? {open?'▲':'▼'}</span>
        </div>
      </div>
      {open && (
        <div style={{background:'#0a0d12',border:'1px solid #1e2030',borderTop:'none',borderRadius:'0 0 12px 12px',padding:'14px 18px',display:'flex',flexDirection:'column',gap:8}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'rgba(16,185,129,0.05)',border:'1px solid rgba(16,185,129,0.12)',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span>✓</span><div><div style={{color:'#e2e8f0',fontSize:13,fontWeight:600}}>Real spending counted</div><div style={{color:'#475569',fontSize:11,marginTop:1}}>All purchases, groceries, dining, shopping, transport</div></div></div>
            <span style={{color:'#10b981',fontWeight:700,fontFamily:'monospace'}}>{fmt(expTotal)}</span>
          </div>
          {cardPmts.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#0f1117',border:'1px solid #1e2030',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{color:'#475569'}}>✗</span><div><div style={{color:'#64748b',fontSize:13,fontWeight:600}}>Credit card payments excluded</div><div style={{color:'#334155',fontSize:11,marginTop:1}}>Already counted at point of purchase</div></div></div>
            <span style={{color:'#475569',fontFamily:'monospace'}}>{fmt(cardTotal)}</span>
          </div>}
          {transfers.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#0f1117',border:'1px solid #1e2030',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{color:'#475569'}}>✗</span><div><div style={{color:'#64748b',fontSize:13,fontWeight:600}}>Transfers excluded</div><div style={{color:'#334155',fontSize:11,marginTop:1}}>Moving money between your own accounts</div></div></div>
            <span style={{color:'#475569',fontFamily:'monospace'}}>{fmt(transferTotal)}</span>
          </div>}
          {credits.length > 0 && <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',background:'#0f1117',border:'1px solid #1e2030',borderRadius:10}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{color:'#475569'}}>✗</span><div><div style={{color:'#64748b',fontSize:13,fontWeight:600}}>Card credits excluded</div><div style={{color:'#334155',fontSize:11,marginTop:1}}>Rewards, cashback and statement credits</div></div></div>
            <span style={{color:'#10b981',fontFamily:'monospace'}}>−{fmt(creditTotal)}</span>
          </div>}
          <p style={{color:'#283244',fontSize:11,textAlign:'center',marginTop:2}}>All exclusions are automatic · <Link to="/app/upload" style={{color:'#334155',textDecoration:'none'}}>review transactions →</Link></p>
        </div>
      )}
    </div>
  )
}

function FixedSummaryCard() {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { fetch(`${API_URL}/fixed-summary`).then(r=>r.json()).then(setData).catch(()=>{}) }, [])
  if (!data?.fixed?.items?.length) return null
  const { fixed, subscriptions } = data
  const ICONS = { netflix:'🎬',spotify:'🎵',hulu:'📺',disney:'📺',apple:'🍎',google:'▶️',youtube:'▶️',gym:'💪',fitness:'💪',geico:'🛡️',insurance:'🛡️',rent:'🏠',hoa:'🏠',mortgage:'🏠',electric:'⚡',light:'⚡',comcast:'📡',xfinity:'📡',internet:'📡',paddle:'🎮',runna:'🏃',walmart:'🛒',wmt:'🛒' }
  const getIcon = name => { const n = name.toLowerCase(); for (const [k,v] of Object.entries(ICONS)) if (n.includes(k)) return v; return '🔒' }
  return (
    <div style={{background:'#0a0d12',border:'1px solid #1e2030',borderRadius:16,marginBottom:16}}>
      <button onClick={() => setOpen(o=>!o)} style={{width:'100%',background:'none',border:'none',cursor:'pointer',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'16px 22px',fontFamily:'DM Sans, Inter, sans-serif'}}>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <div style={{width:36,height:36,borderRadius:10,background:'rgba(100,116,139,0.1)',border:'1px solid #1e2030',display:'flex',alignItems:'center',justifyContent:'center',fontSize:16}}>🔒</div>
          <div style={{textAlign:'left'}}>
            <p style={{color:'#94a3b8',fontSize:13,fontWeight:600,marginBottom:1}}>Recurring expenses</p>
            <p style={{color:'#475569',fontSize:11}}>Not part of your budget · {fixed.items.length} recurring{subscriptions?.count>0?` · ${subscriptions.count} subscriptions`:''}</p>
          </div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <span style={{fontSize:15,fontWeight:700,color:'#64748b',fontFamily:'monospace'}}>{fmt(data?.net_fixed_total ?? fixed.total)}/mo</span>
          <span style={{color:'#334155',fontSize:11,transform:open?'rotate(180deg)':'none',transition:'transform 0.2s',display:'inline-block'}}>▼</span>
        </div>
      </button>
      {open && (
        <div style={{padding:'0 22px 18px'}}>
          <div style={{borderTop:'1px solid #1e2030',paddingTop:14,display:'flex',flexDirection:'column',gap:6,marginBottom:12}}>
            {fixed.items.map((item,i) => (
              <div key={i} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 14px',background:'#0f1117',borderRadius:10,border:'1px solid #1e2030'}}>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <span style={{fontSize:14}}>{getIcon(item.merchant)}</span>
                  <p style={{color:'#e2e8f0',fontSize:12,fontWeight:500}}>{item.merchant}{item.varies?' (varies)':''}</p>
                </div>
                <div style={{textAlign:'right'}}>
                  <p style={{color:item.credit_covered>=item.amount?'#10b981':'#64748b',fontSize:12,fontFamily:'monospace',fontWeight:600}}>
                    {item.credit_covered>=item.amount?'Fully covered':fmt(item.net_amount||item.amount)}
                  </p>
                  {item.credit_covered>0&&item.credit_covered<item.amount&&<p style={{fontSize:10,color:'#10b981'}}>+{fmt(item.credit_covered)} covered by card</p>}
                  {item.credit_covered>=item.amount&&<p style={{fontSize:10,color:'#475569'}}>{fmt(item.amount)} gross</p>}
                </div>
              </div>
            ))}
          </div>
          {data?.credit_covered_total > 0 && (
            <div style={{padding:'10px 14px',background:'rgba(16,185,129,0.05)',border:'1px solid rgba(16,185,129,0.15)',borderRadius:10}}>
              <p style={{color:'#10b981',fontSize:12,fontWeight:600}}>
                ✓ {fmt(data.credit_covered_total)}/mo covered by card credits · {fmt(data.net_fixed_total)} actual cost
              </p>
              <p style={{color:'#475569',fontSize:11,marginTop:3}}>
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
const card = { background:'#0f1117', border:'1px solid #1e2030', borderRadius:18, padding:'22px 24px' }

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

  const activePeriodMonth = useMemo(()=>{
    if (period==='latest') return months[months.length-1]
    if (period?.match(/^\d{4}-\d{2}$/)) return period
    return null
  },[period,months])

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
  const EXCLUDED_CATS = new Set(['Transfer','Payment','Credit Card Payment','Loan Payment','Income'])
  const catMap = acctAllExp.filter(t=>!EXCLUDED_CATS.has(t.category)).reduce((acc,t)=>{const c=t.category||'Other';acc[c]=(acc[c]||0)+Math.abs(t.amount);return acc},{})
  const catEntries = Object.entries(catMap).map(([name,val])=>({name,val:parseFloat(val.toFixed(2))})).sort((a,b)=>b.val-a.val)
  const top5 = catEntries.slice(0,5)
  const othersVal = catEntries.slice(5).reduce((s,c)=>s+c.val,0)
  const donutData = [...top5,...(othersVal>0?[{name:'Others',val:parseFloat(othersVal.toFixed(2))}]:[])].map((c,i)=>({...c,fill:COLORS[i%COLORS.length]}))

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
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'100vh',background:'#080b0f',fontFamily:F}}>
      <div style={{textAlign:'center'}}><div style={{fontSize:32,marginBottom:12}}>📊</div><p style={{color:'#475569',fontSize:14}}>Loading your finances...</p></div>
    </div>
  )

  if (!txs.length) return (
    <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:'100vh',background:'#080b0f',gap:0,fontFamily:F,padding:24}}>
      <div style={{textAlign:'center',maxWidth:480}}>
        <div style={{fontSize:48,marginBottom:20}}>📊</div>
        <h2 style={{color:'#f1f5f9',fontSize:22,fontWeight:800,marginBottom:8,letterSpacing:'-0.5px'}}>
          {name !== 'Your' ? `Welcome, ${name}!` : 'Your dashboard is ready'}
        </h2>
        {monthlyBudget > 0 ? (
          <p style={{color:'#475569',fontSize:14,marginBottom:8,lineHeight:1.7}}>
            You have a <span style={{color:'#3b82f6',fontWeight:700}}>{fmt(monthlyBudget)} budget</span> set for {new Date().toLocaleDateString('en-US',{month:'long'})}.
            <br/>Upload your bank statement to start tracking.
          </p>
        ) : (
          <p style={{color:'#475569',fontSize:14,marginBottom:8,lineHeight:1.7}}>
            Upload your first bank statement to see where your money is going.
          </p>
        )}
        <div style={{display:'flex',gap:12,justifyContent:'center',marginTop:24,flexWrap:'wrap'}}>
          <Link to="/app/upload" style={{background:'#3b82f6',color:'#fff',padding:'12px 28px',borderRadius:12,textDecoration:'none',fontWeight:700,fontSize:14}}>
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
            <div key={i} style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:14,padding:'18px 16px',textAlign:'center'}}>
              <div style={{fontSize:24,marginBottom:8}}>{icon}</div>
              <p style={{color:'#e2e8f0',fontSize:12,fontWeight:600,marginBottom:4}}>{title}</p>
              <p style={{color:'#334155',fontSize:11,lineHeight:1.5}}>{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <div style={{background:'#080b0f',minHeight:'100vh',fontFamily:F,maxWidth:'100vw',overflowX:'hidden'}}>
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
      <div style={{maxWidth:1200,margin:'0 auto',padding:'28px 40px 80px'}}>

        {/* HEADER — simplified */}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:28,flexWrap:'wrap',gap:12}}>
          <div>
            <p style={{fontSize:12,color:'#334155',marginBottom:4}}>{greeting()}</p>
            <h1 style={{fontSize:24,fontWeight:800,color:'#f1f5f9',letterSpacing:'-0.5px',marginBottom:6}}>{name}'s spending</h1>
            <div style={{display:'flex',alignItems:'center',gap:8}}>
              <span style={{fontSize:12,color:'#94a3b8',background:'#0f1117',border:'1px solid #1e2030',padding:'3px 10px',borderRadius:7}}>{periodLabel}</span>
              <span style={{fontSize:11,color:'#334155'}}>· {accounts.length} account{accounts.length!==1?'s':''}</span>
            </div>
          </div>

          <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
            <select value={period} onChange={e=>{setPeriod(e.target.value);setAcctFilter('all')}}
              style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:10,padding:'8px 14px',color:'#e2e8f0',fontSize:13,outline:'none',fontFamily:F,cursor:'pointer'}}>
              <option value="latest">Latest · {months.length?new Date(months[months.length-1]+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'}):''}</option>
              {months.slice().reverse().filter(m=>m!==months[months.length-1]).map(m=>(
                <option key={m} value={m}>{new Date(m+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'})}</option>
              ))}
              {months.length>=3&&<option value="3m">Last 3 months</option>}
              {months.length>1&&<option value="all">All uploaded data</option>}
              <option value="custom">Custom range...</option>
            </select>
            {period==='custom'&&(
              <>
                <input type="date" value={customStart} onChange={e=>setCustomStart(e.target.value)} style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:8,padding:'7px 10px',color:'#e2e8f0',fontSize:12,outline:'none',fontFamily:F}}/>
                <span style={{color:'#334155',fontSize:12}}>→</span>
                <input type="date" value={customEnd} onChange={e=>setCustomEnd(e.target.value)} style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:8,padding:'7px 10px',color:'#e2e8f0',fontSize:12,outline:'none',fontFamily:F}}/>
              </>
            )}
            {accounts.length>1&&(
              <div style={{position:'relative'}}>
                <button onClick={()=>setShowAcctMenu(s=>!s)} style={{background:'#0f1117',border:`1px solid ${acctFilter!=='all'?'#3b82f6':'#1e2030'}`,borderRadius:10,padding:'8px 14px',color:acctFilter!=='all'?'#3b82f6':'#94a3b8',fontSize:13,cursor:'pointer',fontFamily:F}}>
                  {acctFilter==='all'?'All accounts':acctFilter} ▾
                </button>
                {showAcctMenu&&(
                  <div style={{position:'absolute',top:'calc(100% + 6px)',right:0,background:'#0f1117',border:'1px solid #1e2030',borderRadius:12,padding:6,minWidth:180,zIndex:100,boxShadow:'0 8px 32px rgba(0,0,0,0.5)'}}>
                    {['all',...accounts].map(a=>(
                      <button key={a} onClick={()=>{setAcctFilter(a);setShowAcctMenu(false)}} style={{display:'block',width:'100%',textAlign:'left',padding:'9px 14px',borderRadius:8,border:'none',background:acctFilter===a?'#1e2030':'transparent',color:acctFilter===a?'#fff':'#94a3b8',fontSize:13,cursor:'pointer',fontFamily:F}}>
                        {a==='all'?'All accounts':a}{acctFilter===a&&<span style={{float:'right',color:'#3b82f6'}}>✓</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* PARTIAL MONTH BANNER */}
        {partialInfo?.isPartial&&(
          <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px 16px',background:'rgba(99,102,241,0.05)',border:'1px solid rgba(99,102,241,0.15)',borderRadius:10,marginBottom:16}}>
            <span style={{fontSize:12,color:'#818cf8'}}>📅 Partial data · {partialInfo.earliest} → {partialInfo.latest}</span>
          </div>
        )}

        {/* CC-ONLY BANNER */}
        {isCCOnly && (
          <div style={{display:'flex',alignItems:'flex-start',gap:12,padding:'12px 18px',background:'rgba(59,130,246,0.05)',border:'1px solid rgba(59,130,246,0.15)',borderRadius:12,marginBottom:16}}>
            <span style={{fontSize:16,flexShrink:0}}>🏦</span>
            <div style={{flex:1}}>
              <p style={{color:'#93c5fd',fontSize:13,fontWeight:600,marginBottom:3}}>Looks like you uploaded credit card statements only</p>
              <p style={{color:'#475569',fontSize:12,lineHeight:1.6}}>Fixed expenses like rent, mortgage, and car payments are usually paid from a bank account. Upload your bank statement or add them manually in <a href="/app/goals" style={{color:'#3b82f6',textDecoration:'none',fontWeight:600}}>Goals</a> for complete tracking.</p>
            </div>
            <Link to="/app/upload" style={{background:'rgba(59,130,246,0.1)',color:'#3b82f6',border:'1px solid rgba(59,130,246,0.2)',padding:'6px 14px',borderRadius:8,textDecoration:'none',fontWeight:600,fontSize:12,whiteSpace:'nowrap',flexShrink:0}}>Upload bank →</Link>
          </div>
        )}

        {/* ALL-FIXED EDGE CASE */}
        {allSpendingIsFixed && (
          <div style={{display:'flex',alignItems:'center',gap:10,padding:'10px 16px',background:'rgba(100,116,139,0.06)',border:'1px solid rgba(100,116,139,0.2)',borderRadius:10,marginBottom:16}}>
            <span style={{fontSize:14}}>ℹ️</span>
            <span style={{fontSize:12,color:'#94a3b8'}}>All detected spending this period is classified as fixed — no variable spend found. Your full budget of <strong>{fmt(monthlyBudget)}</strong> remains available.</span>
          </div>
        )}

        {/* ── 3 KPI CARDS ── */}
        {/* HERO KPIs — Awareness-first redesign */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12,marginBottom:14}}>

          {/* Card 1: SPENT — primary KPI, slightly larger */}
          <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:18,padding:'24px 26px'}}>
            <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px',marginBottom:18}}>Spent</p>
            <div style={{fontSize:36,fontWeight:800,color:'#10b981',letterSpacing:'-1.2px',fontFamily:'monospace',lineHeight:1,marginBottom:14}}>
              {summary?.current_month ? fmt(summary.current_month.total) : '—'}
            </div>
            {(compShow||compUnavailableShow) ? (
              <div style={{marginBottom:14}}>
                <span style={{fontSize:12,padding:'4px 10px',borderRadius:8,fontWeight:700,background:compBg,color:compColor,display:'inline-block'}}>
                  {compArrow}{compText}
                </span>
              </div>
            ) : (
              <div style={{height:14,marginBottom:14}}/>
            )}
            <p style={{fontSize:12,color:'#475569',margin:0}}>
              {summary?.current_month?.txn_count ?? 0} transactions
            </p>
          </div>

          {/* Card 2: TOP CATEGORY */}
          <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:18,padding:'24px 26px'}}>
            <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px',marginBottom:18}}>Top category</p>
            {summary?.current_month?.top_category ? (
              <>
                <div style={{fontSize:28,fontWeight:800,color:'#f1f5f9',letterSpacing:'-0.5px',lineHeight:1.1,marginBottom:14}}>
                  {summary.current_month.top_category.name}
                </div>
                <div style={{fontSize:13,color:'#94a3b8',marginBottom:14}}>
                  <span style={{fontFamily:'monospace',color:'#10b981',fontWeight:700}}>{fmt(summary.current_month.top_category.amount)}</span>
                  <span style={{color:'#475569',margin:'0 6px'}}>·</span>
                  <span>{summary.current_month.top_category.pct_of_flexible}%</span>
                </div>
                <p style={{fontSize:12,color:'#475569',margin:0}}>
                  {summary.current_month.top_category.txn_count} transaction{summary.current_month.top_category.txn_count===1?'':'s'}
                </p>
              </>
            ) : (
              <div style={{fontSize:14,color:'#475569'}}>No flexible spending this month</div>
            )}
          </div>

          {/* Card 3: BIGGEST CHARGE */}
          <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:18,padding:'24px 26px'}}>
            <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px',marginBottom:18}}>Biggest charge</p>
            {summary?.current_month?.biggest_charge ? (
              <>
                <div style={{fontSize:28,fontWeight:800,color:'#f1f5f9',letterSpacing:'-0.5px',lineHeight:1.1,marginBottom:14,wordBreak:'break-word'}}>
                  {summary.current_month.biggest_charge.merchant}
                </div>
                <div style={{fontSize:14,color:'#10b981',fontWeight:700,marginBottom:14,fontFamily:'monospace'}}>
                  {fmt(summary.current_month.biggest_charge.amount)}
                </div>
                <p style={{fontSize:12,color:'#475569',margin:0}}>
                  {summary.current_month.biggest_charge.date && new Date(summary.current_month.biggest_charge.date+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'})}
                  {summary.current_month.biggest_charge.category && (
                    <span> · {summary.current_month.biggest_charge.category}</span>
                  )}
                </p>
              </>
            ) : (
              <div style={{fontSize:14,color:'#475569'}}>No charges this month</div>
            )}
          </div>

        </div>

        {/* DISCRETIONARY vs FIXED — Section 2 */}
        {summary?.current_month && (() => {
          const cm = summary.current_month
          const total = cm.total || 0
          const disc = cm.flexible || 0
          const fix = cm.committed || 0
          if (total <= 0) return null
          const dPct = Math.round((disc / total) * 100)
          const fPct = 100 - dPct
          const copy = (
            dPct >= 85 ? 'Most of your spending was discretionary this month.' :
            dPct >= 60 ? `Your spending was mostly discretionary — ${dPct}% this month.` :
            dPct >= 40 ? 'Your spending was evenly split between discretionary and fixed.' :
            dPct >= 15 ? 'Most of your spending was fixed costs this month.' :
                         'Almost all of your spending was fixed costs this month.'
          )
          return (
            <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:18,padding:'24px 26px',marginBottom:14}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:18}}>
                <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px'}}>
                  Discretionary vs Fixed
                </p>
                <span style={{fontSize:12,color:'#475569'}}>
                  {fmt(total)} total · {cm.label}
                </span>
              </div>

              <div style={{display:'flex',height:14,borderRadius:99,overflow:'hidden',marginBottom:14,background:'#1a1f2e',gap:2}}>
                <div style={{width:dPct+'%',background:'linear-gradient(90deg,#3b82f6,#6366f1)',transition:'width 0.5s',borderRadius:99}}/>
                <div style={{width:fPct+'%',background:'#475569',transition:'width 0.5s',borderRadius:99}}/>
              </div>

              <div style={{display:'flex',justifyContent:'space-between',marginBottom:14,flexWrap:'wrap',gap:8}}>
                <div>
                  <span style={{display:'inline-block',width:8,height:8,borderRadius:2,background:'#6366f1',marginRight:8,verticalAlign:'middle'}}/>
                  <span style={{fontSize:14,fontWeight:700,color:'#cbd5e1'}}>Discretionary</span>
                  <span style={{fontSize:14,color:'#10b981',fontFamily:'monospace',fontWeight:700,marginLeft:10}}>{fmt(disc)}</span>
                  <span style={{fontSize:13,color:'#64748b',marginLeft:8}}>· {dPct}%</span>
                </div>
                <div style={{textAlign:'right'}}>
                  <span style={{display:'inline-block',width:8,height:8,borderRadius:2,background:'#475569',marginRight:8,verticalAlign:'middle'}}/>
                  <span style={{fontSize:14,fontWeight:700,color:'#cbd5e1'}}>Fixed</span>
                  <span style={{fontSize:14,color:'#10b981',fontFamily:'monospace',fontWeight:700,marginLeft:10}}>{fmt(fix)}</span>
                  <span style={{fontSize:13,color:'#64748b',marginLeft:8}}>· {fPct}%</span>
                </div>
              </div>

              <p style={{fontSize:13,color:'#94a3b8',lineHeight:1.5,margin:0}}>{copy}</p>
            </div>
          )
        })()}

        {/* SPENDING BY CATEGORY — Section 3, Phase 2 (Chunk 2: collapsed list) */}
        {summary?.current_month?.categories && summary.current_month.categories.length > 0 && (() => {
          const cats = summary.current_month.categories
          // Split into shown + others (< 2% pct_of_flexible)
          const shown = cats.filter(c => c.pct_of_flexible >= 2)
          const others = cats.filter(c => c.pct_of_flexible < 2)
          const othersTotal = others.reduce((s, c) => s + c.amount, 0)
          const othersCount = others.reduce((s, c) => s + c.txn_count, 0)
          const othersPct = others.reduce((s, c) => s + c.pct_of_flexible, 0)
          // Top amount for relative-bar scaling (uses the largest category, NOT total)
          const topAmount = cats[0]?.amount || 1
          return (
            <div style={{background:'#0f1117',border:'1px solid #1e2030',borderRadius:18,padding:'24px 26px',marginBottom:14}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:18}}>
                <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px'}}>
                  Spending by category
                </p>
                <span style={{fontSize:12,color:'#475569'}}>
                  {shown.length} categor{shown.length === 1 ? 'y' : 'ies'} · flexible only
                </span>
              </div>

              <div style={{display:'flex',flexDirection:'column',gap:2}}>
                {shown.map((c, i) => {
                  const barPct = Math.max(2, Math.round((c.amount / topAmount) * 100))
                  const icon = CAT_ICONS[c.name] || '📦'
                  return (
                    <React.Fragment key={c.name}>
                    <div
                      style={{
                        display:'grid',
                        gridTemplateColumns:'28px 1fr 90px 180px 50px 20px',
                        gap:14,
                        alignItems:'center',
                        padding:'12px 8px',
                        borderRadius:10,
                        cursor:'pointer',
                        transition:'background 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = '#151720'}
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
                      <span style={{fontSize:18}}>{icon}</span>
                      <span style={{fontSize:14,color:'#f1f5f9',fontWeight:500}}>{c.name}</span>
                      <span style={{fontSize:14,fontWeight:700,color:'#10b981',fontFamily:'monospace',textAlign:'right'}}>
                        {fmt(c.amount)}
                      </span>
                      <div style={{background:'#1a1f2e',borderRadius:99,height:6,overflow:'hidden'}}>
                        <div style={{height:'100%',width:`${barPct}%`,background:'linear-gradient(90deg,#3b82f6,#6366f1)',transition:'width 0.5s'}}/>
                      </div>
                      <span style={{fontSize:13,color:'#64748b',textAlign:'right'}}>{Math.round(c.pct_of_flexible)}%</span>
                      <span style={{fontSize:14,color:'#475569',textAlign:'center',transform:expandedCats.has(c.name)?'rotate(90deg)':'rotate(0deg)',transition:'transform 0.2s'}}>›</span>
                    </div>

                    {expandedCats.has(c.name) && (
                      <div style={{
                        padding:'12px 8px 18px 50px',
                        animation:'xspendFadeIn 150ms ease-out',
                      }}>
                        {/* Context line */}
                        <div style={{fontSize:12,color:'#64748b',marginBottom:6}}>
                          {c.txn_count} transaction{c.txn_count===1?'':'s'} · avg {fmt(c.avg_amount)}
                        </div>

                        {/* Interpretive insight */}
                        {c.insight?.text && (
                          <div style={{fontSize:13,color:'#cbd5e1',marginBottom:16,fontStyle:'italic'}}>
                            {c.insight.text}
                          </div>
                        )}

                        {/* Top transactions */}
                        {c.top_transactions && c.top_transactions.length > 0 && (
                          <>
                            <div style={{fontSize:10,fontWeight:700,color:'#475569',textTransform:'uppercase',letterSpacing:'1px',marginBottom:8}}>
                              Top transactions
                            </div>
                            <div style={{display:'flex',flexDirection:'column',gap:4,marginBottom:14}}>
                              {c.top_transactions.map((tx, ti) => (
                                <div key={ti} style={{display:'grid',gridTemplateColumns:'70px 1fr 100px',gap:12,alignItems:'baseline',fontSize:13,padding:'4px 0'}}>
                                  <span style={{color:'#64748b'}}>
                                    {tx.date && new Date(tx.date+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'})}
                                  </span>
                                  <span style={{color:'#e2e8f0'}}>{tx.merchant}</span>
                                  <span style={{color:'#10b981',fontFamily:'monospace',textAlign:'right',fontWeight:600}}>
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
                          style={{fontSize:12,color:'#3b82f6',textDecoration:'none',display:'inline-block',marginRight:18}}
                          onMouseEnter={e => e.currentTarget.style.textDecoration='underline'}
                          onMouseLeave={e => e.currentTarget.style.textDecoration='none'}
                        >
                          View all {c.name} transactions →
                        </a>

                        {/* Soft limit placeholder */}
                        <button
                          style={{
                            background:'transparent',
                            border:'1px dashed #334155',
                            borderRadius:6,
                            padding:'4px 10px',
                            fontSize:12,
                            color:'#64748b',
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

                {others.length > 0 && (
                  <div
                    style={{
                      display:'grid',
                      gridTemplateColumns:'28px 1fr 90px 180px 50px 20px',
                      gap:14,
                      alignItems:'center',
                      padding:'12px 8px',
                      marginTop:6,
                      borderTop:'1px solid #1e2030',
                      paddingTop:14,
                      cursor:'pointer',
                      borderRadius:10,
                      transition:'background 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = '#151720'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <span style={{fontSize:16}}>📦</span>
                    <span style={{fontSize:13,color:'#94a3b8'}}>
                      Others <span style={{color:'#475569',marginLeft:6}}>· {others.length} categor{others.length === 1 ? 'y' : 'ies'} · {othersCount} txn{othersCount === 1 ? '' : 's'}</span>
                    </span>
                    <span style={{fontSize:13,fontWeight:700,color:'#10b981',fontFamily:'monospace',textAlign:'right'}}>
                      {fmt(othersTotal)}
                    </span>
                    <div style={{background:'#1a1f2e',borderRadius:99,height:4,overflow:'hidden',opacity:0.6}}>
                      <div style={{height:'100%',width:`${Math.max(2, Math.round((othersTotal / topAmount) * 100))}%`,background:'#475569',transition:'width 0.5s'}}/>
                    </div>
                    <span style={{fontSize:12,color:'#475569',textAlign:'right'}}>{Math.round(othersPct)}%</span>
                    <span style={{fontSize:14,color:'#475569',textAlign:'center'}}>›</span>
                  </div>
                )}
              </div>
            </div>
          )
        })()}

        {/* SPENDING EXPLANATION */}
        <SpendingExplanation expTotal={totalExp} cardPmts={cardPmts} transfers={transfers} credits={credits} acctFilter={acctFilter}/>

        {/* FIXED EXPENSES */}
        <FixedSummaryCard/>

        {/* TREND + INSIGHTS side by side */}
        <div style={{display:'grid',gridTemplateColumns:'1.2fr 1fr',gap:14,marginBottom:14,alignItems:'stretch'}}>

          {/* Trend — smaller */}
          <div style={{...card,display:'flex',flexDirection:'column'}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
              <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px'}}>Monthly trend</p>
              {(compShow||compUnavailableShow)&&(
                <span style={{fontSize:12,fontWeight:700,color:compColor,background:compBg,padding:'4px 10px',borderRadius:8,border:`1px solid ${compShow?(comp.direction==='up'?'rgba(239,68,68,0.15)':comp.direction==='down'?'rgba(16,185,129,0.15)':'rgba(148,163,184,0.15)'):'rgba(100,116,139,0.15)'}`}}>
                  {compArrow}{compText}
                </span>
              )}
            </div>
            {summary?.trend_chart?.show && trendData.length>=2?(
              <div style={{flex:1,display:'flex',flexDirection:'column'}}>
                <div style={{display:'flex',gap:16,marginBottom:12}}>
                  <div style={{display:'flex',alignItems:'center',gap:6}}><div style={{width:10,height:10,borderRadius:2,background:'#8b5cf6'}}/><span style={{fontSize:11,color:'#64748b'}}>Committed</span></div>
                  <div style={{display:'flex',alignItems:'center',gap:6}}><div style={{width:10,height:10,borderRadius:2,background:'#10b981'}}/><span style={{fontSize:11,color:'#64748b'}}>Flexible</span></div>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={trendData} barCategoryGap="30%" barSize={28}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#0f1117" vertical={false}/>
                    <XAxis dataKey="label" tick={{fill:'#94a3b8',fontSize:12}} axisLine={false} tickLine={false}/>
                    <YAxis tick={{fill:'#94a3b8',fontSize:12,fontWeight:600}} axisLine={false} tickLine={false} tickFormatter={v=>'$'+Math.round(v/1000)+'k'} width={45}/>
                    <Tooltip content={<BarTip/>}/>
                    <Bar dataKey="Fixed" radius={[6,6,0,0]} maxBarSize={24}>
                      {trendData.map((d,i)=><Cell key={i} fill={d.month===activePeriodMonth?'#8b5cf6':'#4c1d95'}/>)}
                    </Bar>
                    <Bar dataKey="Variable" radius={[6,6,0,0]} maxBarSize={24}>
                      {trendData.map((d,i)=><Cell key={i} fill={d.month===activePeriodMonth?'#10b981':'#064e3b'}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ):(
              <div style={{height:160,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:10}}>
                <p style={{color:'#475569',fontSize:13}}>Upload another month to see trends</p>
                <Link to="/app/upload" style={{color:'#3b82f6',fontSize:13,textDecoration:'none',fontWeight:600}}>Upload →</Link>
              </div>
            )}
          </div>

          {/* Insights — beside trend */}
          <div style={{...card,display:'flex',flexDirection:'column',minHeight:320}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
              <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px'}}>Insights</p>
              {insights.length > 0 && <span style={{fontSize:10,color:'#283244'}}>{insights.length} for {periodLabel}</span>}
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:10,overflowY:'auto',maxHeight:320,paddingRight:4}}>
              {insightsLoading && (
                <div style={{textAlign:'center',padding:'20px 0',color:'#334155',fontSize:12}}>Analyzing your spending…</div>
              )}
              {!insightsLoading && insights.length === 0 && (
                <div style={{textAlign:'center',padding:'20px 0'}}>
                  <p style={{color:'#334155',fontSize:12,marginBottom:8}}>No insights yet for this period</p>
                  {fullMonths.length <= 1 && (
                    <Link to="/app/upload" style={{fontSize:11,color:'#3b82f6',textDecoration:'none',fontWeight:600}}>Upload another month to unlock insights →</Link>
                  )}
                </div>
              )}
              {!insightsLoading && insights.map((ins,i) => (
                <div key={i} style={{display:'flex',gap:12,padding:'12px 14px',background:'#0a0d12',borderRadius:12,borderLeft:`3px solid ${ins.color}`,cursor:ins.action_filter?'pointer':'default'}}
                  onClick={() => ins.action_filter && window.location.assign('/app/transactions?cat='+ins.action_filter)}>
                  <span style={{fontSize:16,flexShrink:0}}>{ins.icon}</span>
                  <div style={{flex:1}}>
                    <p style={{fontSize:12,fontWeight:700,color:'#e2e8f0',marginBottom:3,lineHeight:1.3}}>{ins.title}</p>
                    <p style={{fontSize:11,color:'#475569',lineHeight:1.5}}>{ins.body}</p>
                    {ins.action && <p style={{fontSize:10,color:ins.color,marginTop:4,fontWeight:600}}>{ins.action} →</p>}
                  </div>
                </div>
              ))}
              {!insightsLoading && fullMonths.length <= 1 && insights.length > 0 && (
                <div style={{padding:'10px 14px',background:'rgba(59,130,246,0.05)',border:'1px solid rgba(59,130,246,0.12)',borderRadius:10,textAlign:'center'}}>
                  <p style={{fontSize:11,color:'#475569',marginBottom:4}}>🔓 Upload 2-3 months to unlock trend insights</p>
                  <Link to="/app/upload" style={{fontSize:11,color:'#3b82f6',textDecoration:'none',fontWeight:600}}>Upload another month →</Link>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── BANK RECONCILIATION INSIGHT ── */}
        {(() => {
          const nonSpend = acctFiltered.filter(t =>
            ['transfer','credit_card_payment','reimbursement','card_credit'].includes(t.transaction_type)
          ).reduce((s,t) => s + Math.abs(t.amount), 0)
          if (nonSpend < 200) return null
          return (
            <div style={{background:'rgba(59,130,246,0.04)',border:'1px solid rgba(59,130,246,0.12)',borderRadius:12,padding:'12px 18px',marginBottom:14,display:'flex',alignItems:'center',gap:10}}>
              <span style={{fontSize:14}}>💡</span>
              <p style={{fontSize:12,color:'#475569',lineHeight:1.6}}>
                Your bank balance includes <strong style={{color:'#94a3b8'}}>{fmt(nonSpend)}</strong> in transfers and card payments.
                We only count real spending — that's why the numbers differ.
              </p>
            </div>
          )
        })()}

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
              sub: cardCredits.length + ' benefit credit' + (cardCredits.length !== 1 ? 's' : '') + ' · offset against charges' },
            { icon:'↔️', label:'Transfers out', amount:transferTotal, color:'#8b5cf6', show: transferTotal > 0,
              sub: transfers.length + ' transfer' + (transfers.length !== 1 ? 's' : '') + ' · not real spending' },
            { icon:'🏦', label:'Card payments', amount:ccTotal, color:'#3b82f6', show: ccTotal > 0,
              sub: ccPayments.length + ' payment' + (ccPayments.length !== 1 ? 's' : '') + ' · paying off your card balance' },
            { icon:'🔄', label:'Refunds', amount:refundTotal, color:'#f59e0b', show: refundTotal > 0,
              sub: refunds.length + ' refund' + (refunds.length !== 1 ? 's' : '') + ' · money back to you' },
          ].filter(i => i.show)

          if (items.length === 0) return null
          return (
            <div style={{display:'flex', gap:12, marginBottom:14, flexWrap:'wrap'}}>
              {items.map((item, i) => (
                <div key={i} style={{...card, flex:1, minWidth:140, padding:'14px 18px', display:'flex', alignItems:'center', gap:12}}>
                  <span style={{fontSize:18}}>{item.icon}</span>
                  <div>
                    <p style={{fontSize:10, color:'#475569', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.8px', marginBottom:3}}>{item.label}</p>
                    <p style={{fontSize:16, fontWeight:800, color:item.color, fontFamily:'monospace', marginBottom:2}}>{fmt(item.amount)}</p>
                    {item.sub && <p style={{fontSize:10, color:'#334155', lineHeight:1.4}}>{item.sub}</p>}
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
              <p style={{fontSize:11,fontWeight:700,color:'#94a3b8',textTransform:'uppercase',letterSpacing:'1.2px',marginBottom:3}}>Top transactions</p>
              <p style={{fontSize:12,color:'#334155'}}>{periodLabel}</p>
            </div>
            <Link to="/app/transactions" style={{fontSize:12,color:'#3b82f6',textDecoration:'none',fontWeight:600}}>View all →</Link>
          </div>
          {top10.length>0?(
            <table style={{width:'100%',borderCollapse:'collapse'}}>
              <thead>
                <tr>
                  {['Date','Description','Category','Amount'].map((h,i)=>(
                    <th key={h} style={{padding:'8px 14px',color:'#283244',fontSize:10,fontWeight:700,textTransform:'uppercase',letterSpacing:'1px',textAlign:i===3?'right':'left',borderBottom:'1px solid #0f1117'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {top10.map((t,i)=>(
                  <tr key={i} style={{borderBottom:'1px solid #0a0d12',transition:'background 0.1s'}}
                    onMouseEnter={e=>e.currentTarget.style.background='#0f1117'}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <td style={{padding:'11px 14px',color:'#334155',fontSize:12}}>{t.transaction_date}</td>
                    <td style={{padding:'11px 14px',color:'#e2e8f0',fontSize:13,fontWeight:500,maxWidth:260}}>
                      <div style={{display:'flex',alignItems:'center',gap:6}}>
                        {t.description}
                        {t.is_fixed&&<span style={{fontSize:9,color:'#475569',background:'#151720',padding:'1px 5px',borderRadius:3,fontWeight:600,flexShrink:0}}>FIXED</span>}
                      </div>
                    </td>
                    <td style={{padding:'11px 14px'}}>
                      <span style={{background:'#151720',color:'#64748b',fontSize:11,padding:'3px 9px',borderRadius:6,cursor:'pointer'}} onClick={()=>setDrillCat(t.category)}>{t.category}</span>
                    </td>
                    <td style={{padding:'11px 14px',textAlign:'right'}}>
                      <div style={{fontWeight:800,color:'#ef4444',fontFamily:'monospace',fontSize:14}}>
                        {t.credit_applied > 0 ? '-$'+t.net_amount.toFixed(2) : '$'+Math.abs(t.amount).toFixed(2)}
                      </div>
                      {t.credit_applied > 0 && <div style={{fontSize:10,color:'#475569',textDecoration:'line-through'}}>${Math.abs(t.amount).toFixed(2)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ):(
            <div style={{textAlign:'center',padding:'40px 0',color:'#334155',fontSize:13}}>No expense transactions in this period</div>
          )}
        </div>

        {/* GOALS LINK */}
        <div style={{padding:'18px 24px',background:'linear-gradient(135deg,rgba(59,130,246,0.06),rgba(139,92,246,0.06))',border:'1px solid rgba(59,130,246,0.12)',borderRadius:16,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
          <div>
            <p style={{fontSize:13,fontWeight:700,color:'#e2e8f0',marginBottom:3}}>For more insights</p>
            <p style={{fontSize:12,color:'#475569'}}>Add income, savings targets, what-if calculator and project tracking</p>
          </div>
          <Link to="/app/goals" style={{background:'rgba(59,130,246,0.1)',color:'#3b82f6',border:'1px solid rgba(59,130,246,0.2)',padding:'9px 18px',borderRadius:10,textDecoration:'none',fontWeight:700,fontSize:13,whiteSpace:'nowrap'}}>Set up goals →</Link>
        </div>

      </div>
      {drillCat&&<DrillDown category={drillCat} transactions={acctFiltered} onClose={()=>setDrillCat(null)}/>}
    </div>
  )
}
