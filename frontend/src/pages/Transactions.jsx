import { useState, useEffect, useMemo } from 'react'
import { API_URL } from '../lib/config'

const DEFAULT_CATEGORIES = [
  'Food & Dining','Groceries','Transport','Rent & Utilities',
  'Subscriptions','Health','Shopping','Entertainment','Travel',
  'Personal Care','Pets','Education','Rent & Utilities','Government & Taxes','Bank Fees','Gifts & Donations','Professional Services','Baby & Kids','Alcohol & Liquor','Transfer','Credit Card Payment','Other'
]

const F = 'DM Sans, Inter, sans-serif'
const fmtAmt = n => (n>=0?'+':'-')+'$'+Math.abs(n).toFixed(2)
const fmt = n => '$' + Math.round(Math.abs(n)||0).toLocaleString()

// ── Project dropdown for a single transaction ──
function ProjectDropdown({ tx, projects, onAssign }) {
  const [open, setOpen] = useState(false)
  const current = projects.find(p => p.id === tx.project_id)

  const assign = async (projectId) => {
    setOpen(false)
    await fetch(`${API_URL}/transactions/${tx.id}/project`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId })
    }).catch(() => {})
    onAssign(tx.id, projectId)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ background: current ? 'rgba(139,92,246,0.1)' : 'none', border: `1px solid ${current ? 'rgba(139,92,246,0.3)' : '#1e2030'}`, borderRadius: 7, padding: '3px 10px', fontSize: 11, color: current ? '#8b5cf6' : '#334155', cursor: 'pointer', fontFamily: F, whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 5 }}>
        {current ? `📁 ${current.name}` : '+ Project'}
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, background: '#0f1117', border: '1px solid #1e2030', borderRadius: 12, padding: 6, minWidth: 180, zIndex: 100, boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}
          onClick={e => e.stopPropagation()}>
          {current && (
            <button onClick={() => assign(null)}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 8, border: 'none', background: 'transparent', color: '#475569', fontSize: 12, cursor: 'pointer', fontFamily: F }}>
              ✕ Remove project
            </button>
          )}
          {projects.length === 0 ? (
            <div style={{ padding: '8px 12px', color: '#334155', fontSize: 12 }}>No projects yet — create one in Goals</div>
          ) : (
            projects.map(p => (
              <button key={p.id} onClick={() => assign(p.id)}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 8, border: 'none', background: tx.project_id === p.id ? '#1e2030' : 'transparent', color: tx.project_id === p.id ? '#8b5cf6' : '#94a3b8', fontSize: 12, cursor: 'pointer', fontFamily: F }}>
                📁 {p.name}
                {tx.project_id === p.id && <span style={{ float: 'right', color: '#8b5cf6' }}>✓</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default function Transactions() {
  const [txs, setTxs] = useState([])
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [editRow, setEditRow] = useState({})
  const [filterCat, setFilterCat] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('category') || 'all'
  })
  const [filterAcct, setFilterAcct] = useState('all')
  const [filterMonth, setFilterMonth] = useState('all')
  const [filterProject, setFilterProject] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // Sync filterCat to URL (?category=...) so filter state is shareable
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (filterCat === 'all') {
      params.delete('category')
    } else {
      params.set('category', filterCat)
    }
    const newSearch = params.toString()
    const newUrl = newSearch ? `${window.location.pathname}?${newSearch}` : window.location.pathname
    window.history.replaceState({}, '', newUrl)
  }, [filterCat])
  const PER_PAGE = 25

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/transactions`).then(r => r.json()).catch(() => []),
      fetch(`${API_URL}/projects`).then(r => r.json()).catch(() => []),
    ]).then(([t, p]) => {
      setTxs(Array.isArray(t) ? t : [])
      setProjects(Array.isArray(p) ? p : [])
      setLoading(false)
    })
  }, [])

  const accounts = useMemo(() => [...new Set(txs.map(t => t.bank_source).filter(Boolean))], [txs])
  const months = useMemo(() => [...new Set(txs.map(t => t.transaction_date?.slice(0,7)).filter(Boolean))].sort().reverse(), [txs])
  const allCats = useMemo(() => [...new Set([...DEFAULT_CATEGORIES, ...txs.map(t => t.category).filter(Boolean)])], [txs])

  const filtered = useMemo(() => txs.filter(t => {
    if (filterCat !== 'all' && t.category !== filterCat) return false
    if (filterAcct !== 'all' && t.bank_source !== filterAcct) return false
    if (filterMonth !== 'all' && !t.transaction_date?.startsWith(filterMonth)) return false
    if (filterProject !== 'all') {
      if (filterProject === 'tagged' && !t.project_id) return false
      if (filterProject === 'untagged' && t.project_id) return false
      if (filterProject !== 'tagged' && filterProject !== 'untagged' && t.project_id !== parseInt(filterProject)) return false
    }
    if (search && !t.description?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  }), [txs, filterCat, filterAcct, filterMonth, filterProject, search])

  const paginated = filtered.slice((page-1)*PER_PAGE, page*PER_PAGE)
  const totalPages = Math.ceil(filtered.length/PER_PAGE)

  const handleAssignProject = (txId, projectId) => {
    setTxs(p => p.map(t => t.id === txId ? {...t, project_id: projectId} : t))
  }

  const saveEdit = async id => {
    try {
      await fetch(`${API_URL}/transactions/${id}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          transaction_date: editRow.transaction_date,
          description: editRow.description,
          amount: parseFloat(editRow.amount),
          category: editRow.category,
          notes: editRow.notes,
        })
      })
      setTxs(p => p.map(t => t.id===id ? {...t,...editRow, amount:parseFloat(editRow.amount)} : t))
    } catch {}
    setEditingId(null)
  }

  const updateCategory = async (id, category) => {
    setTxs(p => p.map(t => t.id===id ? {...t, category} : t))
    await fetch(`${API_URL}/transactions/${id}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category})
    }).catch(() => {})
  }

  const updateNotes = async (id, notes) => {
    setTxs(p => p.map(t => t.id===id ? {...t, notes} : t))
    await fetch(`${API_URL}/transactions/${id}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({notes})
    }).catch(() => {})
  }

  const taggedCount = txs.filter(t => t.project_id).length

  const S = {
    page: { padding: '32px 40px 64px', maxWidth: 1300, margin: '0 auto', fontFamily: F, background: '#080b0f', minHeight: '100vh' },
    card: { background: '#0f1117', border: '1px solid #1e2030', borderRadius: 16 },
    input: { background: '#0a0d12', border: '1px solid #1e2030', borderRadius: 10, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: F },
    select: { background: '#0a0d12', border: '1px solid #1e2030', borderRadius: 10, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: F, cursor: 'pointer' },
    th: { padding: '10px 14px', color: '#283244', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', textAlign: 'left', borderBottom: '1px solid #0f1117', whiteSpace: 'nowrap' },
    td: { padding: '11px 14px', borderBottom: '1px solid #0a0d12', verticalAlign: 'middle' },
    editInput: { background: '#0a0d12', border: '1px solid #3b82f6', borderRadius: 7, padding: '5px 8px', color: '#fff', fontSize: 12, outline: 'none', fontFamily: F, width: '100%' },
  }

  if (loading) return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'60vh',fontFamily:F}}>
      <p style={{color:'#475569'}}>Loading transactions…</p>
    </div>
  )

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:24 }}>
        <div>
          <h1 style={{ fontSize:26, fontWeight:800, color:'#f1f5f9', letterSpacing:'-0.5px', marginBottom:6 }}>Transactions</h1>
          <p style={{ color:'#475569', fontSize:13 }}>
            {filtered.length} of {txs.length} transactions
            {taggedCount > 0 && <span style={{ color:'#8b5cf6', marginLeft:8 }}>· {taggedCount} tagged to projects</span>}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display:'flex', gap:10, marginBottom:20, flexWrap:'wrap' }}>
        <input placeholder="Search descriptions…" value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          style={{ ...S.input, minWidth:200, flex:1 }}/>

        <select value={filterMonth} onChange={e => { setFilterMonth(e.target.value); setPage(1) }} style={S.select}>
          <option value="all">All months</option>
          {months.map(m => <option key={m} value={m}>{new Date(m+'-02').toLocaleDateString('en-US',{month:'long',year:'numeric'})}</option>)}
        </select>

        <select value={filterCat} onChange={e => { setFilterCat(e.target.value); setPage(1) }} style={S.select}>
          <option value="all">All categories</option>
          {allCats.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {accounts.length > 1 && (
          <select value={filterAcct} onChange={e => { setFilterAcct(e.target.value); setPage(1) }} style={S.select}>
            <option value="all">All accounts</option>
            {accounts.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        )}

        {projects.length > 0 && (
          <select value={filterProject} onChange={e => { setFilterProject(e.target.value); setPage(1) }} style={S.select}>
            <option value="all">All projects</option>
            <option value="tagged">Tagged only</option>
            <option value="untagged">Untagged only</option>
            {projects.map(p => <option key={p.id} value={p.id}>📁 {p.name}</option>)}
          </select>
        )}
      </div>

      {/* Table */}
      <div style={S.card}>
        <div style={{ overflowX:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', minWidth:900 }}>
            <thead>
              <tr style={{ background:'#0a0d12' }}>
                <th style={S.th}>Date</th>
                <th style={S.th}>Description</th>
                <th style={{ ...S.th, textAlign:'right' }}>Amount</th>
                <th style={S.th}>Category</th>
                <th style={S.th}>Project</th>
                <th style={S.th}>Account</th>
                <th style={S.th}>Notes</th>
                <th style={S.th}></th>
              </tr>
            </thead>
            <tbody>
              {paginated.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ ...S.td, textAlign:'center', padding:'48px', color:'#334155' }}>
                    No transactions match your filters
                  </td>
                </tr>
              ) : paginated.map(tx => {
                const isEditing = editingId === tx.id
                const isExp = tx.transaction_type === 'expense'
                const amtColor = tx.amount >= 0 ? '#10b981' : isExp ? '#ef4444' : '#64748b'

                return (
                  <tr key={tx.id}
                    style={{ borderBottom:'1px solid #0a0d12', transition:'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.background='#0f1117'}
                    onMouseLeave={e => e.currentTarget.style.background='transparent'}>

                    {/* Date */}
                    <td style={{ ...S.td, color:'#334155', fontSize:12, whiteSpace:'nowrap' }}>
                      {isEditing
                        ? <input type="date" style={{...S.editInput, width:120}} value={editRow.transaction_date} onChange={e => setEditRow({...editRow, transaction_date:e.target.value})}/>
                        : tx.transaction_date}
                    </td>

                    {/* Description */}
                    <td style={{ ...S.td, maxWidth:260 }}>
                      {isEditing
                        ? <input style={S.editInput} value={editRow.description} onChange={e => setEditRow({...editRow, description:e.target.value})}/>
                        : (
                          <div>
                            <div style={{ color:'#e2e8f0', fontSize:13, fontWeight:500, marginBottom:2 }}>{tx.description}</div>
                            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                              {tx.is_fixed && <span style={{ fontSize:9, color:'#475569', background:'#151720', padding:'1px 6px', borderRadius:4, fontWeight:600 }}>FIXED</span>}
                              {tx.needs_review && <span style={{ fontSize:9, color:'#f59e0b', background:'rgba(245,158,11,0.1)', padding:'1px 6px', borderRadius:4 }}>REVIEW</span>}
                              {tx.transaction_type === 'loan_payment' && !tx.is_extra_payment && (
                                <button onClick={async e => {
                                  e.stopPropagation()
                                  await fetch(`${API_URL}/transactions/${tx.id}`, {
                                    method:'PATCH', headers:{'Content-Type':'application/json'},
                                    body: JSON.stringify({notes: 'extra_payment'})
                                  })
                                  setTxs(p => p.map(t => t.id===tx.id ? {...t, is_extra_payment:true} : t))
                                }} style={{ fontSize:9, color:'#10b981', background:'rgba(16,185,129,0.08)', border:'1px solid rgba(16,185,129,0.2)', padding:'1px 7px', borderRadius:4, cursor:'pointer', fontFamily:F }}>
                                  Extra payment?
                                </button>
                              )}
                              {tx.is_extra_payment && <span style={{ fontSize:9, color:'#10b981', background:'rgba(16,185,129,0.08)', padding:'1px 6px', borderRadius:4 }}>EXTRA PMT</span>}
                            </div>
                          </div>
                        )}
                    </td>

                    {/* Amount */}
                    <td style={{ ...S.td, textAlign:'right', whiteSpace:'nowrap' }}>
                      {isEditing
                        ? <input type="number" style={{...S.editInput, width:90, textAlign:'right'}} value={editRow.amount} onChange={e => setEditRow({...editRow, amount:e.target.value})}/>
                        : <div style={{ textAlign:'right' }}>
                            <span style={{ color:amtColor, fontWeight:700, fontSize:14, fontFamily:'monospace' }}>
                              {tx.credit_applied > 0 ? '-$'+tx.net_amount.toFixed(2) : fmtAmt(tx.amount)}
                            </span>
                            {tx.credit_applied > 0 && (
                              <div style={{ fontSize:10, color:'#10b981', marginTop:2 }}>
                                ✓ ${tx.credit_applied.toFixed(2)} credit applied
                              </div>
                            )}
                            {tx.credit_applied > 0 && (
                              <div style={{ fontSize:10, color:'#475569', textDecoration:'line-through' }}>
                                {fmtAmt(tx.amount)}
                              </div>
                            )}
                          </div>}
                    </td>

                    {/* Category */}
                    <td style={S.td}>
                      {isEditing
                        ? <select style={{...S.editInput, width:140}} value={editRow.category} onChange={e => setEditRow({...editRow, category:e.target.value})}>
                            {allCats.map(c => <option key={c}>{c}</option>)}
                          </select>
                        : <select value={tx.category||'Other'}
                            onChange={e => updateCategory(tx.id, e.target.value)}
                            style={{ background:'#151720', border:'1px solid #1e2030', borderRadius:7, padding:'4px 8px', color:'#64748b', fontSize:11, outline:'none', fontFamily:F, cursor:'pointer' }}>
                            {allCats.map(c => <option key={c}>{c}</option>)}
                          </select>}
                    </td>

                    {/* Project */}
                    <td style={S.td}>
                      {!isEditing && tx.transaction_type === 'expense' && (
                        <ProjectDropdown tx={tx} projects={projects} onAssign={handleAssignProject}/>
                      )}
                    </td>

                    {/* Account */}
                    <td style={{ ...S.td, color:'#334155', fontSize:12, whiteSpace:'nowrap' }}>
                      {tx.bank_source}
                    </td>

                    {/* Notes */}
                    <td style={{ ...S.td, minWidth:120 }}>
                      {isEditing
                        ? <input style={S.editInput} placeholder="Note…" value={editRow.notes||''} onChange={e => setEditRow({...editRow, notes:e.target.value})}/>
                        : <input placeholder="Add note…" defaultValue={tx.notes||''}
                            onBlur={e => { if(e.target.value !== (tx.notes||'')) updateNotes(tx.id, e.target.value) }}
                            style={{ background:'none', border:'none', color:'#334155', fontSize:12, outline:'none', fontFamily:F, width:'100%', cursor:'text' }}/>}
                    </td>

                    {/* Actions */}
                    <td style={{ ...S.td, whiteSpace:'nowrap' }}>
                      {isEditing ? (
                        <div style={{ display:'flex', gap:6 }}>
                          <button onClick={() => saveEdit(tx.id)}
                            style={{ background:'#10b981', color:'#fff', border:'none', borderRadius:7, padding:'5px 12px', fontSize:11, cursor:'pointer', fontWeight:700, fontFamily:F }}>Save</button>
                          <button onClick={() => setEditingId(null)}
                            style={{ background:'none', border:'1px solid #1e2030', borderRadius:7, padding:'5px 10px', fontSize:11, cursor:'pointer', color:'#475569', fontFamily:F }}>✕</button>
                        </div>
                      ) : (
                        <button onClick={() => { setEditingId(tx.id); setEditRow({ transaction_date:tx.transaction_date||'', description:tx.description||'', amount:tx.amount||0, category:tx.category||'Other', notes:tx.notes||'' }) }}
                          style={{ background:'none', border:'1px solid #1e2030', borderRadius:7, padding:'4px 10px', fontSize:11, cursor:'pointer', color:'#475569', fontFamily:F }}>
                          Edit
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 20px', borderTop:'1px solid #0f1117' }}>
            <span style={{ color:'#334155', fontSize:12 }}>
              {(page-1)*PER_PAGE+1}–{Math.min(page*PER_PAGE, filtered.length)} of {filtered.length}
            </span>
            <div style={{ display:'flex', gap:6 }}>
              <button onClick={() => setPage(p => Math.max(1,p-1))} disabled={page===1}
                style={{ background:'none', border:'1px solid #1e2030', borderRadius:8, padding:'6px 14px', fontSize:12, cursor:page===1?'not-allowed':'pointer', color:page===1?'#283244':'#64748b', fontFamily:F }}>← Prev</button>
              {Array.from({length:Math.min(5,totalPages)},(_,i)=>{
                let p = page <= 3 ? i+1 : page+i-2
                if (p > totalPages) return null
                return <button key={p} onClick={() => setPage(p)}
                  style={{ background:p===page?'#2563eb':'none', border:`1px solid ${p===page?'#2563eb':'#1e2030'}`, borderRadius:8, padding:'6px 12px', fontSize:12, cursor:'pointer', color:p===page?'#fff':'#64748b', fontFamily:F }}>{p}</button>
              })}
              <button onClick={() => setPage(p => Math.min(totalPages,p+1))} disabled={page===totalPages}
                style={{ background:'none', border:'1px solid #1e2030', borderRadius:8, padding:'6px 14px', fontSize:12, cursor:page===totalPages?'not-allowed':'pointer', color:page===totalPages?'#283244':'#64748b', fontFamily:F }}>Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
