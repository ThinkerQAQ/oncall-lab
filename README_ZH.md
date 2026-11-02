# Oncall Lab

基于 **Go、Kitex（Thrift RPC）、Docker Compose、Prometheus、Grafana、Loki、Tempo、Mailpit 和 Kubernetes（Kind）** 的可复现故障排查实验。从真实收到告警开始，沿着 Metrics、日志、Trace 和运行代码逐步定位问题。

全部服务、请求、错误及故障域均为**独立合成实验**。Docker 和 Kind 中的三个逻辑 Zone **不等于物理机房或真实可用区**。

## 目录

1. [项目简介](#1-项目简介)
2. [实验架构](#2-实验架构)
3. [快速开始](#3-快速开始)
4. [实验场景](#4-实验场景)
5. [配置说明](#5-配置说明)
6. [常见问题](#6-常见问题)
7. [开发与清理](#7-开发与清理)

## 1. 项目简介

主案例是**由受控服务端处理延迟引发的真实 Kitex RPC 超时**。六个 Gateway 进程调用六个 Metadata 进程，分布在三个逻辑 Zone。故障阶段仅对 Zone A 的部分请求注入 **1,500ms** 的服务端处理时间，超过客户端 **1,200ms** 的 RPC 超时预算。

Kitex 和 Prometheus 上报真实 RPC 指标；Promtail/Loki 采集 JSON 日志；OpenTelemetry/Tempo 记录关联的客户端和服务端 Span。Grafana 根据 **P2 / Warning**（超时 QPS）和 **P1 / Critical**（Zone A 超时比例持续 20 秒超过 25%）规则，通过 SMTP 把触发和恢复邮件送到**本地 Mailpit 收件箱**，不会发送到真实邮箱。

另有独立 Kind 实验，验证 Kubernetes 的滚动发布、自动扩容、实例摘流、请求分配和 Pod 替换。**客户端超时不代表服务端 Handler 必然执行失败**。

## 2. 实验架构

~~~text
合成流量生成器
  ├── Zone A：Gateway A1/A2 ── Kitex/Thrift ── Metadata A1/A2
  ├── Zone B：Gateway B1/B2 ── Kitex/Thrift ── Metadata B1/B2
  └── Zone C：Gateway C1/C2 ── Kitex/Thrift ── Metadata C1/C2
                      │
                      ├── Kitex / 应用指标 ── Prometheus
                      ├── JSON 日志 ── Promtail ── Loki
                      └── OpenTelemetry ── Tempo
                                           │
                       Grafana Dashboard / Explore / Alerting
                                           │
                                  本地 SMTP ── Mailpit

独立 Kind：控制平面 + 3 个带逻辑 Zone 标签的 Worker
  └── Deployment / Service / EndpointSlice / HPA
~~~

Compose 主案例刻意采用 Gateway 到 Metadata 的**一对一路由**，以便核对真实实例上的失败分布；它没有实现生产环境级别的动态服务发现。Kind 的三个逻辑 Zone 也都运行在同一台物理电脑上。

## 3. 快速开始

### 3.1 环境准备

- 安装 **Git、Docker Engine / Docker Desktop（含 Compose v2）、Bash、Python 3 和 curl**。
- Docker 服务已启动：可执行 `docker info`、`docker compose version` 验证。
- 首次构建需要联网下载公开容器镜像和 Go 依赖。
- 本地端口未被占用，详见[配置说明](#5-配置说明)。

Windows 推荐使用 **WSL2 + Docker Desktop 集成**。下列命令均在 Bash 执行。主实验的二进制由 Docker 构建，**宿主机不必单独安装 Go**。

### 3.2 下载代码并配置

~~~bash
git clone https://github.com/ThinkerQAQ/oncall-lab.git
cd oncall-lab
cp .env.example .env
~~~

编辑 `.env`，将 `GRAFANA_ADMIN_PASSWORD` 设置成**自己的本地密码**。该文件被 Git 忽略。

### 3.3 一键复现完整故障

~~~bash
bash scripts/scenarios/replay-alert-notification.sh
~~~

脚本会一次性构建 Gateway、Metadata、Load Generator，启动三个逻辑 Zone 和 **Prometheus、Grafana、Loki、Promtail、Tempo、Mailpit**，依次执行**正常基线 → 超时注入 → 恢复观察**。

脚本会校验真实请求结果，并等待**本轮 P1、P2 两个等级的 FIRING / RESOLVED 邮件**。本地日志和实验记录保存在 `evidence/`。

Grafana 的告警评估和通知分组是异步的，**邮件送达不一定与指标状态变化同时发生**。

### 3.4 验收结果

| 本地入口 | 预期结果 |
| --- | --- |
| [Mailpit](http://127.0.0.1:28025) | P1/Critical 与 P2/Warning，各有 **FIRING**、**RESOLVED** 邮件 |
| [Grafana](http://127.0.0.1:23000) | Dashboard、告警和 Prometheus / Loki / Tempo Explore |
| [Prometheus](http://127.0.0.1:23090) | 真实 RPC、实例指标和抓取目标状态 |
| [Zone A Gateway](http://127.0.0.1:28081/metadata?id=demo) | 正常 Kitex 请求返回 HTTP 200 |

Grafana Explore 需要使用 `demo` 和 `.env` 中的密码登录；匿名访问仅具有 Viewer 权限。脚本会按**本次实验的开始时间**筛选邮件，不会拿旧邮件冒充新结果。

也可以单独运行验收工具：

~~~bash
python3 scripts/verify_zone_run.py "$(ls -1t evidence/alert-notification-*.log | head -1)"
python3 scripts/verify_mailpit_notifications.py
~~~

每轮请求总数可能随调度时间有轻微变化，不必与文章中的数字完全一致。关键是观察**错误集中在 Zone A、恢复阶段成功，以及两个级别的通知都送达**。Mailpit 邮件显示“已读”**不代表值班人员已经 ACK 认领事件**。

## 4. 实验场景

先完成[快速开始](#3-快速开始)，再执行下列独立的 Compose 实验。

### 4.1 RPC 超时和业务错误

~~~bash
# 正常 Kitex 调用 → HTTP 200
curl 'http://127.0.0.1:28081/metadata?id=demo'

# Handler 延迟超过 1.2s 客户端预算 → HTTP 504
curl -i 'http://127.0.0.1:28081/metadata?id=slow&delay_ms=1500'

# 真实 Kitex BizStatusError(2101) → HTTP 502
curl -i 'http://127.0.0.1:28081/metadata?id=synthetic-application-error'
~~~

`2101` 是**合成业务错误码**，不是企业内部的真实错误码。

### 4.2 Metrics → Logs → Trace

打开 Grafana **Explore**，分别选择：

- **Prometheus**：`sum by (zone) (rate(rpc_client_requests_total{result="timeout",zone=~"zone-.*"}[30s]))`
- **Loki**：`{job="oncall-lab",result="timeout"}`。打开真实的 Gateway 超时日志，复制 `trace_id`。
- **Tempo**：用同一个 Trace ID 查看 Gateway HTTP → Kitex Client → Metadata Server 三层 Span。

客户端可能在约 **1,200ms** 超时，而服务端 Handler 在约 **1,500ms** 后才完成。应同时核对**上下游两端**，不能只凭 HTTP 504 判定网络故障。

### 4.3 连接故障与恢复

~~~bash
bash scripts/scenarios/connection-unavailable.sh
~~~

脚本停止 **Zone B1** Metadata 实例，检查真实 Kitex 连接/传输错误，然后恢复服务。连接重试耗尽 RPC 超时预算时，最终也可能表现为 HTTP 504。

### 4.4 真实变更记录

~~~bash
bash scripts/scenarios/record-change.sh
~~~

采集真实容器启动时间和镜像 ID，重建一台 Zone C Gateway，再比较前后记录。此处验证的是**同镜像实例重建**，不是新代码发布。记录保存在 `evidence/`。

### 4.5 Kubernetes 实验准备（Kind）

Kubernetes 脚本目前在 **Linux amd64（含 WSL2）**、Docker 可用的环境中实现并验证。与主实验不同，此部分还需要 **Go、curl 和 sha256sum**，用于安装 Kind 及指定版本的 Linux kubectl。其他架构尚未验证。

~~~bash
bash k8s/up.sh
bash k8s/check.sh
~~~

预期结果：三个带**逻辑 Zone 标签**的 Worker、六个 Ready Metadata Pod（**2/2/2** 分布）、六个 Ready Service Endpoint，以及转发到 `127.0.0.1:28084` 的 Gateway。

### 4.6 实例摘流并保留现场

~~~bash
bash k8s/drain.sh
~~~

预期结果：Pod 保持 Running、Liveness 正常，**Ready Endpoint 数由 6 → 5 → 6**。已有连接可能在 EndpointSlice 更新后继续存活。

### 4.7 滚动发布、Pod 替换与手动扩容

~~~bash
bash k8s/lifecycle.sh
~~~

验证实际滚动发布、ReplicaSet 自动补齐已删除的 Pod，以及副本数 **6 → 9 → 6 的手动调整**。这与 HPA 实验不同。

### 4.8 CPU 自动扩容（HPA）

~~~bash
bash k8s/metrics-server.sh
bash k8s/hpa.sh
~~~

在本实验的临时 Kind 集群安装 Metrics Server，通过受控 CPU 负载触发 HPA。观察期望副本数是否从 6 增加；结束后脚本会清理 HPA、CPU 负载并恢复六个副本。

Metrics Server 使用了**仅供 Kind 实验的非严格 kubelet TLS 配置**，**不能直接用于生产环境**。

### 4.9 实例路由与持续请求下的滚动发布

~~~bash
python3 k8s/load-balancing.py
python3 k8s/rollout-traffic.py
~~~

前一个实验读取真实 Pod 的 Kitex Counter，观察 TCP 长连接复用造成的请求分布；**不保证六个 Pod 均分流量**。后一个实验在滚动发布时发送 420 次 RPC，将每次 HTTP 结果保存在 `evidence/`。某一轮全部成功，不代表所有场景都能做到零错误发布。

## 5. 配置说明

| 文件 / 配置 | 用途 |
| --- | --- |
| `.env` / `GRAFANA_ADMIN_PASSWORD` | 本地 Grafana 用户 `demo` 的密码，禁止提交 |
| `compose.yaml` | 基础服务、可观测性组件和本地端口 |
| `compose.zones.yaml` | 三个逻辑 Zone 与真实 Gateway / Metadata 进程 |
| `observability/prometheus/` | Kitex / 应用指标采集 |
| `observability/grafana/` | Dashboard、P1/P2 告警与本地邮件通知 |
| `observability/promtail/`、`loki/`、`tempo/` | 日志采集与分布式 Trace |
| `k8s/` | Kind 发布、就绪探测、扩缩容和实例恢复 |
| `evidence/`、`Data/` | Git 忽略的本地证据、kubeconfig 与工具 |

以下端口仅绑定 **127.0.0.1**：Grafana `23000`、Mailpit `28025`、Prometheus `23090`、Loki `23100`、Tempo `23200`、基础 Gateway `28080`、逻辑 Zone Gateway `28081`～`28083`、Kind Gateway `28084`。Mailpit SMTP **不会暴露到宿主机**，也不会向外部邮箱发送。

## 6. 常见问题

- **无法连接 Docker**：启动 Docker Desktop / Docker Engine，必要时开启 WSL 集成，然后执行 `docker info`。
- **缺少 Grafana 密码**：从 `.env.example` 复制 `.env`，设置 `GRAFANA_ADMIN_PASSWORD`。
- **端口冲突**：检查上述本地端口。Compose 项目名为 `oncall-lab`。
- **邮件暂时未到**：检查 Mailpit 和 Grafana；告警评估与邮件分组是异步的。完整脚本会校验**本轮新邮件**。
- **Loki 查不到日志**：检查 `docker compose -f compose.yaml -f compose.zones.yaml ps promtail`。一键脚本会显式启动日志采集。
- **Grafana Explore 无法匿名访问**：使用 `demo` 登录。
- **Kind Pod 未 Ready / 分布异常**：执行 `bash k8s/check.sh`、`bash k8s/rebalance.sh`，并检查 Docker 资源是否充足。

## 7. 开发与清理

主实验不要求宿主机安装 Go；**源码开发与 Kind 初始化**才需要 Go。

~~~bash
go test ./...
go vet ./...
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s k8s -p 'test_*.py'
docker compose -f compose.yaml -f compose.zones.yaml config --quiet
~~~

停止 Compose 环境，并**保留** Mailpit 邮件与日志卷：

~~~bash
docker compose -f compose.yaml -f compose.zones.yaml down
~~~

确认不再使用 Kubernetes 实验时，再单独删除 Kind 集群：

~~~bash
"$(go env GOPATH)/bin/kind" delete cluster --name oncall-lab-kind
~~~

`docker compose down -v` **会额外删除本地具名数据卷**，不属于日常清理命令。请保持 `.env`、`Data/` 和 `evidence/` 私有。仓库不包含企业内部代码或真实生产故障数据。
