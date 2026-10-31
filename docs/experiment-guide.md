# 进程调度实验使用指南

## 1. Linux 服务器部署

在 Ubuntu/WSL 中执行：

```bash
cd ~/os-process-scheduler-lab/native
make

cd ../backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ..
npm --prefix frontend install
npm --prefix frontend run build

uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 4001
```

如果要使用 `legacy-cli`：

```bash
cd legacy-cli
make
./main -n 6 -s 42
```

真实 PID 模式需要先完成 `native/make`。模拟模式不依赖 C 编译器。

## 2. 反向代理

反向代理只需要把域名转发到本机：

```text
https://os_practice1.jasonrhan.cn
  -> http://127.0.0.1:4001
```

代理必须同时支持 HTTP 和 WebSocket，并保留 `/ws/` 路径。FastAPI 直接提供 `frontend/dist`，所以不需要额外的前端端口。

## 3. 课堂演示顺序

1. 启动 FastAPI 服务后打开首页，服务会自动运行 `live` 会话。
2. 观察 CPU 时间、时间片、运行进程 CPU 时间，以及 `READY / RUNNING / BLOCKED / FINISHED` 四个队列。
3. 点击暂停或继续，观察单 CPU 调度停止和恢复。
4. 观察运行进程每个时间片优先级降低 3、等待进程优先级增加 1。
5. 观察阻塞进程的 I/O 剩余时间，以及它回到 READY 的过程。
6. 点击进程行查看 PID、优先级、needtime、CPU 时间和 I/O 累计时间。
7. 使用重置重新开始连续演示。教学 PID 从 `1001` 起按生成顺序递增。

当前首页使用确定性模拟，适合课堂实时观察和复现。仓库保留真实 PID 后端和 C worker 作为扩展入口；真实模式的历史记录可以查看，但不能回退真实 Linux 进程。

## 4. 服务器验收

```bash
curl http://127.0.0.1:4001/api/health
```

浏览器中确认：

- 初始进程为 6 或 7 个。
- 时间片为 1 秒。
- 新进程按配置动态到达。
- W/R/B/F 状态能完整转换。
- 模拟模式固定种子后事件序列可复现。
- 真实模式页面显示 PID 与 `/proc` 采样字段。
- 重置或停止后没有残留 `scheduler-worker`。

## 5. 截图建议

建议保留四张截图：

- 初始运行：READY 队列和 CPU 核心。
- 阻塞发生：BLOCKED 队列、I/O 剩余时间和事件流。
- 动态到达：顶部 CREATED 计数、下次到达时间和新进程。
- 完成报告：FINISHED 队列、甘特图和周转/等待统计。
