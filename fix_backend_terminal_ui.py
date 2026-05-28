from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent

def write(path, content):
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content.strip() + '\n', encoding='utf-8')
    print(f'updated: {path}')

# Backend: prevent monitor endpoints from logging themselves forever
main_path = ROOT / 'backend/app/main.py'
main_text = main_path.read_text(encoding='utf-8')
main_text = main_text.replace('if request.url.path not in {"/system/events"}:', 'if request.url.path not in {"/system/events", "/system/health"}:')
pattern = r'@app\.get\("/system/health"\)\ndef system_health\(\):.*?\n\n@app\.get\("/db/status"\)'
replacement = '''@app.get("/system/health")
def system_health():
    # Silent snapshot endpoint used by the frontend terminal header.
    # It should not create log events, otherwise the terminal fills itself forever.
    db_status = get_db_status()
    ml_status = get_ml_status()
    llm_status = get_llm_status()

    return {
        "backend": "ok",
        "database": db_status,
        "ml": ml_status,
        "llm": llm_status,
        "event_count": len(get_events()),
    }


@app.get("/db/status")'''
new_text = re.sub(pattern, replacement, main_text, flags=re.DOTALL)
if new_text != main_text:
    main_path.write_text(new_text, encoding='utf-8')
    print('updated: backend/app/main.py')
else:
    main_path.write_text(main_text, encoding='utf-8')
    print('checked: backend/app/main.py')

write('frontend/src/components/TerminalPanel.jsx', '\nimport { useEffect, useRef, useState } from "react";\n\nimport { apiDelete, apiGet } from "../api/client";\n\nfunction formatTime(timestamp) {\n  if (!timestamp) return "";\n  return timestamp.replace("T", " ");\n}\n\nfunction formatData(data) {\n  if (!data || Object.keys(data).length === 0) return "";\n  return JSON.stringify(data, null, 2)\n    .split("\\n")\n    .map((line) => `    ${line}`)\n    .join("\\n");\n}\n\nfunction EventLine({ event }) {\n  const dataText = formatData(event.data);\n\n  return (\n    <div className="winTerminalLine">\n      <div>\n        <span className="winPrompt">PS backend&gt;</span>{" "}\n        <span className="winTime">[{formatTime(event.timestamp)}]</span>{" "}\n        <span className="winMeta">{event.level.toUpperCase()}</span>{" "}\n        <span className="winMeta">{event.source}</span>{" "}\n        <span>{event.message}</span>\n      </div>\n\n      {dataText && <pre>{dataText}</pre>}\n    </div>\n  );\n}\n\nexport default function TerminalPanel() {\n  const [events, setEvents] = useState([]);\n  const [health, setHealth] = useState(null);\n  const [expanded, setExpanded] = useState(true);\n  const [paused, setPaused] = useState(false);\n  const [autoScroll, setAutoScroll] = useState(false);\n  const [error, setError] = useState("");\n  const terminalRef = useRef(null);\n\n  async function loadEvents() {\n    if (paused) return;\n\n    try {\n      const data = await apiGet("/system/events?limit=120");\n      setEvents(data.events || []);\n      setError("");\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function loadHealth() {\n    try {\n      const data = await apiGet("/system/health");\n      setHealth(data);\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function clearTerminal() {\n    try {\n      const data = await apiDelete("/system/events");\n      setEvents(data.events || []);\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  useEffect(() => {\n    loadEvents();\n    loadHealth();\n\n    const eventsInterval = setInterval(loadEvents, 2200);\n    const healthInterval = setInterval(loadHealth, 12000);\n\n    return () => {\n      clearInterval(eventsInterval);\n      clearInterval(healthInterval);\n    };\n  }, [paused]);\n\n  useEffect(() => {\n    if (!autoScroll || !terminalRef.current) return;\n    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;\n  }, [events, autoScroll, expanded]);\n\n  const dbReady = health?.database?.database_exists;\n  const mlReady = health?.ml?.model_exists;\n  const ollamaReady = health?.llm?.providers?.ollama?.running;\n  const modelType = health?.ml?.metadata?.model_type || "not trained";\n  const ollamaModel = health?.llm?.providers?.ollama?.model || "offline";\n\n  return (\n    <div className="windowsTerminalCard">\n      <div className="windowsTerminalTopBar">\n        <div className="terminalDots">\n          <span />\n          <span />\n          <span />\n        </div>\n\n        <div className="terminalTitle">\n          Windows PowerShell - Backend Monitor\n        </div>\n\n        <div className="terminalActions">\n          <button type="button" onClick={() => setExpanded((value) => !value)}>\n            {expanded ? "Hide" : "Show"}\n          </button>\n          <button type="button" onClick={() => setPaused((value) => !value)}>\n            {paused ? "Resume" : "Pause"}\n          </button>\n          <button type="button" onClick={() => setAutoScroll((value) => !value)}>\n            Auto {autoScroll ? "On" : "Off"}\n          </button>\n          <button type="button" onClick={clearTerminal}>\n            Clear\n          </button>\n        </div>\n      </div>\n\n      <div className="windowsTerminalStatus">\n        <span>SQLite: {dbReady ? "online" : "offline"}</span>\n        <span>ML: {mlReady ? modelType : "not trained"}</span>\n        <span>Ollama: {ollamaReady ? ollamaModel : "offline"}</span>\n        <span>Events: {events.length}</span>\n        <span>Stream: {paused ? "paused" : "live"}</span>\n      </div>\n\n      {error && <div className="windowsTerminalError">{error}</div>}\n\n      {expanded && (\n        <div className="windowsTerminalWindow" ref={terminalRef}>\n          <div className="winTerminalIntro">\n            Windows PowerShell<br />\n            Copyright (C) Microsoft Corporation. All rights reserved.<br />\n            Backend telemetry stream initialized.\n          </div>\n\n          {events.length === 0 ? (\n            <div className="winTerminalLine">\n              <span className="winPrompt">PS backend&gt;</span> Waiting for backend events...\n            </div>\n          ) : (\n            events.map((event) => <EventLine key={event.id} event={event} />)\n          )}\n        </div>\n      )}\n    </div>\n  );\n}\n')

css_path = ROOT / 'frontend/src/styles.css'
current_css = css_path.read_text(encoding='utf-8') if css_path.exists() else ''
if '.windowsTerminalCard' not in current_css:
    css_path.write_text(current_css.rstrip() + '\n\n/* Windows-like black/white backend terminal monitor */\n.windowsTerminalCard {\n  border: 1px solid #2b2b2b;\n  border-radius: 10px;\n  background: #000000;\n  color: #f2f2f2;\n  overflow: hidden;\n  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.45);\n  font-family: Consolas, "Cascadia Mono", "Courier New", monospace;\n}\n\n.windowsTerminalTopBar {\n  min-height: 42px;\n  display: grid;\n  grid-template-columns: auto 1fr auto;\n  align-items: center;\n  gap: 12px;\n  padding: 8px 12px;\n  background: #111111;\n  border-bottom: 1px solid #2b2b2b;\n}\n\n.terminalDots {\n  display: flex;\n  gap: 6px;\n}\n\n.terminalDots span {\n  width: 10px;\n  height: 10px;\n  border-radius: 999px;\n  background: #777777;\n}\n\n.terminalTitle {\n  color: #ffffff;\n  font-weight: 700;\n  font-size: 14px;\n}\n\n.terminalActions {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 6px;\n}\n\n.terminalActions button {\n  background: #1f1f1f;\n  color: #ffffff;\n  border: 1px solid #666666;\n  border-radius: 4px;\n  padding: 5px 8px;\n  font-family: inherit;\n  font-size: 12px;\n}\n\n.terminalActions button:hover {\n  background: #333333;\n}\n\n.windowsTerminalStatus {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 0;\n  border-bottom: 1px solid #2b2b2b;\n  background: #050505;\n}\n\n.windowsTerminalStatus span {\n  padding: 8px 12px;\n  border-right: 1px solid #2b2b2b;\n  color: #ffffff;\n  font-size: 12px;\n}\n\n.windowsTerminalWindow {\n  height: 320px;\n  overflow: auto;\n  background: #000000;\n  color: #f2f2f2;\n  padding: 14px;\n  font-size: 13px;\n  line-height: 1.45;\n  scrollbar-color: #888888 #111111;\n}\n\n.winTerminalIntro {\n  color: #dcdcdc;\n  margin-bottom: 12px;\n  white-space: pre-wrap;\n}\n\n.winTerminalLine {\n  color: #f2f2f2;\n  padding: 3px 0;\n  border: 0;\n}\n\n.winTerminalLine pre {\n  margin: 3px 0 8px;\n  color: #dcdcdc;\n  white-space: pre-wrap;\n  font-family: inherit;\n  font-size: 12px;\n}\n\n.winPrompt {\n  color: #ffffff;\n  font-weight: 700;\n}\n\n.winTime,\n.winMeta {\n  color: #cfcfcf;\n}\n\n.windowsTerminalError {\n  background: #000000;\n  color: #ffffff;\n  border-bottom: 1px solid #777777;\n  padding: 8px 12px;\n  font-family: inherit;\n}\n\n@media (max-width: 900px) {\n  .windowsTerminalTopBar {\n    grid-template-columns: 1fr;\n  }\n\n  .terminalActions {\n    justify-content: flex-start;\n  }\n\n  .windowsTerminalStatus span {\n    width: 100%;\n    border-right: 0;\n    border-bottom: 1px solid #2b2b2b;\n  }\n}\n' + '\n', encoding='utf-8')
    print('updated: frontend/src/styles.css')
else:
    print('skipped: frontend/src/styles.css already has Windows terminal styles')

readme = ROOT / 'README.md'
if readme.exists():
    current = readme.read_text(encoding='utf-8')
    if '## Windows-Style Backend Terminal Monitor' not in current:
        readme.write_text(current.rstrip() + '\n\n## Windows-Style Backend Terminal Monitor\n\nThe terminal monitor now uses a black-and-white Windows PowerShell-style UI.\n\nNoise reduction:\n- `/system/events` polling is not logged.\n- `/system/health` polling is not logged.\n- Health polling is slower.\n- Auto-scroll is off by default so manual scrolling is usable.\n- Pause/Resume can freeze the event stream during demos.\n' + '\n', encoding='utf-8')
        print('updated: README.md')

print('\nTerminal UI fix applied successfully.')
print('Next: restart backend and refresh frontend.')