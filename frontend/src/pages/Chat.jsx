import { useState, useRef, useEffect } from 'react'
import { API_URL } from '../lib/config'

const suggestions = [
  'Where is most of my money going?',
  'Why did I overspend this month?',
  'How can I save more?',
  'What are my biggest expenses?',
]

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: "Hi, I'm xspend. I've analysed your transactions and I'm ready to help. Ask me anything about your spending." }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (msg) => {
    const text = msg || input
    if (!text.trim() || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      })
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.success ? data.response : `Error: ${data.error}`
      }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', text: 'Could not connect to backend.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-[#1a1a1a] mb-1">AI Chat</h1>
        <p className="text-[#5a5a5a] text-sm">Ask anything about your finances</p>
      </div>

      <div style={{border:'1px solid #1a1a28'}} className="bg-[#12121e] rounded-xl flex flex-col h-[520px]">
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-lg bg-blue-500 flex items-center justify-center text-white text-xs font-bold mr-2 mt-1 flex-shrink-0">x</div>
              )}
              <div className={`max-w-md px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-[#1a1a28] text-[#e0e0eb]'
              }`}>
                {msg.text}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex items-start gap-2">
              <div className="w-7 h-7 rounded-lg bg-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">x</div>
              <div style={{border:'1px solid #2a2a3a'}} className="bg-[#1a1a28] px-4 py-3 rounded-xl text-sm text-[#b8b8c8]">
                Analysing...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{borderTop:'1px solid #1a1a28'}} className="p-4">
          <div className="flex gap-2 mb-3 flex-wrap">
            {suggestions.map(s => (
              <button
                key={s}
                onClick={() => send(s)}
                className="text-xs text-[#b8b8c8] hover:text-white bg-[#1a1a28] hover:bg-[#2a2a3a] px-3 py-1.5 rounded-lg transition-all border border-[#2a2a3a]"
              >
                {s}
              </button>
            ))}
          </div>
          <div style={{border:'1px solid #2a2a3a'}} className="flex gap-2 bg-[#1a1a28] rounded-xl px-4 py-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Ask about your finances..."
              className="flex-1 bg-transparent text-white text-sm outline-none placeholder-[#8a8a9a]"
            />
            <button
              onClick={() => send()}
              disabled={loading || !input.trim()}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-[#2a2a3a] disabled:cursor-not-allowed text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
