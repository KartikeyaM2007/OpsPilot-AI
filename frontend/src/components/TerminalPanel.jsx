import { useEffect, useRef, useState } from "react";

import { apiDelete, apiGet } from "../api/client";

function formatTime(timestamp) {
  if (!timestamp) return "";
  return timestamp.replace("T", " ");
}

function formatData(data) {
  if (!data || Object.keys(data).length === 0) return "";
  return JSON.stringify(data, null, 2)
    .split("\n")
    .map((line) => `    ${line}`)
    .join("\n");
}

function EventLine({ event }) {
  const dataText = formatData(event.data);

  return (
    <div className="winTerminalLine">
      <div>
        <span className="winPrompt">PS backend&gt;</span>{" "}
        <span className="winTime">[{formatTime(event.timestamp)}]</span>{" "}
        <span className="winMeta">{event.level.toUpperCase()}</span>{" "}
        <span className="winMeta">{event.source}</span>{" "}
        <span>{event.message}</span>
      </div>

      {dataText && <pre>{dataText}</pre>}
    </div>
  );
}

export default function TerminalPanel() {
  const [events, setEvents] = useState([]);
  const [health, setHealth] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(false);
  const [error, setError] = useState("");
  const terminalRef = useRef(null);

  async function loadEvents() {
    if (paused) return;

    try {
      const data = await apiGet("/system/events?limit=120");
      setEvents(data.events || []);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadHealth() {
    try {
      const data = await apiGet("/system/health");
      setHealth(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function clearTerminal() {
    try {
      const data = await apiDelete("/system/events");
      setEvents(data.events || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadEvents();
    loadHealth();

    const eventsInterval = setInterval(loadEvents, 2200);
    const healthInterval = setInterval(loadHealth, 12000);

    return () => {
      clearInterval(eventsInterval);
      clearInterval(healthInterval);
    };
  }, [paused]);

  useEffect(() => {
    if (!autoScroll || !terminalRef.current) return;
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [events, autoScroll, expanded]);

  const dbReady = health?.database?.database_exists;
  const mlReady = health?.ml?.model_exists;
  const ollamaReady = health?.llm?.providers?.ollama?.running;
  const modelType = health?.ml?.metadata?.model_type || "not trained";
  const ollamaModel = health?.llm?.providers?.ollama?.model || "offline";

  return (
    <div className="windowsTerminalCard">
      <div className="windowsTerminalTopBar">
        <div className="terminalDots">
          <span />
          <span />
          <span />
        </div>

        <div className="terminalTitle">
          Windows PowerShell - Backend Monitor
        </div>

        <div className="terminalActions">
          <button type="button" onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Hide" : "Show"}
          </button>
          <button type="button" onClick={() => setPaused((value) => !value)}>
            {paused ? "Resume" : "Pause"}
          </button>
          <button type="button" onClick={() => setAutoScroll((value) => !value)}>
            Auto {autoScroll ? "On" : "Off"}
          </button>
          <button type="button" onClick={clearTerminal}>
            Clear
          </button>
        </div>
      </div>

      <div className="windowsTerminalStatus">
        <span>SQLite: {dbReady ? "online" : "offline"}</span>
        <span>ML: {mlReady ? modelType : "not trained"}</span>
        <span>Ollama: {ollamaReady ? ollamaModel : "offline"}</span>
        <span>Events: {events.length}</span>
        <span>Stream: {paused ? "paused" : "live"}</span>
      </div>

      {error && <div className="windowsTerminalError">{error}</div>}

      {expanded && (
        <div className="windowsTerminalWindow" ref={terminalRef}>
          <div className="winTerminalIntro">
            Windows PowerShell<br />
            Copyright (C) Microsoft Corporation. All rights reserved.<br />
            Backend telemetry stream initialized.
          </div>

          {events.length === 0 ? (
            <div className="winTerminalLine">
              <span className="winPrompt">PS backend&gt;</span> Waiting for backend events...
            </div>
          ) : (
            events.map((event) => <EventLine key={event.id} event={event} />)
          )}
        </div>
      )}
    </div>
  );
}
