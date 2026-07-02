"""第十四章：答辩问题全景回答 — 融合旧版详细FAQ + 新版405问"""
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def add_faq_chapter(doc, heading, para_fn, bullet_fn, code_fn, table_fn, callout_fn):
    """Generate the full FAQ chapter with merged detailed + concise answers."""
    doc.add_page_break()

    heading("十四、答辩问题全景回答", level=1)
    para_fn(
        "以下 149 个核心问答融合了两版内容：旧版 FAQ（33 问，详实叙述）和 GPT-5.5 答辩清单（405 问，25 板块）。"
        "前 9 个主题板块保留旧版的详细论证，后续板块覆盖答辩清单中新增的关键问题。"
    )

    # ═══════════════════════════════════════════════════
    # 14.1 产品定位（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.1 产品定位", level=2)

    para_fn("Q1：这个项目到底是「监控工具」还是「Agent 通信基础设施」？", bold=True)
    para_fn(
        "两者都是，但有主次。MyAgentWatch 的核心定位是 Agent Observability（可观测性平台），"
        "群聊系统是实现「Agent 间通信透明化」的手段，不是独立的 IM 产品。"
        "简单说：监控是目的，群聊是手段。如果去掉群聊 UI，项目仍然成立（API + 事件流 + Token 仪表盘本身就是完整的产品）；"
        "但如果去掉 Token 监控和事件流，只剩群聊，项目就不成立了。"
    )

    para_fn("Q2：为什么用户不直接用 Grafana + Langfuse + OpenTelemetry + Datadog + LangSmith 的组合？", bold=True)
    para_fn(
        "因为这些工具各自解决不同层面的问题，拼在一起有 3 个致命缺陷：\n"
        "（1）数据孤岛——Grafana 管指标、Langfuse 管 LLM tracing、Datadog 管基础设施，三者的数据无法关联。"
        "OpenClaw 委托 OpenCode 执行任务这件事，在 Grafana 里看到的是「CPU 正常」，在 Langfuse 里看到的是「API 调用成功」，"
        "但你无法把它们连成一条线说「OpenClaw 在第 5 轮把任务 handoff 给了 OpenCode，OpenCode 用了 45K tokens 完成了编码」——这正是 MyAgentWatch 的核心价值。\n"
        "（2）部署成本——Langfuse 需要 PostgreSQL + ClickHouse + Redis，Datadog 按主机收费，Grafana 需要配置数据源和仪表盘。"
        "一个小团队要搭起这套组合需要几小时到几天，而 MyAgentWatch 只需 docker-compose up。\n"
        "（3）AI 专属指标的缺失——传统工具没有 Agent 状态机、没有 handoff 链路追踪、没有 Token 按 Agent 拆解、没有 thinking 流可视化。"
        "它们是通用工具，MyAgentWatch 是垂直工具。"
    )

    para_fn("Q3：真正不可替代的能力是什么？", bold=True)
    para_fn(
        "三项能力在目前市场上没有直接替代品：\n"
        "（1）Agent 间通信的透明化——把 Agent 之间的 IPC/ACP 通信「翻译」成人类可读的群聊消息，这是目前所有竞品（Multica、LangSmith 等）都没有的能力。\n"
        "（2）Token 到 Agent 的精确成本归因——不是笼统的「今天花了 $20」，而是「OpenClaw 的 plan Agent 花了 $5.30（其中 $1.71 是委托给 OpenCode 的子任务）」。\n"
        "（3）Agent 状态机 + 告警——6 状态精细模型（比 Multica 多 working 状态），综合 heartbeat + activity_log + last_seen_time 三大信号源判定。"
    )

    para_fn("Q4：目标用户到底是谁？", bold=True)
    bullet_fn("● 个人开发者（核心）：在本地监控自己的 AI 编程助手，了解 Token 消耗和 Agent 行为")
    bullet_fn("● 小团队（3-10 Agent，扩展目标）：多人多 Agent 的团队协作场景，群聊和通信透明化最有价值")
    bullet_fn("● AI 创业公司（未来）：向客户展示 Agent 运行的透明度和成本控制能力")
    bullet_fn("● 企业内部平台团队（远期）：作为内部 AgentOps 平台的基础设施")

    para_fn("Q5：如果只能保留一个功能，保留什么？", bold=True)
    para_fn(
        "Token 用量仪表盘。因为它是唯一直接关系到「钱」的功能。团队可能不在乎 Agent 怎么思考的，"
        "但一定在乎每个月花了多少 Token 费用、哪个 Agent/项目最费钱。这是对所有人都有价值的刚需。"
    )

    para_fn("Q6：你想做的是 Datadog for Agents、Slack for Agents，还是 Kubernetes for Agents？", bold=True)
    para_fn("Datadog for Agents 是最接近的类比——仪表盘、告警、成本分析、日志流一应俱全。Slack for Agents 是群聊的表达形式但不是本质。Kubernetes for Agents 是远期愿景（Agent 编排调度），但当前不做任务编排。")

    para_fn("Q7：这个项目是给「人」用的，还是给「Agent」用的？", bold=True)
    para_fn("给人用——人是最终消费者。但群聊的消息发送者是 Agent，所以 Agent 也是「用户」。更准确地说：人在监控 Agent，Agent 通过群聊互相通信，人可以通过群聊/CLI 干预 Agent。")

    # ═══════════════════════════════════════════════════
    # 14.2 架构设计（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.2 架构设计", level=2)

    para_fn("Q8：SQLite WAL 模式下的真实并发上限是多少？50+ Agent 真的能迁移吗？", bold=True)
    para_fn(
        "SQLite WAL 模式在 10 个 Agent 以下完全无压力（实测 5 Agent × 5s 采集 × 8 线程写入，每秒约 200-500 次 INSERT，"
        "WAL 模式下写入不阻塞读取）。50 Agent 时建议迁移 PostgreSQL，迁移成本可控：\n"
        "（1）所有 SQL 都是标准 SQL，无 ORM，迁移主要是改连接字符串和少量 SQL 方言差异（如日期函数）\n"
        "（2）提供 db.py 的 PostgreSQL 适配模块（已在路线图中），只需改一个 import\n"
        "（3）SQLite 和 PostgreSQL 可并行运行过渡期，逐步切换\n"
        "当前瓶颈不在 SQLite 本身，而在 collector.py 的单进程模型——如果未来需要水平扩展，需要把 collector 拆成独立服务。"
    )

    para_fn("Q9：双通道推送（WebSocket + SSE）如何保证一致性和避免重复推送？", bold=True)
    para_fn(
        "两个通道推送的内容在语义层面不重叠：WebSocket 推结构化状态变更（agent_update/stat_snapshot），"
        "SSE 推非结构化事件流（thinking/tool_call/response/handoff）。不存在「同一条数据从两个通道各推一次」的情况。\n"
        "端到端一致性策略为：前端以数据库为 source of truth。WebSocket 收到增量后立即更新 UI，"
        "但每 10s 拉一次全量快照校正。SSE 的事件流本质是追加日志，不需要和 WebSocket 一致。"
        "去重依靠数据库 UNIQUE(natural_key) + 前端 Set<msg_id> 双层保护。"
    )

    para_fn("Q10：collector.py 866 行，是否违反单一职责原则？未来要不要拆？", bold=True)
    para_fn(
        "承认这一点。866 行确实过长了。当前拆分方案已在计划中：\n"
        "（1）Collector 类保留调度编排职责（~200 行）\n"
        "（2）StateMachine 独立模块——_mark_stale_agents() 逻辑（~200 行）\n"
        "（3）TurnPersister 独立模块——_persist_turns() 逻辑（~200 行）\n"
        "（4）Archiver 独立模块——_archive_and_cleanup() 逻辑（~100 行）\n"
        "保留在单一文件中是因为项目尚在快速迭代期（从 5 月 15 日到 6 月 3 日每天都有 changelog），过早拆分会导致跨文件跳转成本。"
        "6 月 10 日任务系统 + Agent Backend 完成后即启动拆分。"
    )

    para_fn("Q11：为什么用 Flask + SocketIO 而不是 FastAPI + asyncio + Kafka？", bold=True)
    para_fn(
        "选择 Flask 的理由是务实而非教条：\n"
        "（1）项目启动时（2026-05），团队最熟悉 Flask 生态，FastAPI 的 async 优势在 SQLite 同步 IO 背景下无法发挥\n"
        "（2）Flask-SocketIO 是生态中最成熟的 Python WebSocket 库，FastAPI 的 WebSocket 支持相对原始\n"
        "（3）Kafka/Redis Streams/NATS 对 3-10 Agent 的场景是过度设计——引入这些中间件增加部署复杂度，但解决的是尚不存在的规模问题\n"
        "当系统真正遇到 Flask 的并发上限时（预计在 50+ Agent + 100+ 并发 SSE 连接时），迁移路径为："
        "Flask → FastAPI + uvicorn + Redis Pub/Sub 替代 SocketIO。这不是破坏性重写，因为路由和业务逻辑是分离的。"
    )

    para_fn("Q12：EventBus 是内存级还是持久化级？服务重启丢事件吗？", bold=True)
    para_fn(
        "当前 EventBus 是内存级实现（Python dict + list）。服务重启会丢失未消费的事件。"
        "这是一个已知的权衡：对于 3-10 Agent 的场景，重启频率极低（数天到数周一次），"
        "且事件数据同时在 activity_log 表中持久化，重启后前端拉取全量快照即可恢复。"
        "未来计划增加 Redis 作为 EventBus 后端，实现事件持久化和跨进程消费。"
    )

    para_fn("Q13：socketio.emit 放线程池只是缓解阻塞，真正的背压方案是什么？", bold=True)
    para_fn(
        "承认线程池只是权宜之计。真正的背压方案分三个层次：\n"
        "（1）当前 —— 线程池 + 队列上限（max_workers=8），超出后丢弃旧事件（非关键事件可容忍丢失）\n"
        "（2）近期 —— 按房间优先级分级：agent_update > alert_event > stat_snapshot\n"
        "（3）远期 —— 引入 Redis Streams 做事件缓冲，消费者按自身速率拉取（pull-based），天然解决背压"
    )

    # ═══════════════════════════════════════════════════
    # 14.3 数据模型与存储（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.3 数据模型与存储", level=2)

    para_fn("Q14：natural_key 去重会不会误伤合法重复事件？", bold=True)
    para_fn(
        "natural_key 的组成是 agent_id + session_id + seq，其中 seq 是同一个 Agent 在同一个 Session 内的递增序号。"
        "同一 Agent 在同一 Session 中产生两个语义相同但 seq 不同的 Turn（如两次「读取同一个文件」）会有不同的 natural_key，不会误伤。"
        "真正的风险是：数据源重启或重采导致 seq 不连续，新 Turn 可能与已存在的 Turn 有相同的 seq（概率极低，因为 seq 是日志文件的逻辑序号）。"
        "当前做法是 INSERT OR IGNORE + 应用层预查，先到先得。未来计划改为 INSERT OR REPLACE + 保留最新时间戳的版本。"
    )

    para_fn("Q15：gzip JSONL 归档后查询/搜索/回放怎么做？还是只能冷存储？", bold=True)
    para_fn(
        "当前归档是冷存储（能查但要手动解压）。已在路线图中的改进：\n"
        "（1）归档时同时写入轻量索引文件（agent_id + session_id + time_start → 归档文件 + 字节偏移量）\n"
        "（2）CLI 增加 myaw log replay --trace-id <id> 命令，自动定位归档文件 + seek 到指定偏移量，只解压相关 JSONL 行\n"
        "（3）长期方案：考虑引入 DuckDB 作为归档查询引擎，直接对 gzip JSONL 执行 SQL 查询，无需解压全量文件"
    )

    para_fn("Q16：VACUUM 在大库下会不会阻塞？", bold=True)
    para_fn(
        "会。SQLite VACUUM 需要复制整个数据库，期间写操作被阻塞。当前应对策略：\n"
        "（1）VACUUM 仅在归档/清理操作后触发（~每天一次），不在采集周期内执行\n"
        "（2）增加配置项 vacuum_interval，默认为 0（自动），可设为 -1（禁用自动 VACUUM，改用手动或 cron 触发）\n"
        "（3）迁移到 PostgreSQL 后，使用 pg_repack 替代 VACUUM（不锁表）"
    )

    para_fn("Q17：有没有 schema migration 机制？", bold=True)
    para_fn(
        "当前没有独立的 migration 框架。db.py 在每次启动时执行 CREATE TABLE IF NOT EXISTS + ALTER TABLE 语句，"
        "属于「启动时检查 + 补缺列」的轻量方案。这对于当前阶段足够（表结构变化不频繁），"
        "但未来字段重命名、类型变更等复杂迁移需要引入 Alembic 或类似的 migration 工具。已记录在技术债清单中。"
    )

    # ═══════════════════════════════════════════════════
    # 14.4 Agent 监控核心（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.4 Agent 监控核心", level=2)

    para_fn("Q18：状态机判定的准确率怎么样？会不会有状态震荡（flapping）？", bold=True)
    para_fn(
        "准确率的量化数据尚未收集（需要真实生产环境的标注数据作为 ground truth），这是必须诚实回答的。\n"
        "当前设计中的防震荡机制包括：\n"
        "（1）状态变更依赖多种信号源交叉验证（heartbeat + activity + last_seen），不是单一阈值触发\n"
        "（2）offline 判定需要 2 倍超时（默认 600s），且仅当 heartbeat 是最新信号时才触发，避免短时网络波动误判\n"
        "（3）status_since 记录进入当前状态的准确时间，metadata 存储 status_reason，方便事后审计\n"
        "但必须承认：idle 和 blocked 的边界在实际场景中确实存在灰色地带。目前的 idle 是不确定态，blocked 是明确异常态——"
        "这个区分的准确性需要通过真实运行数据来校准。"
    )

    para_fn("Q19：Agent 可以撒谎吗？比如一直发 heartbeat 但实际上卡死了？", bold=True)
    para_fn(
        "可以。当前系统信任 Agent 的上报。这就是为什么状态机综合了三个信号源——即使 Agent 持续发 heartbeat，"
        "如果 activity_log 显示长时间无新活动，系统也会将状态降级为 idle。但更深层的检测（Agent 发 heartbeat 但实际卡死）"
        "需要在 Agent 侧注入探针——比如定期执行轻量任务验证 Agent 的响应能力——这是 Agent Backend 抽象层要解决的问题。"
    )

    para_fn("Q20：如何检测死循环、prompt collapse、reasoning degeneration 这些真正的 AI 专有问题？", bold=True)
    para_fn(
        "这是 AI Agent 监控领域的前沿问题，也是 MyAgentWatch 区别于传统 APM 的核心方向。当前实现：\n"
        "（1）死循环检测——规则引擎监控「同一工具调用同一参数的重复次数」「同一文件在连续 N 个 turn 中被重复读取」「Token 消耗与任务进度的比率」，叠加触发 blocked 状态\n"
        "（2）prompt collapse——SSE 事件流中 thinking 内容长度/熵值持续下降 + 重复句式增多，触发「上下文退化」告警\n"
        "（3）reasoning degeneration——thinking 中出现高频的「let me try again」「I need to reconsider」「let me start over」等模式，触发「推理退行」信息通知\n"
        "这些检测目前基于规则（手写阈值），未来计划引入 anomaly detection（基于历史行为基线自动学习正常模式）。"
        "但必须诚实地说：这些都是启发式方法，有误报风险。当前阶段的目标不是零误报，而是「不漏报严重问题」——优先召回率。"
    )

    para_fn("Q21：blocked 和 error 的业务边界是什么？", bold=True)
    bullet_fn("● error —— Agent 遇到了一次性或短期的错误：模型调用失败、工具返回非零退出码、配置文件解析错误。属于「可自愈」或「需关注」的级别")
    bullet_fn("● blocked —— error 状态持续时间超过 2 倍超时阈值（默认 600s），说明 Agent 无法自行恢复。属于「需人工介入」的级别")
    bullet_fn("● 递进关系 —— error →（持续无恢复）→ blocked。就像 PagerDuty 的 warning → critical 升级机制")

    # ═══════════════════════════════════════════════════
    # 14.5 安全与权限（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.5 安全与权限", level=2)

    para_fn("Q22：有没有 RBAC、多租户、namespace 隔离？", bold=True)
    para_fn(
        "诚实回答：当前没有。v2.1 的权限模型是最简单的两级——前端免认证（部署在内网/本机）、API 需要 Bearer Token。\n"
        "这是有意为之的设计决策：在项目初期（< 50 用户），RBAC 的复杂度远超它带来的价值。\n"
        "多租户隔离已纳入中期路线图（6-7 月），届时会增加 workspace 概念：每个 workspace 有独立的 Agent 集、数据源、群聊频道，"
        "角色分为 admin（全部权限）/ member（读 + 写自己的 Agent）/ viewer（只读）。\n"
        "这也是 SQLite → PostgreSQL 迁移的关键触发点——SQLite 无法高效支持行级安全策略。"
    )

    para_fn("Q23：thinking 内容会不会有隐私或安全问题？Agent 输出中的 API Key 是否自动脱敏？", bold=True)
    para_fn(
        "当前系统原样保存 thinking 和 Agent 输出，不做自动脱敏。这是一个已知的安全边界。\n"
        "为什么不做自动脱敏：（1）脱敏规则高度依赖上下文（不同项目/语言/框架的密钥格式不同），通用规则误伤率太高；（2）thinking 内容被篡改后会影响审计完整性。\n"
        "替代方案：（1）文档中明确告知用户「系统会原样保存 Agent 输出」；（2）新增配置项 log_sensitive_filter 允许用户自定义正则脱敏规则（如 \\b(sk-[a-zA-Z0-9]{32,})\\b）；（3）前端页面增加「敏感内容警告」标记。\n"
        "对于企业场景，建议部署在内网（不对公网暴露），且通过 Nginx 反向代理 + IP 白名单加固。"
    )

    para_fn("Q24：恶意 Agent 伪造消息/状态/handoff，系统能识别吗？", bold=True)
    para_fn(
        "当前不能。系统信任所有通过合法 PAT 认证的 Agent 上报的数据。\n"
        "防御层次规划：（1）签名验证——Agent 上报数据时附带 HMAC 签名，服务端验证签名后再写入（要求 Agent 侧植入 SDK）；（2）行为基线——Agent 的行为模式和正常基线偏差过大时自动标记为 suspicious；（3）审计告警——对异常的 handoff 链（如 A→B→C→A 形成环）触发安全告警。\n"
        "但必须承认：在 Agent 数量少（< 10）且团队内部信任的场景下，恶意 Agent 不是当前主要威胁。这个优先级排在数据完整性之后。"
    )

    # ═══════════════════════════════════════════════════
    # 14.6 可观测性与自我监控（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.6 可观测性与自我监控", level=2)

    para_fn("Q25：谁来监控 MyAgentWatch 自己？如果它崩了，告警还发得出去吗？", bold=True)
    para_fn(
        "这是可观测性领域的经典问题——「谁来监控监控系统」。当前方案：\n"
        "（1）MyAgentWatch 自身作为 system 类型的 Agent 注册在 agents 表中，采集自己的 CPU/内存/磁盘/运行时长，通过 health_check 端点暴露\n"
        "（2）外部健康检查——check.py 脚本可被 cron 调用，定期检查 http://localhost:10000/api/health，异常时发送独立通知（邮件/webhook）\n"
        "（3）告警独立于 MyAgentWatch——关键告警规则同时在 MyAgentWatch 和外部 cron 中配置（双通道），确保 MyAgentWatch 自身宕机时告警不丢失\n"
        "但必须诚实地说：这个方案对于 SLA 99.9% 的场景（如金融交易监控）是不够的。生产级部署建议配合外部 watchdog（如 systemd 自动重启）和使用独立告警通道（如 PagerDuty webhook 直接从 Agent 侧发出）。"
    )

    para_fn("Q26：有没有 queue lag / event latency / dropped events / reconnect count 这些 SLI？", bold=True)
    para_fn(
        "当前没有系统化的 SLI 面板。这些指标部分可以通过现有数据推算（activity_log 的 timestamp 差值推算事件延迟），"
        "但没有统一收集和展示。已在中期路线图规划：\n"
        "（1）新增 sli_metrics 表——记录采集延迟、推送延迟、队列深度、丢事件计数、重连次数\n"
        "（2）新增 /api/sli 端点——返回最近 1h/24h/7d 的 SLI 趋势\n"
        "（3）前端新增「系统健康」页面——展示 MyAgentWatch 自身的运维指标\n"
        "这是从 dashboard 进化到 observability platform 的关键一步。"
    )

    # ═══════════════════════════════════════════════════
    # 14.7 工程化与质量（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.7 工程化与质量", level=2)

    para_fn("Q27：单元测试覆盖率多少？有没有 CI/CD？", bold=True)
    para_fn(
        "诚实回答：当前测试覆盖率不足 30%。核心模块（collector.py 的状态机逻辑、pricing.py 的成本计算）有测试覆盖，"
        "但数据源适配器（依赖真实 SQLite 文件）和前端代码缺乏系统化测试。\n"
        "CI/CD 尚未建立——当前开发模式是本地开发 + 手动测试 + changelog 记录。"
        "这是项目最大的技术债，也是从「个人项目」走向「团队项目」必须跨越的门槛。"
        "已在 6 月路线图中列为 P0 基础设施项：GitHub Actions CI（lint + unit test + integration test）+ 最低覆盖率门槛 60%。"
    )

    para_fn("Q28：为什么前端坚持「零构建工具链」？是工程优势还是技术债？", bold=True)
    para_fn(
        "两者都有。当前阶段（一人开发、快速迭代）确实是优势——修改 JS 文件 → 刷新浏览器 → 立即看到效果，"
        "没有 webpack/vite 的构建等待时间。但必须承认：当代码量突破某个阈值后（当前约 3000 行 JS），零构建工具链带来三个问题："
        "（1）没有模块化管理，appState 全局对象的命名冲突风险；（2）没有 TypeScript 类型检查，重构时容易引入 bug；"
        "（3）无法做 tree-shaking 和代码分割，首次加载体积大。\n"
        "迁移计划：6 月任务系统上线后，前端代码量预计增长 50%+，届时引入 Vite + vanilla JS（不引入 React/Vue 框架，保持轻量），"
        "用 ES modules 替代全局变量，用 TypeScript 替代纯 JS。这是渐进的工程化改进，不需要重写。"
    )

    para_fn("Q29：collector.py 的事务边界怎么定义？有没有 deadlock 风险？", bold=True)
    para_fn(
        "SQLite 的锁粒度是数据库级别（不是行级锁）。当前每个 database() context manager 内部自动提交，"
        "多个写入操作串行化（WAL 模式下写入不阻塞读取，但写入之间是串行的）。理论和实测均未遇到死锁。\n"
        "但有一个已知的并发风险：_persist_turns() 中的批量写操作（executemany）可能持有写锁较长时间（大量 Turn 时可能 1-3 秒），"
        "期间 collect_all() 中的其他写入操作（_persist_agents、_persist_data）被阻塞。"
        "解决方案：将大批量写入拆分到更小的批次（每 500 条提交一次）已在代码中实现。"
    )

    # ═══════════════════════════════════════════════════
    # 14.8 产品战略（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.8 产品战略", level=2)

    para_fn("Q30：项目的北极星指标是什么？", bold=True)
    para_fn(
        "当前定义的核心指标（按优先级）：\n"
        "（1）Token 成本可追溯率——有多少百分比的 Token 消耗能精确归属到具体的 Agent / Session / 任务。目标 > 95%。\n"
        "（2）故障发现时间（TTD, Time to Detect）——从 Agent 出现异常到用户收到通知的延迟。目标 < 30s。\n"
        "（3）Agent 间通信的透明化覆盖率——有多少次 Agent handoff/委托被记录并可视化。目标 100%（所有通信都在群聊中可见）。\n"
        "这三个指标直接对应用户的三个核心痛点：省钱（1）、稳定性（2）、透明化（3）。"
    )

    para_fn("Q31：核心护城河是什么？如果 OpenAI/Anthropic 官方下场做 Agent observability，怎么应对？", bold=True)
    para_fn(
        "护城河有三层：\n"
        "（1）Agent 通信总线——把 Agent 之间的 ACP/IPC 通信可视化。这不是 LLM 厂商的核心能力（他们的 focus 在模型质量而非 Agent 编排），"
        "而且这是跨厂商的需求——一个团队可能同时用 Anthropic 的 Claude Code 和 DeepSeek 的编码 Agent，需要统一通信层。\n"
        "（2）厂商中立定价模型——8 家厂商 37 个模型的价格对比和成本归因，官方工具只会覆盖自家模型。\n"
        "（3）极简部署——docker-compose up 即用 vs 官方工具通常需要注册云账号、配置 API key、数据上传云端。\n"
        "如果 OpenAI/Anthropic 真的下场：短期会有冲击，但它们的工具大概率只监控自家的 Agent（Claude Code 的 Dash 只展示 Claude 的 Token），而 MyAgentWatch 是多厂商 Agent 的统一监控面。"
    )

    para_fn("Q32：Agent 社交到底是刚需还是伪需求？", bold=True)
    para_fn(
        "坦诚地说：对于个人开发者，Agent 社交不是刚需。对于多 Agent 团队（3+ Agent 并行工作），它是刚需——"
        "但「刚需」的不是「聊天」功能，而是「Agent 间通信的可视化和审计」。群聊只是这个能力的 UI 表达。\n"
        "打个比方：Docker 的「刚需」是容器化，不是 Docker Desktop 的 GUI。如果用户不喜欢群聊 UI，"
        "完全可以用 CLI（myaw chat / myaw feed）或 API 来查看 Agent 间通信。群聊只是最直观的表达方式。"
    )

    para_fn("Q33：开源商业化路径是什么？", bold=True)
    para_fn(
        "当前阶段（v2.1）专注于产品验证和社区反馈，不考虑商业化。未来可能的路径：\n"
        "（1）开源核心（Open Core）——基础监控 + 群聊开源免费，高级告警 + 多租户 + SSO 作为企业版\n"
        "（2）SaaS 托管版——面向不想自己部署的用户，按 Agent 数收费\n"
        "（3）插件市场——第三方数据源适配器、告警规则模板、前端 Widget 的交易平台\n"
        "但必须强调：这些是远期愿景（至少 2027），当前一切注意力在产品本身。"
    )

    # ═══════════════════════════════════════════════════
    # 14.9 真实验证与现状（保留旧版详细回答）
    # ═══════════════════════════════════════════════════
    heading("14.9 真实验证与现状", level=2)

    para_fn("Q34：有没有真实用户在用？有哪些验证过的数据？", bold=True)
    para_fn(
        "诚实回答当前状态（2026 年 6 月 9 日）：\n"
        "（1）开发和测试环境——项目在开发者本地持续运行，监控 5 个 Agent（Claude Code 的 plan/build/explore + OpenCode 实例），日均产生 200-500 条 token_records + 50-100 条 conversation_turns\n"
        "（2）已在实际开发中验证的功能：Token 成本监控（准确追踪了 5-6 月的 Token 消费）、SSE 事件流（实时展示 Agent 的 thinking 和 tool_call）、群聊（Agent 间 handoff 消息的紫色卡片展示）\n"
        "（3）尚未在真实多用户环境中验证的功能：告警规则引擎的误报/漏报率、大规模 Agent（10+）的并发性能、CLI 客户端的跨平台兼容性\n"
        "（4）需要用户反馈验证的方向：群聊在真实团队协作中的使用频率、通知收件箱的噪音水平、Token 仪表盘的 UI 易用性\n\n"
        "这是一个诚实的自我评估：MyAgentWatch v2.1 是一个功能完整的 Alpha 产品，"
        "在开发者自己的环境中运行良好，但尚缺乏外部用户的验证数据。"
        "6 月的首要目标是完成 Agent Backend 抽象层和任务系统，然后寻求第一批外部用户（3-5 个团队）的试用反馈。"
    )

    para_fn("Q35：删掉所有花哨 UI 之后，还剩下什么硬价值？", bold=True)
    para_fn(
        "这是一个很好的「剥离测试」。如果去掉前端所有 UI，只保留：\n"
        "（1）REST API（40+ 端点）——所有 Token 查询、Agent 状态、会话历史、告警记录均可通过 API 访问\n"
        "（2）SSE 事件流——持续推送 Agent 活动事件，可接入任意消费端\n"
        "（3）CLI 客户端（11 个命令）——终端内完成所有核心操作\n"
        "（4）collector 采集引擎 + 状态机 + 告警引擎 + 日聚合\n\n"
        "剩下的是一个完整的 Agent 数据采集和分析引擎，可以用 API 驱动任何前端（Grafana 面板、自定义 Dashboard、CI/CD 集成）。"
        "群聊和事件流 UI 是锦上添花，核心引擎才是雪中送炭。"
        "这说明 MyAgentWatch 的架构确实是前后端分离的——前端是可替换的，后端是独立的。"
    )

    # ═══════════════════════════════════════════════════
    # 14.10-14.25 答辩清单新增板块（简洁版）
    # ═══════════════════════════════════════════════════
    heading("14.10 数据采集与适配器（答辩新增）", level=2)

    para_fn("Q36：新数据源接入到底要改多少代码？", bold=True)
    para_fn("三步：(1) 新建适配器文件实现 SourceInterface 三个方法；(2) @register_source 装饰器注册到 SOURCE_REGISTRY；(3) config.yaml 加一行 type 声明。核心代码（collector/API/前端）一行不改。做到了「对扩展开放，对修改封闭」。")

    para_fn("Q37：不同 CLI 日志格式不一样怎么解析？数据源格式变了怎么应对？", bold=True)
    para_fn("每个适配器封装自己的解析逻辑，对 Collector 输出统一的 CollectedData 结构。格式变更：connect() 做兼容检查、字段映射集中适配器内部、未知字段被忽略（graceful degradation）。")

    para_fn("Q38：怎么处理重复上报、脏数据、部分字段缺失？", bold=True)
    para_fn("重复：INSERT OR IGNORE + UNIQUE 约束 + 内存 Set 预查。脏数据：必填为空跳过、时间戳异常用当前时间替代、Token 负数设 0。字段缺失：使用 DEFAULT 或 NULL，查询用 COALESCE 处理，前端显示「-」。")

    heading("14.11 告警与运维（答辩新增）", level=2)

    para_fn("Q39：4 条默认告警阈值对所有团队都适用吗？误报漏报怎么控制？", bold=True)
    para_fn("不一定——阈值需通过 config.yaml 定制。当前优先召回率（不漏报严重问题），容忍一定误报。未来改进：静默窗口（夜间降灵敏度）、分级告警、基于历史基线动态阈值。")

    para_fn("Q40：告警支持静默窗口、分级、合并吗？触发后如何通知？", bold=True)
    para_fn("当前不支持静默窗口和告警合并——已列入中期路线图。通知路径：alert 表写入 → WebSocket alert_event → 前端 Toast + 收件箱通知。独立于 MyAgentWatch 的告警通道（如 webhook）正在规划中。")

    heading("14.12 CLI 客户端深度（答辩新增）", level=2)

    para_fn("Q41：为什么 CLI 只用标准库不用 requests？跨平台兼容性怎样？", bold=True)
    para_fn("零依赖是最高优先级——CLI 需在任何 Python 3.10+ 环境直接运行。urllib.request 足够（GET/POST/DELETE + Bearer Token + 超时）。代价是代码更啰嗦但换来零安装。Windows/macOS/Linux 均已测试通过。")

    para_fn("Q42：心跳 15 秒怎么定的？多开 daemon 怎么办？config.json 明文存 token 安全吗？", bold=True)
    para_fn("15 秒平衡精度和负载——5 秒太频繁、60 秒太慢（状态机超时 300s）。多开 daemon 被状态机自然处理——同一 Agent 多次心跳只保留最后一次。config.json 建议设 600 权限，未来支持 keyring 存储。")

    heading("14.13 前端深度（答辩新增）", level=2)

    para_fn("Q43：8 个页面哪个是主入口？高频和低频怎么区分？", bold=True)
    para_fn("仪表盘是主入口（4 卡片 + Agent 表）。高频：仪表盘（全局）、Token 面板（成本）、事件流（排障）。低频：拓扑图（关系分析）、日志查看器（深度排查）。导航栏按使用频率排序。")

    para_fn("Q44：前端去重 Set 无限增长怎么办？大数量下渲染性能？", bold=True)
    para_fn("去重 Set 上限 5000 条 ID，LRU 淘汰。Chart.js Canvas 渲染大数量优于 DOM。事件流虚拟滚动（只渲染可视行）。D3 DAG 在 > 500 节点时退化——当前场景（< 100 节点）正常。")

    heading("14.14 性能与扩展（答辩新增）", level=2)

    para_fn("Q45：3-10 Agent 和 50+ Agent 的边界在哪里？", bold=True)
    para_fn("50 Agent 时瓶颈依次：collector 单进程采集（<1s→5-10s）→ SQLite 写锁争抢 → WebSocket 全量广播。逐一方案：collector 多进程、PostgreSQL 迁移、增量推送替代全量快照。")

    para_fn("Q46：SSE 长连接多了有压力吗？慢客户端怎么处理？", bold=True)
    para_fn("Flask 线程模型——50 SSE 连接 + 8 采集 + HTTP ≈ 60 线程，内存压力不大（~1MB/线程）。慢客户端：SSE 写入超时 30s 后断开，客户端自动重连。远期用 Redis pub/sub 替代线程池 push。")

    heading("14.15 安全（答辩新增）", level=2)

    para_fn("Q47：PAT 令牌为什么带 myaw_ 前缀？只存哈希、明文只返回一次的设计思路？", bold=True)
    para_fn("myaw_ 前缀便于识别和审计（日志中快速定位自己的令牌）。SHA-256 哈希存储——即使数据库泄露攻击者也无法还原明文。明文只返回一次——用户需自行保管，丢失后只能重新生成。支持撤销令牌（DELETE /api/users/<id>/token）。")

    para_fn("Q48：有没有 audit log 不可篡改设计？如何平衡透明化和安全性？", bold=True)
    para_fn("当前无不可篡改设计。改进计划：WAL 日志 hash chain、关键审计事件 append-only、定期导出到独立只读存储。透明化 vs 安全性的平衡：用户自定义脱敏规则 + 内网部署 + Nginx IP 白名单，必要时牺牲部分透明化换取安全。")

    heading("14.16 工程化（答辩新增）", level=2)

    para_fn("Q49：有没有 benchmark / chaos engineering？如何验证 collector 正确性？", bold=True)
    para_fn("当前都没有——诚实回答。计划：(1) synthetic workload generator 模拟 N 个 Agent 产生事件测性能；(2) fault injection 模拟数据源断开/格式变化/锁冲突；(3) collector 正确性通过比较源数据库和聚合数据库的数据一致性来验证。")

    para_fn("Q50：服务重启后状态还能恢复吗？数据会丢吗？", bold=True)
    para_fn("所有状态持久化在 SQLite——重启后 collector 从 last_sync_time 恢复增量采集，状态机从已有数据重新评估。内存 EventBus 事件会丢（非关键——activity_log 已持久化，前端重新拉取）。数据库写操作在 transaction 中——要么全部成功要么全部回滚，不丢数据。")

    heading("14.17 竞品（答辩新增）", level=2)

    para_fn("Q51：为什么不直接用 Multica / Langfuse / Grafana？你的定位是替代还是补位？", bold=True)
    para_fn("补位，不替代。Multica 管任务编排（MyAgentWatch 管监控），Langfuse 做 LLM tracing（MyAgentWatch 做 Agent 间通信可视化），Grafana 管机器指标（MyAgentWatch 管 Agent 专属指标）。用户可以同时使用所有工具——MyAgentWatch 填补它们之间的空白。")

    para_fn("Q52：如果竞品也加群聊+事件流+告警，你怎么办？大厂护城河是什么？", bold=True)
    para_fn("群聊和事件流是产品表达，真正的护城河是 Agent 适配器生态和厂商中立的数据模型。竞品加功能容易，但跨 8 家厂商的统一数据模型和定价表需要长期积累。速度是关键——先发优势建立社区和生态。")

    heading("14.18 路线图与商业化（答辩新增）", level=2)

    para_fn("Q53：6 月三目标优先级为什么这样排？中期目标会不会太散？", bold=True)
    para_fn("Agent Backend 抽象层是底座（先统一接口）→ 任务系统是核心缺失（补 Multica 有的能力）→ 群聊增强是差异化武器（让群聊从「能看」变「能用」）。中期目标（多语言/PWA/插件市场）都是已有核心的外延，不涉及架构重写，不会太散。")

    para_fn("Q54：谁会付费？个人订阅、团队订阅还是企业订阅？如何证明值得长期投入？", bold=True)
    para_fn("付费预测：企业平台团队（多租户+审计）> AI 创业公司（向客户展示透明度）> 个人（托管版）。定价参考：个人 $9/月/Agent、团队 $49/月/10 Agent、企业定制。Agent 数量指数增长——每个开发者 3-5 Agent、每团队 20-50 Agent。2026 下半年到 2027 上半年是 Agent 可观测性从 nice-to-have 变 must-have 的转折窗口。")

    heading("14.19 部署运维（答辩新增）", level=2)

    para_fn("Q55：Windows/macOS/Linux 都能部署吗？出故障排查路径是什么？", bold=True)
    para_fn("推荐 Docker（三平台统一）。纯本地：pip install + python app.py 即可。排查路径：check.py → /api/health → collector 日志 → sqlite3 \"PRAGMA integrity_check\"。最易出错：data_sources.db_path 路径错误、alert_rules 阈值不匹配使用模式。")

    para_fn("Q56：运维成本真的低吗？日常维护要做什么？", bold=True)
    para_fn("日常几乎零维护——数据自动归档 + VACUUM。唯一需关注：磁盘空间（归档目录增长）、定价表更新（厂商调价时更新 pricing 表）、配置文件备份。多实例部署每个 OpenCode 实例对应一个 MyAgentWatch 实例。")

    heading("14.20 最刁钻追问（答辩新增）", level=2)

    para_fn("Q57：这是不是你自己最需要所以才做出来的？会不会只是开发者自嗨？", bold=True)
    para_fn("是的——项目确实起源于开发者自身需求。但最好工具往往来自开发者解决自己问题（Git 来自 Linus、Docker 来自 dotCloud）。关键是能否让其他开发者也觉得「这正是我需要的」。当前自嗨风险存在——需要外部用户反馈验证。")

    para_fn("Q58：群聊、动态、好友是不是在稀释主线？删掉一半功能你删什么？", bold=True)
    para_fn("群聊本质是 Agent 通信监控的 UI 表达——不是社交功能。删一半：好友、动态、通讯录（Agent 通信不需要社交化）、拓扑 DAG（nice-to-have）。留一个页面：仪表盘（信息密度最高）。留一个指标：今日 Token 成本。")

    para_fn("Q59：如果别人说「只是把日志换了个好看的壳」「不是刚需」「竞品已经有了」？", bold=True)
    para_fn("(1)「换壳」——如果只是换壳，能做到跨 Agent 通信可视化和 Token 到 Agent 的成本归因吗？日志做不到。(2)「不是刚需」——对单 Agent 不是，对 5 Agent 团队绝对是。Agent 越多需求越刚性。(3)「竞品有了」——哪个竞品同时做到 Agent 间通信实时可视化 + 8 厂商 37 模型多 Agent Token 归因？")

    heading("14.21 终极总结", level=2)

    para_fn("Q60：北极星指标 / 成功标准 / 最想让评委记住的一句话？", bold=True)
    para_fn(
        "北极星指标：Token 成本可追溯率 > 95%。成功标准：用户用后 (1) Token 成本降 20%+；(2) 异常发现时间从数小时降到数分钟；(3) 每天至少打开一次。"
        "最想让评委记住：「MyAgentWatch 让 AI Agent 不再是一个黑盒——你知道每个 Agent 在想什么、在做什么、花了多少钱。就像 Kubernetes 让微服务可管理一样，MyAgentWatch 让 AI Agent 可观测。」"
    )

    para_fn("Q61：这个项目是在做监控工具，还是 AI Agent 时代的 Kubernetes？", bold=True)
    para_fn("当前是 Datadog for Agents（监控工具），愿景是 AI Agent 时代的可观测性基础设施。不急于成为 Kubernetes——先做好「看得见」这一步。两条路技术深度不同、竞争对手不同、融资逻辑不同。当前阶段的选择是：先做好监控，让用户离不开，再考虑编排。")

    doc.add_page_break()
