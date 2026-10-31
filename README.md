# OS Process Scheduler Lab

面向操作系统课程的进程调度实验平台。工程同时保留 C/ncurses 课程版本，并提供一个可在服务器上运行的 React + FastAPI Web 控制台。

启动 FastAPI 后会自动运行单 CPU `live` 模拟会话。打开首页即可实时查看 CPU 时间、时间片、运行进程和 READY、RUNNING、BLOCKED、FINISHED 队列；教学 PID 从 `1001` 起按生成顺序递增。

## 目录

- `frontend/`：React + Vite 控制台。
- `backend/`：FastAPI 会话、模拟调度器、真实 PID 调度器和 `/proc` 采集。
- `native/`：Linux C worker。
- `legacy-cli/`：原课程命令行版本。
- `docs/`：架构和实验说明。

详细部署请阅读 [docs/experiment-guide.md](docs/experiment-guide.md)。
