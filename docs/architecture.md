# OS Scheduler Lab 架构说明

## 运行边界

项目包含两个入口：

- `legacy-cli/`：课程验收用的 ncurses/C11 命令行版本。
- `backend/` + `frontend/`：实时 Web 实验控制台，默认监听 `127.0.0.1:4001`。

Web 版本由三层组成：

```text
浏览器
  ├── REST：创建会话、播放、暂停、单步、回退、重置、导出
  └── WebSocket：接收事件和快照
        │
        ▼
FastAPI
  ├── SimulationSession：固定种子、可回退的确定性模型
  ├── RealSession：真实 Linux worker、SIGSTOP/SIGCONT、/proc 采样
  └── 静态前端：frontend/dist
        │
        ▼
native/scheduler-worker
```

服务启动时自动创建并运行 `live` 模拟会话。浏览器只连接该会话进行观察，页面刷新不会重新创建调度器。模拟使用单 CPU，教学 PID 从 `1001` 开始并按生成顺序递增。

## 模拟模式

模拟模式在 Python 进程内执行课程规则，所有随机行为使用 `SessionConfig.seed` 初始化的独立随机数生成器。每次 `step()` 会按固定顺序执行：

1. 递减阻塞队列的 I/O 时间，完成后转到就绪队列。
2. 当前运行进程消耗一个时间片，完成、阻塞或回到就绪队列。
3. 已经在就绪队列中的进程优先级增加 1。
4. 生成当前时间到达的新进程，新进程不获得本 tick 的等待加分。
5. 取最高优先级的就绪进程运行。

每个 tick 开始前保存一个内部检查点，模拟模式可通过 `/api/sessions/{id}/back` 恢复到上一个 tick。真实模式不提供伪造回退。

页面显示当前 CPU 时间、时间片、运行进程 CPU 时间、CPU 利用率，以及 READY、RUNNING、BLOCKED、FINISHED 队列。连续运行模式会持续生成进程，完成记录只保留最近一段。

## 真实 PID 模式

后端只允许启动仓库内置的 `native/scheduler-worker`，不接受网页传入的命令。每个 worker 使用独立进程组启动，便于重置、停止或断线时只清理当前会话创建的进程。

worker 通过标准输入/输出传递教学协议：

```text
READY
RUN <milliseconds> <FINISH|IO|READY> <io_seconds>
CPU_SLICE_DONE
IO_REQUEST
RESUME
IO_RESUMED
FINISHED
EXIT
```

调度器在执行时间片前发送 `SIGCONT`，收到时间片结果后发送 `SIGSTOP`。I/O 请求进入阻塞队列，剩余时间归零后发送 `RESUME`，收到 `IO_RESUMED` 后再次停止 worker，等待下一次调度。

页面同时显示：

- 教学状态：`W/R/B/F`
- Linux 状态：`R/S/T`
- PID、PPID、PGID、RSS、文件描述符和上下文切换次数

这是用户态教学调度器。它只控制自己创建的 worker，不能替换 Linux 内核的 CFS，也不会重排系统中其他进程。

## 事件模型

所有事件统一包含：

```json
{
  "type": "snapshot",
  "seq": 42,
  "time": 12,
  "mode": "simulation",
  "payload": {}
}
```

事件类型包括创建、调度、剥夺、阻塞、唤醒、完成、`/proc` 采样、上下文切换、快照、报告和错误。

## 统计

对已完成进程使用固定公式：

```text
turnaround = finish_time - arrival_time
wait_time  = turnaround - cputime - io_total
weighted   = turnaround / cputime
```

前端统计用于实时展示，后端 `/report` 和 `/export` 是最终数据源。
