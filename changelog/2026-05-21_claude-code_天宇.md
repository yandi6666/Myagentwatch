# 2026-05-21 — 状态机重构 + 资源监控 + 快捷操作

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 一、Agent 状态机重构

按用户 7 条规则完全重写 `_mark_stale_agents`：

| 状态 | 颜色 | 触发条件 |
|------|------|---------|
| active 运行正常 | 🟢 | 有心跳 + 无错误 + 模型OK |
| idle 等待 | 🟡 | 新发现待首心跳 / 心跳过期不确定 / 无法确认是否有问题 |
| error 错误 | 🔴 | 模型缺失（需模型的agent未配置）/ 运行时错误日志 |
| offline 离线 | 🟣 | 来源断连/移除 / 已安装未启动 / 等待超过5分钟无心跳 |
| removed | — | agent从数据源彻底移除时才从仪表盘消失 |

### 改动文件

| 文件 | 改动 |
|------|------|
| `collector.py` | `_mark_stale_agents` 完全重写：来源→活动→错误→模型四级判定 |
| `collector.py` | 新增 `_agent_needs_model()` — system 类 agent 不需要模型 |
| `collector.py` | `_persist_agents`：新 agent 初始 idle（黄），已存在的不覆盖状态 |
| `queries.py` | 4 处查询改为 `status != 'removed'`，返回全部非移除 agent |
| `config.yaml` | 新增 `heartbeat_timeout: 300` |

### 状态判定优先级
1. 来源断连/移除 → offline
2. 有近期活动 + 无错误 + 模型OK → active
3. 有近期活动 + 有错误/缺模型 → error
4. 有历史活动但过期 → idle（超时后降级 offline）
5. 从未活动 + 新建 → idle
6. 从未活动 + 旧agent → offline（安装未启动）

---

## 二、资源概览真实化

| 文件 | 改动 |
|------|------|
| `index.html` | 资源概览 HTML 改为动态占位（CPU/内存/磁盘替代原来的 CPU/内存/网络） |
| `app.js` | 新增 `updateResources()` — 每 5 秒拉 `/api/health` 更新进度条 |

`/api/health` 端点已存在（psutil），直接复用。

---

## 三、快捷操作功能化

| 按钮 | 功能 |
|------|------|
| 🔄 刷新所有节点状态 | 立即重渲染快照数据 |
| 📥 导出全集群状态报告 | 下载当前快照 JSON |
| 🔄 全量重启 | toast：需 Agent 支持远程控制 |
| ⏸ 暂停所有 | toast：需 Agent 支持远程控制 |

---

## 四、群聊在线列表更新

- 群聊右侧「在线 Agent」→ 显示全部非移除 agent + 状态标签
- 接口 `/api/agents` 也加 `status != 'removed'` 过滤

---

## 五、状态标签统一

- "等待中" → "等待"
- 全四种状态：运行正常 / 等待 / 错误 / 离线
