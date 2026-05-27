import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { API_URL } from '../lib/config'

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const name = localStorage.getItem('user_name') || 'You'
  const isActive = (path) => location.pathname.startsWith(path)
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [chatHistory, setChatHistory] = useState([])
  const [chatLoading, setChatLoading] = useState(false)

  const handleProfileClick = () => navigate('/onboarding')

  const sendChat = async () => {
    if (!chatMsg.trim()) return
    const userMsg = chatMsg.trim()
    setChatMsg('')
    setChatHistory(h => [...h, {role:'user', text:userMsg}])
    setChatLoading(true)
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message: userMsg})
      })
      const data = await res.json()
      setChatHistory(h => [...h, {role:'ai', text:data.response||data.reply||'Sorry, something went wrong.'}])
    } catch {
      setChatHistory(h => [...h, {role:'ai', text:'Could not connect to AI. Make sure the backend is running.'}])
    }
    setChatLoading(false)
  }

  const S = {
    nav: { background:'#12121e', borderBottom:'1px solid #1e1e2e', padding:'0 32px', display:'flex', alignItems:'center', justifyContent:'space-between', height:52, fontFamily:'DM Sans, Inter, sans-serif', position:'sticky', top:0, zIndex:100 },
    logo: { display:'flex', alignItems:'center', gap:10, textDecoration:'none' },
    logoBox: { width:32, height:32, borderRadius:9, background:'linear-gradient(135deg,#2563eb,#1d4ed8)', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:800, fontSize:14 },
    logoText: { color:'#fff', fontWeight:700, fontSize:15 },
    navLinks: { display:'flex', alignItems:'center', gap:4 },
    navLink: (active) => ({ padding:'6px 14px', borderRadius:8, textDecoration:'none', fontSize:13, fontWeight:500, color:active?'#fff':'#6a6a8a', background:active?'#2563eb':'transparent', transition:'all 0.15s' }),
    avatar: { width:32, height:32, borderRadius:'50%', background:'#2563eb', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:13, cursor:'pointer', border:'2px solid #1e1e2e' },
  }

  return (
    <>
      <nav style={S.nav}>
        <Link to="/" style={S.logo}>
          <div style={S.logoBox}>x</div>
          <span style={S.logoText}>xspend</span>
        </Link>

        <div style={S.navLinks}>
          <Link to="/app/upload" style={S.navLink(isActive('/app/upload'))}>📎 Upload</Link>
          <Link to="/app/dashboard" style={S.navLink(isActive('/app/dashboard'))}>📊 Dashboard</Link>
          <Link to="/app/transactions" style={S.navLink(isActive('/app/transactions'))}>📋 Transactions</Link>
          <Link to="/app/goals" style={S.navLink(isActive('/app/goals'))}>📁 Projects</Link>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <button onClick={handleProfileClick}
            style={{ background:'none', border:'1px solid #2a2a3a', borderRadius:8, padding:'5px 12px', fontSize:12, color:'#6a6a8a', cursor:'pointer', fontFamily:'inherit' }}>
            ⚙ Settings
          </button>
          <div style={S.avatar} onClick={handleProfileClick} title="Edit profile">
            {name.charAt(0).toUpperCase()}
          </div>
        </div>
      </nav>

      {/* Floating AI Chat */}
      <div style={{ position:'fixed', bottom:28, right:28, zIndex:500 }}>
        {chatOpen && (
          <div style={{ position:'absolute', bottom:'calc(100% + 12px)', right:0, width:340, background:'#0f1117', border:'1px solid #1e2030', borderRadius:20, boxShadow:'0 16px 48px rgba(0,0,0,0.6)', overflow:'hidden', fontFamily:'DM Sans, Inter, sans-serif' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 18px', borderBottom:'1px solid #1e2030', background:'#0a0d12' }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ fontSize:16 }}>💬</span>
                <span style={{ color:'#f1f5f9', fontSize:13, fontWeight:600 }}>AI Chat</span>
              </div>
              <button onClick={() => setChatOpen(false)} style={{ background:'none', border:'none', color:'#475569', cursor:'pointer', fontSize:16 }}>✕</button>
            </div>

            <div style={{ height:280, overflowY:'auto', padding:'14px 16px', display:'flex', flexDirection:'column', gap:10 }}>
              {chatHistory.length === 0 && (
                <div style={{ textAlign:'center', color:'#334155', fontSize:12, marginTop:40 }}>
                  <div style={{ fontSize:28, marginBottom:8 }}>💬</div>
                  Ask me anything about your spending
                </div>
              )}
              {chatHistory.map((m, i) => (
                <div key={i} style={{ display:'flex', justifyContent:m.role==='user'?'flex-end':'flex-start' }}>
                  <div style={{ maxWidth:'82%', padding:'9px 13px', borderRadius:m.role==='user'?'14px 14px 4px 14px':'14px 14px 14px 4px', background:m.role==='user'?'#2563eb':'#1e2030', color:'#e2e8f0', fontSize:12, lineHeight:1.5 }}>
                    {m.text}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div style={{ display:'flex', justifyContent:'flex-start' }}>
                  <div style={{ padding:'9px 13px', borderRadius:'14px 14px 14px 4px', background:'#1e2030', color:'#475569', fontSize:12 }}>Thinking…</div>
                </div>
              )}
            </div>

            <div style={{ padding:'12px 14px', borderTop:'1px solid #1e2030', display:'flex', gap:8 }}>
              <input value={chatMsg} onChange={e => setChatMsg(e.target.value)}
                onKeyDown={e => e.key==='Enter' && sendChat()}
                placeholder="Ask about your spending..."
                style={{ flex:1, background:'#0a0d12', border:'1px solid #1e2030', borderRadius:10, padding:'8px 12px', color:'#fff', fontSize:12, outline:'none', fontFamily:'inherit' }}/>
              <button onClick={sendChat} disabled={!chatMsg.trim()||chatLoading}
                style={{ background:'#2563eb', border:'none', borderRadius:10, padding:'8px 14px', color:'#fff', fontSize:12, cursor:'pointer', fontWeight:600, opacity:!chatMsg.trim()||chatLoading?0.5:1 }}>
                →
              </button>
            </div>
          </div>
        )}

        <button onClick={() => setChatOpen(o => !o)}
          style={{ width:52, height:52, borderRadius:'50%', background:'#2563eb', border:'none', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center', fontSize:22, boxShadow:'0 4px 20px rgba(37,99,235,0.4)', transition:'transform 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.transform='scale(1.08)'}
          onMouseLeave={e => e.currentTarget.style.transform='scale(1)'}>
          {chatOpen ? '✕' : '💬'}
        </button>
      </div>
    </>
  )
}
