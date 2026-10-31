import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Cpu,
  Gauge,
  HardDrive,
  Layers3,
  ListTree,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Terminal,
  Wifi,
  WifiOff
} from "lucide-react";
import { request, websocketUrl } from "./api";

const STATES = {
  W: { label: "READY", color: "amber" },
  R: { label: "RUNNING", color: "red" },
  B: { label: "BLOCKED", color: "violet" },
  F: { label: "FINISHED", color: "green" }
};

const EVENT_LABELS = {
  session_started: "会话启动",
  session_paused: "暂停播放",
  session_reset: "重新初始化",
  process_created: "进程到达",
  process_scheduled: "调度运行",
  process_preempted: "时间片结束",
  process_blocked: "进入阻塞",
  process_woken: "I/O 唤醒",
  process_finished: "进程完成",
  context_switch: "上下文切换",
  report_ready: "报告生成",
  error: "错误"
};

const COLORS = ["#63d6c8", "#f5bd4f", "#f17878", "#8f91ff", "#73a9f4", "#b1e06e"];

function countsOf(snapshot) {
  return (snapshot?.processes || []).reduce(
    (result, process) => {
      result[process.state] = (result[process.state] || 0) + 1;
      return result;
    },
    { W: 0, R: 0, B: 0, F: 0 }
  );
}

function useSimulation() {
  const [sessionId, setSessionId] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [events, setEvents] = useState([]);
  const [connection, setConnection] = useState("offline");
  const [error, setError] = useState("");
  const socketRef = useRef(null);
  const reconnectRef = useRef(null);

  const acceptSnapshot = useCallback((next) => {
    if (!next) return;
    setSnapshot(next);
  }, []);

  const createSession = useCallback(async () => {
    try {
      const result = await request("/sessions/live/snapshot");
      const next = result.snapshot;
      setSessionId(next.session_id);
      setSnapshot(next);
      setEvents(next.events || []);
    } catch (caught) {
      setError(caught.message);
    }
  }, []);

  useEffect(() => {
    createSession();
    return () => {
      socketRef.current?.close();
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    };
  }, [createSession]);

  useEffect(() => {
    if (!sessionId) return undefined;
    let closed = false;
    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(websocketUrl(sessionId));
      socketRef.current = socket;
      socket.onopen = () => setConnection("online");
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data);
          if (event.type === "snapshot") {
            acceptSnapshot(event.payload);
          } else if (event.type !== "heartbeat") {
            setEvents((previous) => [...previous, event].slice(-100));
          }
        } catch {
          setError("实时事件解析失败");
        }
      };
      socket.onerror = () => setConnection("error");
      socket.onclose = () => {
        setConnection("offline");
        if (!closed) reconnectRef.current = window.setTimeout(connect, 2200);
      };
    };
    connect();
    return () => {
      closed = true;
      socketRef.current?.close();
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    };
  }, [acceptSnapshot, sessionId]);

  const action = useCallback(async (name) => {
    if (!sessionId) return null;
    try {
      const result = await request(`/sessions/live/${name}`, { method: "POST" });
      acceptSnapshot(result.snapshot);
      return result.snapshot;
    } catch (caught) {
      setError(caught.message);
      return null;
    }
  }, [acceptSnapshot, sessionId]);

  return { sessionId, snapshot, events, connection, error, setError, action };
}

function StateBadge({ state }) {
  const meta = STATES[state] || STATES.W;
  return <span className={`state-badge state-${meta.color}`}>{state} · {meta.label}</span>;
}

function ProcessRow({ process, onSelect, selected }) {
  return (
    <button className={`process-row is-compact ${selected === process.name ? "is-selected" : ""}`} onClick={() => onSelect(process.name)}>
      <div className="process-row-main">
        <span className="process-mark" />
        <span className="process-name">{process.name}</span>
        <StateBadge state={process.state} />
        <span className="pid-chip">PID {process.pid}</span>
      </div>
      <div className="process-values">
        <span><small>prio</small>{process.prio}</span>
        <span><small>need</small>{process.needtime}</span>
        <span><small>cpu</small>{process.cputime}</span>
        {process.state === "B" && <span><small>I/O</small>{process.io_remain}s</span>}
      </div>
    </button>
  );
}

function QueueLane({ title, subtitle, count, tone, processes, selected, onSelect, icon: Icon, empty }) {
  return (
    <section className={`lane lane-${tone}`}>
      <div className="lane-header">
        <div className="lane-title">
          <Icon size={16} />
          <div><strong>{title}</strong><span>{subtitle}</span></div>
        </div>
        <span className="lane-count">{count}</span>
      </div>
      <div className="lane-body">
        {processes.length ? processes.map((process) => (
          <ProcessRow key={process.name} process={process} selected={selected} onSelect={onSelect} />
        )) : (
          <div className="empty-state"><div className="empty-glyph">∅</div><span>{empty}</span></div>
        )}
      </div>
    </section>
  );
}

function CpuCore({ running, time, timeSlice, onSelect }) {
  return (
    <section className={`cpu-panel ${running ? "cpu-active" : ""}`}>
      <div className="lane-header">
        <div className="lane-title">
          <Cpu size={16} />
          <div><strong>CPU CORE 0</strong><span>当前运行进程</span></div>
        </div>
        <span className="lane-count">{running ? "RUN" : "IDLE"}</span>
      </div>
      <div className="cpu-body">
        <div className="cpu-ring">
          <div className="cpu-ring-inner">
            <span className="cpu-caption">TIME SLICE</span>
            <strong>{running?.name || "IDLE"}</strong>
            <span>{running ? "执行中" : `T${time} 等待中`}</span>
          </div>
        </div>
        {running ? (
          <button className="cpu-process" onClick={() => onSelect(running.name)}>
            <div><span>{running.name}</span><small>PID {running.pid}</small></div>
            <StateBadge state={running.state} />
          </button>
        ) : <div className="cpu-idle-note">没有可运行的进程</div>}
        <div className="cpu-specs">
          <div><span>priority</span><strong>{running?.prio ?? "—"}</strong></div>
          <div><span>needtime</span><strong>{running?.needtime ?? "—"}</strong></div>
          <div><span>cputime</span><strong>{running?.cputime ?? "—"}</strong></div>
          <div><span>slice</span><strong>{timeSlice}s</strong></div>
        </div>
      </div>
    </section>
  );
}

function SimpleDetail({ process }) {
  if (!process) return null;
  return (
    <div className="simple-detail">
      <div className="simple-detail-title">
        <span>选中进程</span>
        <strong>{process.name}</strong>
        <StateBadge state={process.state} />
      </div>
      <div className="simple-detail-values">
        <span>PID <b>{process.pid}</b></span>
        <span>优先级 <b>{process.prio}</b></span>
        <span>needtime <b>{process.needtime}</b></span>
        <span>CPU <b>{process.cputime}s</b></span>
        <span>I/O <b>{process.io_total}s</b></span>
      </div>
    </div>
  );
}

function SectionHeader({ icon: Icon, title, subtitle, tag }) {
  return (
    <div className="section-header">
      <div className="section-heading">
        <Icon size={15} />
        <div><strong>{title}</strong><span>{subtitle}</span></div>
      </div>
      {tag && <span className="panel-tag">{tag}</span>}
    </div>
  );
}

function Gantt({ snapshot }) {
  const rows = snapshot?.processes || [];
  const gantt = snapshot?.gantt || [];
  const maxTime = Math.max(1, ...gantt.map((entry) => entry.time));
  const times = Array.from({ length: Math.min(maxTime, 36) }, (_, index) => maxTime - Math.min(maxTime, 36) + index + 1);
  return (
    <div className="gantt">
      <div className="gantt-row gantt-head"><span className="gantt-name">进程</span>{times.map((time) => <span key={time}>{time}</span>)}</div>
      {rows.map((process) => (
        <div className="gantt-row" key={process.name}>
          <span className="gantt-name"><i style={{ background: COLORS[(Number(process.name.replace("P", "")) - 1) % COLORS.length] }} />{process.name}</span>
          {times.map((time) => {
            const active = gantt.some((entry) => entry.time === time && entry.process === process.name);
            return <span key={time} className={active ? "gantt-cell active" : "gantt-cell"}>{active ? "·" : ""}</span>;
          })}
        </div>
      ))}
    </div>
  );
}

function EventStream({ events }) {
  const visible = events.filter((event) => !["snapshot", "heartbeat"].includes(event.type)).slice(-14).reverse();
  return (
    <div className="event-stream">
      {visible.length ? visible.map((event, index) => {
        const process = event.payload?.process;
        return (
          <div className="event-line" key={`${event.seq}-${index}`}>
            <span className="event-time">T{event.time ?? "—"}</span>
            <span className={`event-dot event-${event.type}`} />
            <div><strong>{EVENT_LABELS[event.type] || event.type}</strong><span>{process ? `${process.name} · ${process.state}` : event.payload?.message || event.payload?.reason || "系统事件"}</span></div>
            <small>#{event.seq}</small>
          </div>
        );
      }) : <div className="empty-state"><span>点击“开始模拟”查看事件</span></div>}
    </div>
  );
}

function Report({ snapshot }) {
  const rows = (snapshot?.finished || []).map((process) => {
    const turnaround = process.finish_time - process.arrival_time;
    const wait = turnaround - process.cputime - process.io_total;
    return { ...process, turnaround, wait, weighted: process.cputime ? turnaround / process.cputime : 0 };
  });
  const average = (key) => rows.length ? rows.reduce((sum, row) => sum + row[key], 0) / rows.length : 0;
  return (
    <div className="report-wrap">
      <div className="report-summary">
        <div><strong>{rows.length}</strong><span>已完成</span></div>
        <div><strong>{average("turnaround").toFixed(2)}</strong><span>平均周转</span></div>
        <div><strong>{average("wait").toFixed(2)}</strong><span>平均等待</span></div>
        <div><strong>{average("weighted").toFixed(2)}</strong><span>平均带权</span></div>
      </div>
      <div className="report-table">
        <div className="report-row report-head"><span>进程</span><span>到达</span><span>完成</span><span>CPU</span><span>I/O</span><span>周转</span><span>等待</span><span>带权</span></div>
        {rows.map((row) => <div className="report-row" key={row.name}><span className="report-process">{row.name} · {row.pid}</span><span>{row.arrival_time}</span><span>{row.finish_time}</span><span>{row.cputime}</span><span>{row.io_total}</span><span>{row.turnaround}</span><span>{row.wait}</span><span>{row.weighted.toFixed(2)}</span></div>)}
        {!rows.length && <div className="report-empty">模拟完成后会在这里显示最终统计。</div>}
      </div>
    </div>
  );
}

function App() {
  const { sessionId, snapshot, events, connection, error, setError, action } = useSimulation();
  const [selected, setSelected] = useState(null);
  const counts = countsOf(snapshot);
  const processes = snapshot?.processes || [];
  const selectedProcess = processes.find((process) => process.name === selected) || snapshot?.running || processes[0];
  const status = snapshot?.status || "ready";

  useEffect(() => {
    if (!selectedProcess && processes[0]) setSelected(processes[0].name);
  }, [processes, selectedProcess]);

  const statusLabel = { ready: "READY", running: "RUNNING", paused: "PAUSED", completed: "COMPLETED", stopped: "STOPPED", error: "ERROR" }[status] || "READY";

  return (
    <div className="app-shell simple-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="brand-symbol"><Layers3 size={20} /></div>
          <div><div className="brand-title">OS Scheduler Lab</div><div className="brand-subtitle">PROCESS SCHEDULING / EXPERIMENT 01</div></div>
        </div>
        <div className="topbar-meta">
          <div className="top-chip"><span className={`status-pulse ${status === "running" ? "is-running" : ""}`} />实验 <strong>{statusLabel}</strong></div>
          <div className="top-chip"><Clock3 size={14} />时钟 <strong>T{snapshot?.time ?? 0}</strong></div>
          <div className={`connection-chip connection-${connection}`}>{connection === "online" ? <Wifi size={14} /> : <WifiOff size={14} />}{connection === "online" ? "实时连接" : "连接中"}</div>
        </div>
      </header>

      <main className="simple-main">
        <section className="simple-intro">
          <div>
            <h1>实时进程调度</h1>
          </div>
          <div className="simple-actions">
            <button className="primary-button" onClick={() => action(status === "running" ? "pause" : "start")} disabled={!snapshot}>
              {status === "running" ? <Pause size={16} /> : <Play size={16} />}{status === "running" ? "暂停监控" : "继续运行"}
            </button>
            <button className="secondary-button" onClick={() => action("reset")} disabled={!snapshot}><RotateCcw size={15} />重置演示</button>
          </div>
        </section>

        {error && <button className="simple-error" onClick={() => setError("")}>{error} · 点击关闭</button>}

        <div className="simple-rule">
          <span><Gauge size={14} />自动运行</span><b>运行 -3</b><b>等待 +1</b><b>I/O 20%</b><b>时间片 1s</b><span className="simple-session">PID 按生成顺序递增</span>
        </div>

        <div className="cpu-metrics">
          <div><span>CPU CLOCK</span><strong>T{snapshot?.cpu_time ?? snapshot?.time ?? 0}</strong><small>模拟时钟</small></div>
          <div><span>TIME SLICE</span><strong>{snapshot?.time_slice ?? 1}s</strong><small>单核调度粒度</small></div>
          <div><span>RUNNING CPU</span><strong>{snapshot?.running_cpu_time ?? 0}s</strong><small>{snapshot?.running?.name || "IDLE"} 累计服务</small></div>
          <div><span>CPU LOAD</span><strong>{snapshot?.cpu_utilization || 0}%</strong><small>当前单 CPU 占用</small></div>
        </div>

        <div className="state-strip">
          {Object.entries({ W: "READY", R: "RUNNING", B: "BLOCKED", F: "FINISHED" }).map(([key, label]) => (
            <div className={`state-count state-count-${STATES[key].color}`} key={key}><span>{key}</span><strong>{counts[key] || 0}</strong><small>{label}</small></div>
          ))}
          <div className="state-count state-count-neutral"><span>Σ</span><strong>{snapshot?.created || 0}</strong><small>CREATED</small></div>
        </div>

        <section className="stage-grid">
          <QueueLane title="READY QUEUE" subtitle="就绪队列 · W" count={`${snapshot?.ready?.length || 0} 个`} tone="amber" processes={snapshot?.ready || []} selected={selected} onSelect={setSelected} icon={ListTree} empty="就绪队列为空" />
          <CpuCore
            running={snapshot?.running}
            time={snapshot?.time || 0}
            timeSlice={snapshot?.time_slice || 1}
            onSelect={setSelected}
          />
          <div className="stage-stack">
            <QueueLane title="BLOCKED" subtitle="I/O 阻塞 · B" count={`${snapshot?.blocked?.length || 0} 个`} tone="violet" processes={snapshot?.blocked || []} selected={selected} onSelect={setSelected} icon={HardDrive} empty="没有阻塞进程" />
            <QueueLane title="FINISHED" subtitle="完成队列 · F" count={`${snapshot?.finished?.length || 0} 个`} tone="green" processes={snapshot?.finished || []} selected={selected} onSelect={setSelected} icon={CheckCircle2} empty="等待完成进程" />
          </div>
        </section>

        <div className="simple-detail">
          <div className="simple-detail-title"><span>选中进程</span><strong>{selectedProcess?.name || "—"}</strong>{selectedProcess && <StateBadge state={selectedProcess.state} />}</div>
          <div className="simple-detail-values">
            <span>PID <b>{selectedProcess?.pid || "—"}</b></span><span>优先级 <b>{selectedProcess?.prio ?? "—"}</b></span><span>needtime <b>{selectedProcess?.needtime ?? "—"}</b></span><span>CPU <b>{selectedProcess ? `${selectedProcess.cputime}s` : "—"}</b></span><span>I/O <b>{selectedProcess ? `${selectedProcess.io_total}s` : "—"}</b></span>
          </div>
        </div>

        <div className="analysis-grid lower-analysis">
          <section className="panel analysis-panel"><SectionHeader icon={Activity} title="GANTT TIMELINE" subtitle="每个时间片的运行进程" tag="1s / TICK" /><Gantt snapshot={snapshot} /></section>
          <section className="panel analysis-panel"><SectionHeader icon={Terminal} title="EVENT STREAM" subtitle="状态转换日志" tag="REALTIME" /><EventStream events={events.length ? events : snapshot?.events || []} /></section>
        </div>

        <section className="panel report-panel"><SectionHeader icon={RefreshCw} title="FINAL REPORT" subtitle="周转、等待和带权周转时间" tag="公式固定" /><Report snapshot={snapshot} /></section>

      </main>

      <footer className="footer-bar"><span>课程实验 · 动态优先级调度</span><span>PID 按生成顺序递增 · 127.0.0.1:4001</span></footer>
    </div>
  );
}

export default App;
