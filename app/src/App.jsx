import { useEffect, useRef, useState, useCallback } from 'react'

const BACKEND = 'http://127.0.0.1:8765'

/* ---------- Particle Sphere ---------- */
function useParticleSphere(canvasRef, speaking, listening, audioLevel) {
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: true })
    let raf = 0
    let t = 0

    const resize = () => {
      canvas.width = canvas.clientWidth * window.devicePixelRatio
      canvas.height = canvas.clientHeight * window.devicePixelRatio
    }
    resize()
    window.addEventListener('resize', resize)

    const N = 2100
    const particles = Array.from({length: N}, () => {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      return { theta, phi, r: 1, wob: Math.random() * Math.PI * 2, sp: 0.6 + Math.random() * 0.8 }
    })

    const draw = () => {
      t += 0.012
      const W = canvas.width, H = canvas.height
      ctx.clearRect(0, 0, W, H)
      const cx = W/2, cy = H/2
      const baseR = Math.min(W, H) * 0.28

      const grd = ctx.createRadialGradient(cx, cy, baseR*0.4, cx, cy, baseR*1.6)
      grd.addColorStop(0, 'rgba(0,230,255,0.035)')
      grd.addColorStop(1, 'rgba(0,230,255,0)')
      ctx.fillStyle = grd
      ctx.fillRect(0,0,W,H)

      const speakBoost = speaking ? 0.18 + audioLevel * 0.35 : 0
      const listenBoost = listening ? 0.08 : 0

      particles.forEach(p => {
        p.theta += 0.0026 * p.sp
        p.phi += 0.0011 * p.sp

        const wob = Math.sin(t * 1.7 + p.wob) * (0.035 + speakBoost * 0.6)
        const r = baseR * (1 + wob + listenBoost)

        const x = Math.sin(p.phi) * Math.cos(p.theta)
        const y = Math.sin(p.phi) * Math.sin(p.theta)
        const z = Math.cos(p.phi)

        const rotY = t * 0.28
        const rx = x * Math.cos(rotY) - z * Math.sin(rotY)
        const rz = x * Math.sin(rotY) + z * Math.cos(rotY)
        const ry = y

        const scale = 320 / (320 + rz * 120)
        const px = cx + rx * r * scale
        const py = cy + ry * r * scale

        const depth = (rz + 1) * 0.5
        const size = (0.9 + depth * 1.9) * window.devicePixelRatio
        const alpha = 0.35 + depth * 0.75 + speakBoost

        ctx.beginPath()
        ctx.arc(px, py, size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${20 + depth*40}, ${235 + depth*20}, 255, ${alpha})`
        ctx.shadowColor = '#00e5ff'
        ctx.shadowBlur = depth > 0.5 ? 7 * window.devicePixelRatio : 0
        ctx.fill()
        ctx.shadowBlur = 0
      })

      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [speaking, listening, audioLevel, canvasRef])
}

/* ---------- App ---------- */
export default function App() {
  const canvasRef    = useRef(null)
  const chatEndRef   = useRef(null)   // scroll anchor at bottom of chat
  const transcriptRef = useRef(null)  // the scrollable panel itself
  const userScrolledRef = useRef(false) // true if user scrolled up manually

  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking]   = useState(false)
  const [speakWord, setSpeakWord] = useState('')
  const [audioLevel, setAudioLevel] = useState(0.15)

  const [msgs, setMsgs]       = useState([{ who: 'JARVIS', text: '…' }])
  const [input, setInput]     = useState('')
  const [showHud, setShowHud] = useState(true)
  const [showDock, setShowDock] = useState(true)

  const [research, setResearch] = useState({
    active: false, topic: '', queries: 0, sources: 0,
    progress: 0, depth: '0 / 0', current_query: ''
  })

  const wsRef = useRef(null)

  // ── Audio queue ───────────────────────────────────────────────────────────
  const audioQueueRef   = useRef([])
  const isPlayingRef    = useRef(false)
  const currentAudioRef = useRef(null)

  useParticleSphere(canvasRef, speaking, listening, audioLevel)

  useEffect(() => {
    if (!speaking) { setAudioLevel(0.12); return }
    const id = setInterval(() => setAudioLevel(0.18 + Math.random()*0.45), 80)
    return () => clearInterval(id)
  }, [speaking])

  /* ---------- Auto-scroll: stick to bottom unless user scrolled up ---------- */
  useEffect(() => {
    const panel = transcriptRef.current
    if (!panel) return
    if (!userScrolledRef.current) {
      panel.scrollTop = panel.scrollHeight
    }
  }, [msgs])

  /* Track whether user manually scrolled up */
  const handlePanelScroll = useCallback(() => {
    const panel = transcriptRef.current
    if (!panel) return
    const atBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 40
    userScrolledRef.current = !atBottom
  }, [])

  /* ---------- Audio helpers ---------- */
  const resolveAudioUrl = useCallback((pathOrUrl) => {
    const normalized = (pathOrUrl || '').replace(/\\/g, '/')
    if (normalized.startsWith('http')) return normalized
    if (normalized.startsWith('/audio/')) return `${BACKEND}${normalized}`
    return `${BACKEND}/audio/${normalized.split('/').pop()}`
  }, [])

  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false
      currentAudioRef.current = null
      return
    }
    const url = audioQueueRef.current.shift()
    isPlayingRef.current = true
    const audio = new Audio(url)
    currentAudioRef.current = audio
    audio.onended = () => { currentAudioRef.current = null; playNextInQueue() }
    audio.onerror = () => { currentAudioRef.current = null; playNextInQueue() }
    audio.play().catch(() => { currentAudioRef.current = null; playNextInQueue() })
  }, [])

  const enqueueTtsAudio = useCallback((pathOrUrl) => {
    audioQueueRef.current.push(resolveAudioUrl(pathOrUrl))
    if (!isPlayingRef.current) playNextInQueue()
  }, [resolveAudioUrl, playNextInQueue])

  const stopAndClearAudio = useCallback(() => {
    audioQueueRef.current = []
    isPlayingRef.current = false
    if (currentAudioRef.current) {
      try { currentAudioRef.current.pause(); currentAudioRef.current.src = '' } catch (_) {}
      currentAudioRef.current = null
    }
  }, [])

  /* ---------- Startup ---------- */
  useEffect(() => {
    Promise.all([
      fetch(BACKEND + '/health').then(r => r.json()).catch(() => null),
      fetch(BACKEND + '/greeting').then(r => r.json()).catch(() => null),
    ]).then(([health, greet]) => {
      if (!health) {
        setMsgs([{ who: 'JARVIS', text: '❌ Backend offline. Run: python main.py in the backend folder.' }])
        return
      }
      const greetText = greet?.greeting || 'Neural interface online. Always at your service.'
      setMsgs([{ who: 'JARVIS', text: greetText }])
      if (!health.ollama?.connected) {
        setMsgs(m => [...m, { who: 'JARVIS', text: '⚠️ Ollama not connected. Run: ollama serve' }])
      }
      if (greet?.greeting) {
        fetch(BACKEND + '/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: greet.greeting })
        })
          .then(r => r.json())
          .then(d => { if (d.ok && d.audio_url) enqueueTtsAudio(d.audio_url) })
          .catch(() => {})
      }
    })
  }, [enqueueTtsAudio])

  /* ---------- WebSocket ---------- */
  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(BACKEND.replace('http','ws') + '/ws')
        wsRef.current = ws

        ws.onmessage = (e) => {
          const d = JSON.parse(e.data)

          if (d.type === 'delta') {
            setSpeaking(true)
            const words = d.text.trim().split(/\s+/)
            const last = words[words.length-1]?.replace(/[^A-Za-z0-9]/g,'').toUpperCase()
            if (last && last.length > 1 && last.length < 16) {
              setSpeakWord(last)
              setTimeout(()=>setSpeakWord(''), 520)
            }
            // reset scroll-lock so new output auto-scrolls
            userScrolledRef.current = false
            setMsgs(m => {
              const copy = [...m]
              const lastMsg = copy[copy.length-1]
              if (lastMsg && lastMsg.who === 'JARVIS' && lastMsg.streaming) {
                lastMsg.text += d.text
              } else {
                copy.push({ who: 'JARVIS', text: d.text, streaming: true })
              }
              return copy
            })

          } else if (d.type === 'tts_start') {
            stopAndClearAudio()

          } else if (d.type === 'tts' || d.type === 'tts_sentence') {
            const src = d.url || d.path
            if (src) enqueueTtsAudio(src)

          } else if (d.type === 'wake_word') {
            setListening(true)
            setMsgs(m => [...m, { who: 'JARVIS', text: `🎙️ Wake word detected${d.heard ? `: ${d.heard}` : ''}` }])

          } else if (d.type === 'stt_result') {
            setListening(false)
            if (d.ok && d.text?.trim()) {
              send(d.text.trim())
            } else {
              setMsgs(m => [...m, { who: 'JARVIS', text: `⚠️ STT: ${d.error || 'No speech detected'}` }])
            }

          } else if (d.type === 'tool') {
            const isDeepResearch = d.name === 'deep_research'
            setResearch(r => ({
              active: true,
              topic: d.args?.topic || d.args?.query || r.topic || 'autonomous task',
              queries: isDeepResearch ? 0 : r.queries + 1,
              sources: r.sources,
              progress: isDeepResearch ? 5 : Math.min(96, r.progress + 12),
              depth: r.depth,
              current_query: d.args?.topic || d.args?.query || ''
            }))

          } else if (d.type === 'research_progress') {
            setResearch({
              active: true, topic: d.topic || 'deep research',
              queries: d.queries || 0, sources: d.sources || 0,
              progress: d.progress || 0, depth: `${d.queries || 0} / 14`,
              current_query: d.current_query || ''
            })

          } else if (d.type === 'interrupted') {
            stopAndClearAudio()
            setSpeaking(false)
            setSpeakWord('')

          } else if (d.type === 'done') {
            setSpeaking(false)
            setSpeakWord('')
            setMsgs(m => m.map(x => ({...x, streaming:false})))
            setResearch(r => r.active ? { ...r, progress: 100 } : r)
            setTimeout(()=> setResearch(r => r.progress >= 100
              ? {active:false, topic:'', queries:0, sources:0, progress:0, depth:'0 / 0', current_query:''}
              : r), 2200)
          }
        }

        ws.onclose = () => setTimeout(connect, 1800)
      } catch {}
    }
    connect()
    return () => wsRef.current?.close()
  }, [enqueueTtsAudio, stopAndClearAudio])

  const send = (text) => {
    if (!text.trim()) return
    userScrolledRef.current = false   // auto-scroll when user sends
    setMsgs(m => [...m, { who: 'YOU', text }])
    setSpeaking(false)
    stopAndClearAudio()
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', text }))
    } else {
      fetch(BACKEND + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      })
        .then(r => r.json())
        .then(j => { setMsgs(m => [...m, { who: 'JARVIS', text: j.reply || '(backend offline)' }]); setSpeaking(false) })
        .catch(() => setSpeaking(false))
    }
  }

  /* ---------- Push-to-Talk ---------- */
  const startPTT = useCallback(() => {
    if (listening) return
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      setMsgs(m => [...m, { who: 'JARVIS', text: '⚠️ WebSocket not connected.' }])
      return
    }
    setListening(true)
    wsRef.current.send(JSON.stringify({ type: 'transcribe_mic_start' }))
  }, [listening])

  const stopPTT = useCallback(() => {
    if (!listening) return
    wsRef.current?.send(JSON.stringify({ type: 'transcribe_mic_stop' }))
  }, [listening])

  /* ---------- Keys ---------- */
  useEffect(() => {
    const down = (e) => {
      if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT' && !e.repeat) {
        e.preventDefault(); startPTT()
      }
      if (e.code === 'Tab') { e.preventDefault(); setShowHud(h => !h) }
      if (e.code === 'Backquote') { setShowDock(d => !d) }
      if (e.code === 'Escape') {
        stopAndClearAudio(); setSpeaking(false); setListening(false)
        wsRef.current?.send(JSON.stringify({ type: 'interrupt' }))
      }
    }
    const up = (e) => {
      if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault(); stopPTT()
      }
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
  }, [startPTT, stopPTT, stopAndClearAudio])

  return (
    <>
      <div className="neural-header">
        <div>J.A.R.V.I.S. &nbsp;|&nbsp; NEURAL INTERFACE</div>
        <div className="center">MANINA LABS EDITION</div>
        <div className="right">
          <span className="live-pulse"></span> ALWAYS LISTENING
          <div className="win-btns">
            <button onClick={()=>window.jarvis?.min()}>—</button>
            <button onClick={()=>window.jarvis?.max()}>□</button>
            <button onClick={()=>window.jarvis?.close()}>✕</button>
          </div>
        </div>
      </div>

      <div className="stage">
        <canvas id="particleCanvas" ref={canvasRef} style={{width:'100%',height:'100%'}} />
        <div className="mic-ring" style={{opacity: listening ? 1 : 0}} />

        <div className="speak-word-wrap">
          <div className="speak-word">{speakWord}</div>
        </div>

        <div className={`side-hud ${showHud ? '' : 'hidden'}`} style={{right:'34px'}}>
          {research.active && (
            <div className="hud-card" style={{borderColor:'rgba(0,229,255,0.32)'}}>
              <h4>Deep Research</h4>
              <div style={{color:'#7fdfff', marginBottom:8, lineHeight:1.5}}>{research.topic || 'autonomous task'}</div>
              <div style={{height:5, background:'rgba(0,229,255,0.12)', borderRadius:4, overflow:'hidden', marginBottom:10}}>
                <div style={{width:`${research.progress}%`, height:'100%', background:'#00e5ff', boxShadow:'0 0 12px rgba(0,229,255,.7)', transition:'width .3s'}}/>
              </div>
              <div className="tool-row"><span>QUERIES</span><span>{research.queries}</span></div>
              <div className="tool-row"><span>SOURCES</span><span>{research.sources}</span></div>
              <div className="tool-row"><span>DEPTH</span><span>{research.depth}</span></div>
              <div className="tool-row"><span>STATUS</span><span style={{color:'#00e5ff'}}>ANALYZING</span></div>
            </div>
          )}
          <div className="hud-card">
            <h4>System</h4>
            <div className="tool-row"><span>STT</span><span>Whisper</span></div>
            <div className="tool-row"><span>LLM</span><span>Ollama</span></div>
            <div className="tool-row"><span>TTS</span><span>SAPI</span></div>
            <div className="tool-row"><span>MEM</span><span>ChromaDB</span></div>
            <div className="tool-row"><span>MODE</span><span style={{color: listening ? '#00e5ff' : speaking ? '#ffca5f' : '#4a8a99'}}>{listening ? 'LISTEN' : speaking ? 'SPEAK' : 'IDLE'}</span></div>
          </div>
        </div>

        {/* Scrollable chat transcript — top left */}
        <div
          className="transcript-bar"
          ref={transcriptRef}
          onScroll={handlePanelScroll}
          style={{opacity: showHud ? 1 : 0.35}}
        >
          <div className="spacer" />
          {msgs.map((m, i) => (
            <div key={i} className="line">
              <span className={`who ${m.who === 'YOU' ? 'you' : ''}`}>
                {m.who === 'YOU' ? 'YOU >' : 'JARVIS >'}
              </span>
              {m.text}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        <div className="hint">
          <kbd>Space</kbd> talk &nbsp; <kbd>Esc</kbd> interrupt &nbsp; <kbd>Tab</kbd> HUD &nbsp; <kbd>`</kbd> dock
        </div>

        <div className={`dock ${showDock ? '' : 'hidden-dock'}`}>
          <input
            value={input}
            onChange={e=>setInput(e.target.value)}
            onKeyDown={e=>{ if(e.key==='Enter'){ send(input); setInput('') }}}
            placeholder="Type a command or hold Space to speak…"
            className="cmd-input"
          />
          <button className="send-btn" onClick={()=>{ send(input); setInput('') }}>SEND</button>
          <button
            className={`ptt-btn ${listening ? 'active' : ''}`}
            onMouseDown={startPTT} onMouseUp={stopPTT}
            onTouchStart={startPTT} onTouchEnd={stopPTT}
          >🎙</button>
        </div>
      </div>
    </>
  )
}
