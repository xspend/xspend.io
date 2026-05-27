#!/usr/bin/env python3
"""
Phase 2, Chunk 3 — drilldown expansion.

Adds:
- expandedCats state (Set) in Dashboard.jsx
- Toggle expansion on row click (multi-expand allowed)
- Drilldown panel: context line, insight, top 5 transactions, view-all link, soft limit
- Fade-in animation (~150ms opacity transition)
- Transactions.jsx: read ?category= from URL on mount, sync filter changes back

Run from project root:
    cd ~/Desktop/financeai
    python3 patches/phase2_chunk3_drilldown.py
"""

from pathlib import Path

ROOT = Path('/Users/dharanireddy/Desktop/financeai')
DASH = ROOT / 'frontend' / 'src' / 'pages' / 'Dashboard.jsx'
TXNS = ROOT / 'frontend' / 'src' / 'pages' / 'Transactions.jsx'

# ─────────────────────────────────────────────────────────────────────────────
# Edit 1: Transactions.jsx — read ?category= from URL on mount, sync changes
# ─────────────────────────────────────────────────────────────────────────────
with open(TXNS) as f:
    s_txns = f.read()

if "useState('all')" not in s_txns or 'filterCat' not in s_txns:
    print('ABORT — Transactions.jsx structure changed, anchors stale')
    raise SystemExit(1)

if 'window.location.search' in s_txns and 'category' in s_txns and 'URLSearchParams' in s_txns:
    print('  - Transactions.jsx URL filter already wired, skipping')
else:
    # Change initialization of filterCat to read from URL
    old_init = "  const [filterCat, setFilterCat] = useState('all')"
    new_init = """  const [filterCat, setFilterCat] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('category') || 'all'
  })"""

    if s_txns.count(old_init) != 1:
        print(f'ABORT — filterCat init anchor matched {s_txns.count(old_init)} times')
        raise SystemExit(1)

    s_txns = s_txns.replace(old_init, new_init, 1)

    # Add a useEffect to sync filterCat changes back to URL
    # Anchor: after the existing useState block (line 70-71 area)
    old_anchor = "  const [page, setPage] = useState(1)"
    new_anchor = """  const [page, setPage] = useState(1)

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
  }, [filterCat])"""

    if s_txns.count(old_anchor) != 1:
        print(f'ABORT — page useState anchor matched {s_txns.count(old_anchor)} times')
        raise SystemExit(1)

    s_txns = s_txns.replace(old_anchor, new_anchor, 1)

    with open(TXNS) as f_check:
        pass  # just to ensure we re-read fresh
    with open(TXNS, 'w') as f_out:
        f_out.write(s_txns)
    print('  ✓ Transactions.jsx: filterCat reads from + writes to URL')

# ─────────────────────────────────────────────────────────────────────────────
# Edit 2: Dashboard.jsx — add expandedCats state + drilldown
# ─────────────────────────────────────────────────────────────────────────────
with open(DASH) as f:
    s_dash = f.read()

if 'expandedCats' in s_dash:
    print('ABORT — Dashboard.jsx drilldown already applied')
    raise SystemExit(1)

# 2a: Add expandedCats state near the other useState calls
# Anchor: find a useState we can put it after. Looking for one near the top.
old_state_anchor = "  const [summary, setSummary] = useState(null)"
new_state_anchor = """  const [summary, setSummary] = useState(null)
  const [expandedCats, setExpandedCats] = useState(new Set())"""

if s_dash.count(old_state_anchor) != 1:
    print(f'ABORT — summary useState anchor matched {s_dash.count(old_state_anchor)} times')
    raise SystemExit(1)

s_dash = s_dash.replace(old_state_anchor, new_state_anchor, 1)
print('  ✓ Dashboard.jsx: added expandedCats state')

# 2b: Replace the inert onClick with the toggle handler + add drilldown JSX
# Anchor: the entire row block ending with the inert onClick
old_row_block = """                      onClick={() => { /* expansion lives in Chunk 3 */ }}
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
                      <span style={{fontSize:14,color:'#475569',textAlign:'center'}}>›</span>
                    </div>
                  )
                })}"""

new_row_block = """                      onClick={() => {
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
                            alert('Soft limits coming in Phase 4. We\\'ll let you set a gentle target without enforcement.')
                          }}
                        >
                          + Set a soft limit
                        </button>
                      </div>
                    )}
                  </React.Fragment>
                  )
                })}"""

if s_dash.count(old_row_block) != 1:
    print(f'ABORT — row block anchor matched {s_dash.count(old_row_block)} times')
    raise SystemExit(1)

s_dash = s_dash.replace(old_row_block, new_row_block, 1)
print('  ✓ Dashboard.jsx: wired onClick to toggle, added drilldown JSX')

# 2c: Wrap the row+drilldown in a React.Fragment since we now return 2 siblings
# The current key={c.name} is on the row div; with Fragment we need key on Fragment
old_div_open = """                  return (
                    <div
                      key={c.name}
                      style={{
                        display:'grid',
                        gridTemplateColumns:'28px 1fr 90px 180px 50px 20px',
                        gap:14,
                        alignItems:'center',
                        padding:'12px 8px',
                        borderRadius:10,
                        cursor:'pointer',
                        transition:'background 0.15s',
                      }}"""

new_div_open = """                  return (
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
                      }}"""

if s_dash.count(old_div_open) != 1:
    print(f'ABORT — div open anchor matched {s_dash.count(old_div_open)} times')
    raise SystemExit(1)

s_dash = s_dash.replace(old_div_open, new_div_open, 1)
print('  ✓ Dashboard.jsx: wrapped row+drilldown in React.Fragment')

# 2d: Ensure React is imported (it's needed for React.Fragment)
if 'import React' not in s_dash and "import { " in s_dash:
    # Check if React is part of a named import
    if 'from "react"' in s_dash or "from 'react'" in s_dash:
        # Add a default React import
        old_react_import = "import { useState, useEffect"
        if old_react_import in s_dash:
            s_dash = s_dash.replace(old_react_import, "import React, { useState, useEffect", 1)
            print('  ✓ Dashboard.jsx: added React default import')

# 2e: Add the @keyframes for fade-in animation
# Look for existing <style> block, or add inline
if 'xspendFadeIn' not in s_dash:
    # Try to inject into an existing style tag, otherwise add at top of component return
    # Simplest: add as a global style via a useEffect-mounted <style> element
    # Even simpler: just rely on the opacity transition without keyframes
    # Switch the animation to use transition instead of keyframes
    s_dash = s_dash.replace(
        "animation:'xspendFadeIn 150ms ease-out',",
        "animation:'xspendFadeIn 150ms ease-out forwards',"
    )
    # Find a good spot to add @keyframes — top of the return, as a <style> child
    # Look for the outermost return
    style_inject_anchor = "  return ("
    if s_dash.count(style_inject_anchor) >= 1:
        # Add via a <style> tag right after the outermost return's opening
        # We need to be careful — only inject if not already present
        # Look for the outermost <div> in the dashboard component
        outermost = "  return (\n    <div"
        if outermost in s_dash:
            s_dash = s_dash.replace(
                outermost,
                "  return (\n    <>\n      <style>{`@keyframes xspendFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }`}</style>\n    <div",
                1
            )
            # Need to close the fragment at the end
            # Find the matching </div> + ) — heuristic: very last "  )"
            # Better: find the last </div> before the function's closing brace
            import re as _re
            # Find the LAST occurrence of '</div>\n  )' pattern
            match = _re.search(r'(</div>)(\s*\n\s*\)\s*\n\}\s*$)', s_dash)
            if match:
                s_dash = s_dash[:match.start(2)] + '\n    </>' + match.group(2)
                print('  ✓ Dashboard.jsx: added fade-in keyframes via fragment wrapper')
            else:
                print('  ! Could not find fragment close point — animation may not fade')

with open(DASH, 'w') as f:
    f.write(s_dash)

print()
print('Done. Vite should hot-reload.')
print('Click a category row in the dashboard to expand. Click again to collapse.')
