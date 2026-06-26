import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_URL } from '../lib/config'

const GOALS = [
  { value:'understand',    label:'Understand my finances',         icon:'📊' },
  { value:'spending',      label:'Manage spending better',         icon:'💳' },
  { value:'savings',       label:'Build savings',                  icon:'🏦' },
  { value:'debt',          label:'Pay off debt',                   icon:'📉' },
  { value:'budget',        label:'Stay on budget',                 icon:'🎯' },
  { value:'subscriptions', label:'Reduce subscriptions',           icon:'📱' },
  { value:'bills',         label:'Track bills better',             icon:'📋' },
  { value:'irregular',     label:'Prepare for irregular expenses', icon:'🔄' },
]

const STEPS = [
  { id:'welcome',  title:'Welcome to xspend',       subtitle:'Your private, AI-powered finance tracker.' },
  { id:'name',     title:'What should we call you?',   subtitle:'Just your first name is fine.' },
  { id:'budget',   title:'Set your monthly budget',    subtitle:'This powers your Left to Spend tracker — how much you plan to spend each month.' },
  { id:'goals',    title:'What are you here for?',     subtitle:'Pick everything that applies.' },
  { id:'targets',  title:'Optional targets',           subtitle:'Skip if you\'re not sure yet — you can set these later in Goals.' },
  { id:'done',     title:'All set!',                   subtitle:'Start by uploading a bank statement.' },
]

export default function Onboarding() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    full_name: '',
    monthly_budget: '',
    selected_goals: [],
    other_goals: '',
    income_amount: '',
    monthly_savings_goal: '',
    debt_payoff_goal: '',
  })

  const current = STEPS[step]
  const progress = (step / (STEPS.length - 1)) * 100
  const back = () => setStep(s => Math.max(s - 1, 0))

  const canContinue = () => {
    if (step === 1 && !form.full_name.trim()) return false
    if (step === 2 && !form.monthly_budget) return false
    return true
  }

  const next = () => {
    if (!canContinue()) return
    setStep(s => Math.min(s + 1, STEPS.length - 1))
  }

  const toggleGoal = (val) => {
    setForm(f => ({
      ...f,
      selected_goals: f.selected_goals.includes(val)
        ? f.selected_goals.filter(g => g !== val)
        : [...f.selected_goals, val]
    }))
  }

  const handleFinish = async () => {
    setSaving(true)
    try {
      await fetch(`${API_URL}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: form.full_name,
          monthly_budget: parseFloat(form.monthly_budget) || 0,
          income_amount: parseFloat(form.income_amount) || 0,
          monthly_income: parseFloat(form.income_amount) || 0,
          preferred_currency: 'USD',
          currency_code: 'USD',
          selected_goals: form.selected_goals.join(','),
          other_goals: form.other_goals,
          monthly_savings_goal: parseFloat(form.monthly_savings_goal) || 0,
          savings_goal_monthly: parseFloat(form.monthly_savings_goal) || 0,
          debt_payoff_goal: parseFloat(form.debt_payoff_goal) || 0,
        })
      })
      localStorage.setItem('onboarding_complete', 'true')
      if (form.full_name) localStorage.setItem('user_name', form.full_name.split(' ')[0])
    } catch(e) {
      console.error(e)
      localStorage.setItem('onboarding_complete', 'true')
    }
    setSaving(false)
    navigate('/app/upload')
  }

  const S = {
    page: { minHeight:'100vh', background:'#0a0a0f', display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'DM Sans, Inter, sans-serif', padding:24 },
    card: { background:'#12121e', border:'1px solid #1e1e2e', borderRadius:24, padding:'44px 48px', width:'100%', maxWidth:540 },
    progress: { background:'#1e1e2e', borderRadius:99, height:3, marginBottom:36, overflow:'hidden' },
    progressFill: { height:'100%', borderRadius:99, background:'linear-gradient(90deg,#2563eb,#7c3aed)', transition:'width 0.4s ease', width:`${progress}%` },
    stepNum: { color:'#4a4a6a', fontSize:13, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', marginBottom:10 },
    title: { color:'#fff', fontSize:26, fontWeight:700, marginBottom:6, letterSpacing:'-0.3px', lineHeight:1.2 },
    subtitle: { color:'#6a6a8a', fontSize:15, lineHeight:1.6, marginBottom:32 },
    label: { display:'block', color:'#8888aa', fontSize:13, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', marginBottom:8 },
    hint: { color:'#4a4a6a', fontSize:13, marginTop:7, lineHeight:1.5 },
    input: { width:'100%', background:'#0a0a0f', border:'1px solid #2a2a3a', borderRadius:10, padding:'12px 14px', color:'#fff', fontSize:17, outline:'none', boxSizing:'border-box', fontFamily:'inherit' },
    btnRow: { display:'flex', gap:10, marginTop:36 },
    btnPrimary: (disabled) => ({ flex:1, background: disabled ? '#1e2030' : '#2563eb', color: disabled ? '#4a4a6a' : '#fff', border:'none', borderRadius:12, padding:'13px', fontSize:16, fontWeight:700, cursor: disabled ? 'not-allowed' : 'pointer', fontFamily:'inherit', transition:'all 0.15s' }),
    btnSecondary: { background:'#1e1e2e', color:'#8888aa', border:'1px solid #2a2a3a', borderRadius:12, padding:'13px 18px', fontSize:15, fontWeight:600, cursor:'pointer', fontFamily:'inherit' },
    skip: { textAlign:'center', color:'#4a4a6a', fontSize:14, marginTop:14, cursor:'pointer' },
    option: (sel) => ({ background:sel?'rgba(37,99,235,0.12)':'#0a0a0f', border:`1px solid ${sel?'#2563eb':'#2a2a3a'}`, borderRadius:10, padding:'12px 14px', color:sel?'#fff':'#8888aa', fontSize:15, fontWeight:sel?600:400, cursor:'pointer', textAlign:'left', transition:'all 0.15s', fontFamily:'inherit', display:'flex', alignItems:'center', gap:8 }),
    summaryRow: (i, len) => ({ display:'flex', justifyContent:'space-between', padding:'9px 0', borderBottom:i<len-1?'1px solid #1e1e2e':'none' }),
  }

  return (
    <div style={S.page}>
      <div style={S.card}>

        {/* Logo */}
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:36 }}>
          <div style={{ width:34, height:34, borderRadius:10, background:'linear-gradient(135deg,#2563eb,#1d4ed8)', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:800, fontSize:17 }}>x</div>
          <span style={{ color:'#fff', fontWeight:700, fontSize:17 }}>xspend</span>
        </div>

        {/* Progress */}
        <div style={S.progress}><div style={S.progressFill}/></div>

        {step > 0 && step < STEPS.length - 1 && (
          <p style={S.stepNum}>Step {step} of {STEPS.length - 2}</p>
        )}
        <h2 style={S.title}>{current.title}</h2>
        <p style={S.subtitle}>{current.subtitle}</p>

        {/* ── WELCOME ── */}
        {step === 0 && (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            {[
              ['🔒','Privacy first','Your data stays on your device.'],
              ['📊','Budget tracking','Know exactly how much you have left to spend.'],
              ['💬','AI assistant','Ask anything about your money in plain English.'],
              ['✏️','Fully editable','Change anything anytime in Settings.'],
            ].map(([icon,title,desc],i) => (
              <div key={i} style={{ background:'#0a0a0f', border:'1px solid #1e1e2e', borderRadius:10, padding:14 }}>
                <div style={{ fontSize:22, marginBottom:7 }}>{icon}</div>
                <p style={{ color:'#fff', fontWeight:600, fontSize:14, marginBottom:4 }}>{title}</p>
                <p style={{ color:'#4a4a6a', fontSize:13, lineHeight:1.5 }}>{desc}</p>
              </div>
            ))}
          </div>
        )}

        {/* ── NAME ── */}
        {step === 1 && (
          <div>
            <label style={S.label}>Your first name</label>
            <input style={S.input} placeholder="e.g. Dharani" value={form.full_name}
              onChange={e => setForm({...form, full_name:e.target.value})}
              onKeyDown={e => e.key==='Enter' && canContinue() && next()}
              autoFocus/>
            {form.full_name === '' && <p style={{...S.hint, color:'#ef4444', marginTop:8}}>Required to continue</p>}
          </div>
        )}

        {/* ── BUDGET (required) ── */}
        {step === 2 && (
          <div>
            <label style={S.label}>Monthly budget <span style={{ color:'#ef4444', letterSpacing:0, textTransform:'none', fontWeight:400 }}>required</span></label>
            <div style={{ position:'relative', marginBottom:12 }}>
              <span style={{ position:'absolute', left:14, top:'50%', transform:'translateY(-50%)', color:'#4a4a6a', fontSize:20 }}>$</span>
              <input type="number" style={{...S.input, paddingLeft:32, fontSize:26, fontWeight:700}}
                placeholder="0"
                value={form.monthly_budget}
                onChange={e => setForm({...form, monthly_budget:e.target.value})}
                onKeyDown={e => e.key==='Enter' && canContinue() && next()}
                autoFocus/>
            </div>
            <p style={S.hint}>💡 How much you plan to spend per month on variable expenses — groceries, dining, shopping, etc. Fixed costs like rent are tracked separately and don't count against this budget.</p>

            <div style={{ display:'flex', gap:8, marginTop:16, flexWrap:'wrap' }}>
              {[1500, 2000, 2500, 3000, 4000].map(v => (
                <button key={v} onClick={() => setForm({...form, monthly_budget: String(v)})}
                  style={{ background: form.monthly_budget===String(v)?'rgba(37,99,235,0.15)':'#0a0a0f', border:`1px solid ${form.monthly_budget===String(v)?'#2563eb':'#2a2a3a'}`, borderRadius:8, padding:'6px 14px', color: form.monthly_budget===String(v)?'#fff':'#6a6a8a', fontSize:15, cursor:'pointer', fontFamily:'inherit' }}>
                  ${v.toLocaleString()}
                </button>
              ))}
            </div>

            {!form.monthly_budget && (
              <div style={{ marginTop:16, padding:'10px 14px', background:'rgba(239,68,68,0.06)', border:'1px solid rgba(239,68,68,0.2)', borderRadius:8 }}>
                <p style={{ color:'#ef4444', fontSize:14 }}>⚠ A monthly budget is required — this powers your Left to Spend tracker.</p>
              </div>
            )}
          </div>
        )}

        {/* ── GOALS ── */}
        {step === 3 && (
          <div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              {GOALS.map(g => (
                <button key={g.value} onClick={() => toggleGoal(g.value)}
                  style={S.option(form.selected_goals.includes(g.value))}>
                  <span style={{ fontSize:18 }}>{g.icon}</span>
                  <span style={{ fontSize:14 }}>{g.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── OPTIONAL TARGETS ── */}
        {step === 4 && (
          <div>
            <div style={{ background:'rgba(37,99,235,0.06)', border:'1px solid rgba(37,99,235,0.15)', borderRadius:10, padding:'12px 16px', marginBottom:20 }}>
              <p style={{ color:'#6a8adf', fontSize:14, lineHeight:1.6 }}>
                These are optional and used for deeper insights in your Goals section. Your dashboard works perfectly without them.
              </p>
            </div>
            {[
              { label:'Monthly income',       field:'income_amount',        placeholder:'e.g. 5000', hint:'Your take-home pay after tax' },
              { label:'Monthly savings target', field:'monthly_savings_goal', placeholder:'e.g. 500',  hint:'How much you want to save per month' },
              { label:'Total debt to pay off',  field:'debt_payoff_goal',     placeholder:'e.g. 8000', hint:'Used in your Goals section for debt tracking' },
            ].map((f,i) => (
              <div key={i} style={{ marginBottom:18 }}>
                <label style={S.label}>{f.label} <span style={{ color:'#4a4a6a', textTransform:'none', letterSpacing:0, fontWeight:400 }}>(optional)</span></label>
                <div style={{ position:'relative' }}>
                  <span style={{ position:'absolute', left:14, top:'50%', transform:'translateY(-50%)', color:'#4a4a6a', fontSize:17 }}>$</span>
                  <input type="number" style={{...S.input, paddingLeft:30}} placeholder={f.placeholder}
                    value={form[f.field]} onChange={e => setForm({...form,[f.field]:e.target.value})}/>
                </div>
                <p style={S.hint}>{f.hint}</p>
              </div>
            ))}
          </div>
        )}

        {/* ── DONE ── */}
        {step === STEPS.length - 1 && (
          <div>
            <p style={{ color:'#6a6a8a', fontSize:16, marginBottom:20 }}>
              Welcome, <strong style={{ color:'#fff' }}>{form.full_name || 'there'}</strong>! Here's what we saved:
            </p>
            <div style={{ background:'#0a0a0f', border:'1px solid #1e1e2e', borderRadius:12, padding:'14px 16px', marginBottom:24 }}>
              {[
                ['Monthly budget', `$${parseFloat(form.monthly_budget||0).toLocaleString()}`, true],
                ['Income',         form.income_amount ? `$${parseFloat(form.income_amount).toLocaleString()}/mo` : 'Not set', false],
                ['Savings target', form.monthly_savings_goal ? `$${parseFloat(form.monthly_savings_goal).toLocaleString()}/mo` : 'Not set', false],
                ['Debt goal',      form.debt_payoff_goal ? `$${parseFloat(form.debt_payoff_goal).toLocaleString()}` : 'Not set', false],
                ['Goals',          form.selected_goals.length ? `${form.selected_goals.length} selected` : 'None selected', false],
              ].map(([l,v,highlight],i,arr) => (
                <div key={i} style={S.summaryRow(i, arr.length)}>
                  <span style={{ color:'#6a6a8a', fontSize:15 }}>{l}</span>
                  <span style={{ color: highlight?'#3b82f6':'#fff', fontWeight:600, fontSize:15 }}>{v}</span>
                </div>
              ))}
            </div>
            <p style={{ color:'#4a4a6a', fontSize:14, textAlign:'center', marginBottom:24 }}>
              Everything can be updated anytime in Settings ⚙️
            </p>
            <button onClick={handleFinish} disabled={saving}
              style={{ width:'100%', background:'#2563eb', color:'#fff', border:'none', borderRadius:14, padding:'18px', cursor: saving?'not-allowed':'pointer', fontFamily:'inherit', fontSize:17, fontWeight:700, opacity:saving?0.6:1 }}>
              {saving ? 'Saving...' : '🚀 Upload your first statement →'}
            </button>
          </div>
        )}

        {/* BUTTONS */}
        {step < STEPS.length - 1 && (
          <div style={S.btnRow}>
            {step > 0 && <button onClick={back} style={S.btnSecondary}>← Back</button>}
            <button onClick={next} disabled={!canContinue()} style={S.btnPrimary(!canContinue())}>
              {step === 0 ? 'Get Started →' : step === STEPS.length - 2 ? 'Review & finish →' : 'Continue →'}
            </button>
          </div>
        )}

        {/* Skip — not shown on budget step */}
        {step > 0 && step < STEPS.length - 1 && step !== 2 && (
          <p style={S.skip} onClick={next}>Skip this step</p>
        )}

      </div>
    </div>
  )
}
