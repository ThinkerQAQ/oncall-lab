# Oncall Lab

独立的生产故障排查实验环境，使用 **Go、Kitex（Thrift RPC）、Docker Compose 和开源可观测性工具** 构建可重复验证的技术案例。

仅使用合成请求、独立服务和公开技术，不复刻或公开任何公司的内部系统、配置与真实故障数据。

## 主要内容

- **RPC**：Gateway → Kitex Metadata Service，真实 Thrift 调用与客户端超时设置。
- **可观测性**：通过 Docker Compose 管理 Prometheus、Grafana、Loki、Tempo。
- **实验计划**：先验证 RPC 超时，再逐步研究负载均衡、服务发现、优雅退出和滚动发布。

目前是实验环境的初始版本，并非已经完成的生产事故复现。 Gateway 和 Metadata 的指标已接入；Loki 日志采集、Tempo 调用链目前仅准备了基础设施，业务埋点留待故障场景阶段接入。

## 启动

~~~sh
cp .env.example .env   # 修改 .env 中的 Grafana 管理员密码
docker compose up -d --build
curl 'http://127.0.0.1:28080/metadata?id=demo'
~~~

Grafana：http://127.0.0.1:23000

停止：

~~~sh
docker compose down
~~~

具体代码职责和验收约束见 AGENTS.md。禁止提交内部源码、生产配置和原始监控截图。
