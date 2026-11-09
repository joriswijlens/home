---
name: deye-cloud-scenarios
description: "DeyeCloud 业务场景助手 — 基于云端 Deye Open MCP（deye_open）的上层场景剧本。把官方 49 个 MCP 工具按真实业务流编排成 SOP，AI 照剧本组合调用并解读成用户能看懂的结论。Use when a user asks in natural language about station health, generation trends, battery strategy, real-time status, device diagnostics, or wants to compare stations. 触发词：电站巡检、电站健康、今天发了多少电、发电曲线、历史发电、电池策略、SOC、充放电、实时功率、设备离线、采集器故障、电站对比。"
version: v261109
author: DeyeCloud Portal
---

# DeyeCloud 业务场景助手（基于云端 MCP）

> 本 skill 是**上层场景剧本**，基于云端 Deye Open MCP（`deye_open`）的官方工具，按真实业务流编排成 SOP。每个场景定义：触发词 → 工具组合顺序 → AI 解读策略。AI 照剧本组合调用工具，把原始数据解读成用户能看懂的结论。
>
> **前置依赖**：本 skill 假设 AI 客户端已配置 `deye_open` MCP 服务器（`https://developer.deyecloud.com/openmcp/mcp`）。所有工具调用需先经 `get_access_token` 拿到 `access_token`，后续工具传入该 token 与 `data_center`。每次调用计入 OpenAPI 配额。

## 🚀 首次使用引导

用户不需要提前知道 stationId。AI 应在首次对话时自动引导：

1. 若用户未提供凭据 → 引导用户去 `https://developer.deyecloud.com/app` 注册应用，拿 AppId/AppSecret
2. 若不知道 `data_center` → 调 `list_data_centers()`（无需参数）获取可用数据中心列表
3. 调 `get_access_token(app_id, app_secret, email, password, data_center)` 拿 token
4. 调 `list_stations(page=1, size=10, access_token, data_center)` 列出电站，展示给用户选择
5. 用户选择后，记住 `stationId` 与 `data_center`，后续对话自动携带

**`data_center` 有效值**（短 key，不是完整名称）：

| 数据中心 | `data_center` 值 |
|---|---|
| EU | `eu` |
| Americas | `am` |
| India | `india` |

**用户也可以直接说电站名**，AI 调 `list_stations` 搜索匹配即可。

---

## 📋 场景目录

| # | 场景 | 状态 | 说明 |
|---|------|------|------|
| 1 | 电站巡检 | ✅ 已验证 | 设备在线率 + 告警 + 实时功率流 |
| 2 | 历史发电分析 | ✅ 已验证 | 日/月发电量趋势 |
| 3 | 电池充放电策略 | ✅ 已验证 | TOU配置 + SOC曲线 + 充放电时间线 |
| 4 | 实时监控 | ✅ 已验证 | 实时功率流 + SOC + 并离网 |
| 5 | 设备运维诊断 | ✅ 已验证 | 设备清单 + 告警 + 实时数据下钻 |
| 6 | 电站对比 | ✅ 已验证 | 多电站发电量/效率横向对比 |


---

## 场景 1：电站巡检

> 用户想一键了解某电站当前是否健康、设备在线情况、有无告警、实时功率流。

### 触发词

电站巡检、电站健康、电站概况、查看电站、给我看看这个电站、station overview、check my station、station health、电站状态、电站怎么样

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 判断/分支 |
|------|------|------|----------|-----------|
| 0 | `get_access_token` | app_id/app_secret/email/password/data_center | `access_token` | 整个会话复用，不重复换 |
| 1 | `list_stations` | page=1, size=10 | 电站列表（id、名称、装机容量、在线状态） | 列出电站让用户选；记下 `stationId` |
| 2 | `get_station_latest` | station_id | 实时功率流：光伏/电网/负载/电池/储能 PCS 功率 + 并离网状态 + 电池 SOC | 功率字段为 null → 设备可能离线 |
| 3 | `list_station_devices` | station_id, page=1, size=100 | 全设备清单：SN、设备类型、在线/离线 | 统计在线率 = 在线数 / 总数 |
| 4 | `station_alert_list` | body={stationId, startTimestamp, endTimestamp} | 电站级告警列表（故障/警告/提示 × 设备） | 需传时间范围（10位Unix秒）；若有活跃故障 → 标红置顶 |
| 5（可选） | `device_alert_list` | body={deviceSn, startTimestamp, endTimestamp}, language=zh | 单设备告警下钻 | 仅当步骤 4 发现某设备异常且用户追问时调用 |

### AI 解读策略

拿到上述数据后，AI 应组织成**结构化健康报告**，不是平铺数据：

**报告结构**：
1. **总体状态一句话**：电站名 + 总体状态（🟢 健康 / 🟡 有警告 / 🔴 有故障 / ⚫ 部分离线）
2. **实时功率流**：光伏 X kW → [电池充/放 X kW] → 电网 买/卖 X kW → 负载 X kW；标注并网/离网
3. **设备健康度**：采集器 N/N、电池 N/N、PCS N/N（在线/总数）；离线设备清单（SN + 类型），红色标记
4. **告警摘要**：故障 N 条 / 警告 N 条 / 提示 N 条；列出最严重的 3 条（设备 SN + 告警名 + 等级 + 时间）
5. **建议动作**：
   - 有故障 → "建议立即处理：[SN] [告警名]"
   - 有离线设备 → "建议检查采集器/网络：[SN]"
   - 全健康 → "电站运行正常，无需处理"

**判定阈值**（参考，可按装机容量调整）：
- 在线率 < 100% 但 ≥ 90% → 🟡 轻微异常
- 在线率 < 90% → 🔴 多设备离线，需处理
- 有"故障"级告警 → 至少 🟡，若故障设备数 ≥ 1 且影响核心设备（PCS/电池）→ 🔴
- 无告警且全在线 → 🟢

**异常数据处理**：
- `get_station_latest` 某字段为 null → 可能传感器故障或设备离线，不要当"0 kW 正常发电"解读，应提示"数据缺失，可能设备离线"
- 告警列表为空但设备离线 → 提示"有离线设备但无告警记录，可能是采集器断连未上报"
- ⚠️ 站级告警（station_alert_list）与设备级告警（device_alert_list）可能数据不一致：同一时间窗口内站级 total=0 但设备级有告警记录。如需完整告警信息，建议以 device_alert_list 为准逐设备查询

### 对应云端 MCP 工具

| 工具 | OpenAPI 端点 | 备注 |
|------|------|------|
| `get_access_token` | `POST /v1.0/account/token` | 便捷工具，换 token |
| `list_stations` | `POST /v1.0/station/list` | 便捷工具，分页 |
| `get_station_latest` | `POST /v1.0/station/latest` | 便捷工具，扁平入参 |
| `list_station_devices` | `POST /v1.0/station/device` | 便捷工具，入参为 stationIds 数组 |
| `station_alert_list` | `POST /v1.0/station/alertList` | 标准封装，body 传参，需 startTimestamp/endTimestamp |
| `device_alert_list` | `POST /v1.0/device/alertList` | 标准封装，body 传参，带 language |

---


## 场景 2：历史发电分析

> 用户想看发电趋势、发电用途分布、异常天标记。

### 触发词

发电曲线、历史发电、发电趋势、generation、power analysis、发电量统计、这周发多少、这个月发电、今天发了多少电

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 备注 |
|------|------|------|----------|------|
| 0 | `get_access_token` | — | token | — |
| 1 | `list_stations` | page=1, size=10 | stationId | 列出电站让用户选 |
| 2 | `station_history` | body={stationId, startAt, endAt, granularity=2} | 逐日发电/用电/买电/卖电/充电/放电 | granularity 枚举见下方 |
| 3（可选） | `station_history` | body={stationId, startAt, endAt, granularity=1} | 单日5分钟级功率曲线 | 用户问某日发电曲线时用 |

### ⚠️ station/history 参数格式（已验证）

```
POST /v1.0/station/history
{
  "stationId": 1760000000001,     // integer, 电站ID
  "startAt": "2026-08-20",        // string, 日期格式 YYYY-MM-DD
  "endAt": "2026-08-28",           // string, 日期格式 YYYY-MM-DD
  "granularity": 2                 // integer, 粒度枚举
}
```

**granularity 枚举值**：
- `1` — 5分钟级功率曲线（同日 startAt/endAt 传同一天）
- `2` — 日汇总（每日发电量/用电量/充放电量/买卖电量）

> ⚠️ granularity=3（月汇总）入参日期格式为 `YYYY-MM`（如 `"2026-08"`），最多查 12 个月。
> ⚠️ granularity=4（年汇总）入参日期格式为 `YYYY`（如 `"2026"`），查年汇总数据。
> ⚠️ 如果月度数据返回空（total=0），可能是电站当月无汇总产出，建议用 granularity=2 取日数据后 AI 自行按月聚合。
> ⚠️ 日期格式与 granularity 的对应关系（已验证）：
> - granularity=1/2：`startAt`/`endAt` 格式为 `YYYY-MM-DD`
> - granularity=3：`startAt`/`endAt` 格式为 `YYYY-MM`（如 `"2026-08"`）
> - granularity=4：`startAt`/`endAt` 格式为 `YYYY`（如 `"2026"`）

**granularity=2 返回字段含义**（每个 stationDataItems 元素）：

| 字段 | 含义 | 单位 |
|------|------|------|
| `generationValue` | 发电量 | kWh |
| `consumptionValue` | 负载用电量 | kWh |
| `gridValue` | 电网卖电(馈电) | kWh |
| `purchaseValue` | 电网购电 | kWh |
| `chargeValue` | 电池充电量（含 PV 充电和市电充电） | kWh |
| `dischargeValue` | 电池放电量 | kWh |
| `fullPowerHours` | 等效满发小时数 | h |
| `year/month/day` | 数据日期 | — |

> ⚠️ **字段语义说明**：`chargeValue` 包含 PV 充电和市电（电网）充电的总量（实测：发电 0 时充电 1.4 kWh，充电量可大于发电量）。`purchaseValue` 只统计电网→负载直接供电，不含电网→电池充电。完整能量流需用 granularity=1 功率数据积分。

### AI 解读策略

- **发电趋势**：按日列出发电量，标注峰值日/谷值日
- **发电用途分布**：自用 = 发电 - 卖电；上网 = 卖电字段
- **用电来源分布**：光伏自用 + 电池放电 + 电网买电
- **异常天标记**：发电量环比骤降 > 30% → 标红"可能是遮挡/故障/天气"，结合场景 1 的告警交叉验证
- **月度汇总**：可用 granularity=3 查月汇总数据（格式 YYYY-MM）；若返回空，用 granularity=2 取日数据后 AI 自行按月聚合

**报告结构**：趋势描述 + 日/月汇总表 + 用途分布 + 异常天 + 建议

### 对应工具
`list_stations` / `station_history`

---

## 场景 3：电池充放电策略

> 用户想了解电池当前策略、SOC 曲线、充放电时间线。

### 触发词

电池策略、充放电、SOC、battery strategy、charge discharge、储能策略、电池今天充了多少

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 判断/分支 |
|------|------|------|----------|-----------|
| 0 | `get_access_token` | — | token | — |
| 1 | `list_stations` | — | stationId | — |
| 2 | `list_station_devices` | station_id, size=100 | 设备清单 | 找出 PCS/逆变器 SN（设备类型 PCS 或 INVERTER） |
| 3 | `config_tou` | body={deviceSn} | TOU 配置：时段表 + 充放电策略 + 启用状态 | 设备需在线；离线返回 `2104006 device offline`；对 BATTERY 等不支持 TOU 的设备返回 `2106001 config point not supported` |
| 4 | `config_battery` | body={deviceSn} | 电池配置：SOC 上下限、容量、电池类型 | 同上 |
| 5 | `config_system` | body={deviceSn} | 系统模式（工作模式、能量模式等） | 同上 |
| 6 | `device_history` | deviceSn, startAt/endAt(YYYY-MM-DD), granularity=2 | 逐日充放电量 | 分析充放电模式 |
| 7（可选） | `device_history` | deviceSn, startAt/endAt(YYYY-MM-DD), granularity=1, measurePoints=[...] | 分钟级功率曲线 | 分析充放电时段 vs 电价峰谷 |
| 8（可选） | `strategy_dynamic_control_read` | body={deviceSn} | 读取动态控制策略 | 部分设备可能不支持动态控制（需后端确认错误码） |

### ⚠️ 接口限制（已逐设备验证）

**config 系列（tou/battery/system）**：
- 需设备在线，离线返回 `2104006 device offline`
- 部分在线设备返回 `2106001 config point not supported`（设备型号不支持该配置项；旧版文档称 2101022 已过时）

**device/measurePoints**：
- COLLECTOR / BATTERY 类型返回 `2104005 device not supported`（设备类型本身不支持）
- PCS 类型正常返回测点列表（如 2345678901 返回 226 个测点）
- INVERTER 类型正常返回测点列表（measurePoints/history/latest 正常；alertList 偶发 2101040，见下方验证结果）

**device/latest**：
- 仅有缓存的设备返回数据，无缓存的返回空 `deviceDataList`（不报错）
- 测试环境 8 台设备仅 1 台 PCS 有 latest 数据

**device/alertList / device/history**：
- PCS 类型正常工作
- INVERTER 设备大部分功能正常（measurePoints/history/latest 正常；alertList 偶发 2101040，见下方验证结果）

**strategy/dynamicControl/read**：
- 需用 `strategy/dynamicControl/readResult` 轮询结果
- 部分设备可能返回 `2101040`（strategy read 偶发，见下方验证结果）

### 📋 设备接口验证结果（2026-10-12 实测）

以下为真实 API 调用验证的设备行为，取代旧版"已知问题"表格：

| 设备类型 | device/latest | device/measurePoints | device/alertList | device/history | 说明 |
|---------|--------------|--------------------|-----------------|---------------|------|
| PCS | ✅ 有缓存数据 | ✅ 返回测点 | ✅ 返回告警 | ✅ 返回历史 | 功能完整 |
| INVERTER | ✅ 可返回数据（含 91 测点） | ✅ 返回测点（如 139 个） | ⚠️ 偶发 2101040（按设备） | ✅ 返回历史 | 个别设备 alertList 返回 2101040，同站其他设备正常 |
| COLLECTOR | 空 deviceDataList | 2104005 device not supported | ✅ 返回告警 | 空 | measurePoints 不支持此设备类型 |
| BATTERY | 空 deviceDataList | 2104005 device not supported | ✅ 返回告警 | 空 | measurePoints 不支持此设备类型；对 BATTERY 调 config_tou 返回 2106001 config point not supported |

> ⚠️ `2101040 device not found`（station/device 有但 device/alertList 查不到）为**按设备偶发**问题：同一电站中部分设备正常返回告警，个别设备返回 2101040（2026-10-15 R6 测试复现，requestId `74cc9e7b`，设备 `2302248678`）。其他 device/* 接口（latest、measurePoints、history）对该设备正常。可能原因：设备告警索引未同步或设备类型与告警服务映射缺失。
>
> **AI 处理策略**：遇到 `2101040` 时提示"该设备暂无告警数据记录（服务端索引未同步）"，不要将其判断为设备不存在或离线——以 `station/device` 返回的 `connectStatus` 为准判断在线状态。遇到 `2104005` 时提示"该设备类型不支持 measurePoints 查询"；遇到 `2106001` 时提示"该设备不支持此配置项"；遇到空 `deviceDataList` 时提示"设备无缓存实时数据"。

### AI 解读策略

- **今日充放电时间线**：从 granularity=1 功率数据中提取电池充放电时段，绘制时间线
- **SOC 曲线**：标注 SOC 高低点，是否触达上下限
- **TOU 配置**：展示时段表 + 充放电策略 + 启用状态
- **策略评估**：充电时段是否在低电价时段、放电时段是否在高电价时段
- **优化建议**：若充放电时段与电价峰谷错位 → 提示"建议调整 TOU 时段配置"

**报告结构**：策略配置 + 充放电时间线 + SOC 关键节点 + 优化建议

### 对应工具
`list_station_devices` / `config_tou` / `config_battery` / `config_system` / `device_history` / `strategy_dynamic_control_read` / `strategy_dynamic_control_read_result`

---


## 场景 4：实时监控

> 用户想看当前功率、并离网、电池 SOC 等实时状态。

### 触发词

实时功率、当前状态、现在发多少电、real-time、live、实时数据、现在电站怎么样

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 备注 |
|------|------|------|----------|------|
| 0 | `get_access_token` | — | token | — |
| 1 | `list_stations` | page=1, size=10 | stationId | 列出电站让用户选 |
| 2 | `get_station_latest` | station_id | 电站实时功率流 + 电池 SOC | 功率字段为 null → 设备可能离线 |
| 3（可选） | `device_latest` | body={"deviceList":["sn1","sn2"]} | 多设备实时数据（批量≤10） | 需先 `list_station_devices` 拿 SN；入参字段名是 `deviceList`（camelCase），不是 `device_list` |
| 4（可选） | `station_alert_list` | body={stationId, startTimestamp, endTimestamp} | 实时告警 | 时间范围用近 24 小时 |

### AI 解读策略

- **实时功率仪表盘**：光伏 / 电网 / 负载 / 电池功率 + 方向（充/放）
- **电池 SOC + 充放电方向**
- **数据时效性**：检查 `lastUpdateTime`，若距今超过 1 小时 → 提示"数据可能延迟，设备可能离线"
- **异常提示**：功率全为 null → 电站离线；光伏为 0 但负载有值 → 夜间或设备故障

**报告结构**：仪表盘式呈现 + 数据时效性 + 异常提示

### 对应工具
`list_stations` / `get_station_latest` / `device_latest` / `station_alert_list`

---

## 场景 5：设备运维诊断

> 用户怀疑设备故障、离线、采集器问题，想定位根因。

### 触发词

设备离线、采集器故障、逆变器数据、device、diagnostics、offline、故障、设备怎么了、某设备有问题

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 判断/分支 |
|------|------|------|----------|-----------|
| 0 | `get_access_token` | — | token | — |
| 1 | `list_station_devices` | station_id, size=100 | 全设备清单 + connectStatus | 统计在线率，定位离线设备 SN |
| 2 | `station_alert_list` | body={stationId, startTimestamp, endTimestamp} | 电站级告警 | 找出故障/警告设备 |
| 3 | `device_latest` | body={"deviceList":["故障SN"]} | 故障设备实时数据 | 看异常值（功率 0、温度过高、SOC 异常）；入参字段名是 `deviceList`（camelCase） |
| 4 | `device_alert_list` | body={deviceSn, startTimestamp, endTimestamp}, language=zh | 单设备告警下钻 | 看历史告警 + 恢复时间 |
| 5（可选） | `device_measure_points` | body={deviceSn} | 测点定义 | 不确定设备有哪些数据时先查测点；COLLECTOR 类型不支持 |
| 6（可选） | `device_history` | body={deviceSn, startAt, endAt, granularity=2} | 逐日趋势 | 看故障前后数据变化 |
| 7（可选） | `device_history` | body={deviceSn, startAt, endAt, granularity=1, measurePoints=[...]} | 分钟级功率曲线 | 看故障发生时刻数据跳变 |

### ⚠️ device/history 参数格式（已验证）

```
POST /v1.0/device/history
{
  "deviceSn": "2345678901",       // string, 设备序列号
  "startAt": "2026-08-20",         // string, 日期 YYYY-MM-DD
  "endAt": "2026-08-20",           // string, 日期 YYYY-MM-DD（同日=查单日）
  "granularity": 1,                // integer, 1=分钟级(需传measurePoints), 2=日汇总
  "measurePoints": ["BatteryPower", "TotalGridPower"]  // granularity=1 时必传
}
```

- granularity=1：返回 dataList，每条含 time(Unix秒) + itemList(key/value/unit)
- granularity=2：返回 dataList，每条含 time(日期) + itemList(汇总字段)
- granularity=2 返回的 `ElectricityPurchasing` **不含电网→电池充电电量**

### AI 解读策略

- **设备总览**：在线/离线/告警数量
- **离线设备清单**：SN + 类型 + 离线时长（若可推断）
- **故障设备根因推断**：交叉验证告警 + 实时数据 + 历史趋势
  - 功率骤降 + 有告警 → 硬件故障
  - 功率 0 + 无告警 + 离线 → 采集器断连
  - 温度过高告警 → 散热/环境问题
- **建议操作**：重启/检查网络/联系售后

**报告结构**：设备总览 + 离线清单 + 故障根因 + 建议

### 对应工具
`list_station_devices` / `station_alert_list` / `device_latest` / `device_alert_list` / `device_measure_points` / `device_history`

---


## 场景 6：电站对比

> 用户想横向对比多电站发电效率。

### 触发词

对比、比较、多电站、compare、comparison、哪个性价比高、哪个电站发得多

### 工具组合 SOP

| 步骤 | 工具 | 入参 | 拿到什么 | 备注 |
|------|------|------|----------|------|
| 0 | `get_access_token` | — | token | — |
| 1 | `list_stations` | page=1, size=100 | 全电站列表 + 装机容量 + 在线状态 | — |
| 2 | 对每个电站调 `station_history` | body={stationId, startAt, endAt, granularity=2} | 各电站逐日发电/用电 | 对比发电量，不含收益 |
| 3（可选） | `station_list_with_device` | page=1, size=50 | 各电站设备数 | 辅助判断规模 |

> ⚠️ 电站数多时注意配额，建议限定对比 3-5 个电站。每次 `station_history` 计 1 次调用。

### AI 解读策略

- **多电站发电横向对比表**：电站名 / 装机容量 / 时段发电量 / 单位装机发电量（kWh/kW）
- **单位装机容量排名**：kWh/kW 排序，反映发电效率
- **效率差异分析**：高效率电站 vs 低效率电站，可能原因（朝向/遮挡/设备年龄/策略）
- ⚠️ **不计算收益**：OpenAPI 无收益接口，仅对比发电量

**报告结构**：对比表 + 效率排名 + 差异分析

### 对应工具
`list_stations` / `station_history` / `station_list_with_device`

---

## 📌 全场景共通约定

- **认证**：每个会话开始调一次 `get_access_token`，后续复用 `access_token` + `data_center`，不重复换
- **电站定位**：用户未指定电站时先 `list_stations` 列出电站让用户选
- **设备 SN**：需要 deviceSn 的场景（3/5）先 `list_station_devices` 拿 SN
- **配额意识**：批量循环调用（场景 6）注意电站数量，避免超 QPM
- **只读优先**：全部场景均为只读查询，不产生控制指令
- **控制权限按设备隔离**：若用户需要下发控制命令（如 TOU 更新），注意写权限是按设备粒度的，同站兄弟机可能一台可写一台被拒（返回 `2101027 permission denied`）。下发前先用 `config_tou` 读测试确认设备可控制
- **命令串行**：同一设备同一时间只能执行一条命令，并发下发第二条会返回 `2104004 command concurrent running` 被拒绝。必须等前一条完成后再发下一条

## 📎 API 参数备忘（已验证）

### station/history

```
POST /v1.0/station/history
Body: { stationId: int, startAt: string, endAt: string, granularity: int }
granularity: 1=帧级功率(5分钟), 2=日汇总, 3=月汇总, 4=年汇总
  - granularity=1: startAt 格式 YYYY-MM-DD（仅 startAt，查单日）
  - granularity=2: startAt/endAt 格式 YYYY-MM-DD（最多 31 天）
  ⚠️ granularity=2 时间范围超过 31 天报 2101012
  - granularity=3: startAt/endAt 格式 YYYY-MM（如 "2026-08"，最多 12 个月）
  - granularity=4: startAt/endAt 格式 YYYY（如 "2026"）
```

### station/history/power

```
POST /v1.0/station/history/power
Body: { stationId: int, startTimestamp: int(10位秒), endTimestamp: int(10位秒) }
返回: stationDataItems (5分钟级功率数据)
```

### device/history

```
POST /v1.0/device/history
Body: { deviceSn: string, startAt: "YYYY-MM-DD", endAt: "YYYY-MM-DD", granularity: int, measurePoints: [string] }
granularity: 1=分钟级(需传measurePoints), 2=日汇总(不传measurePoints)
granularity=2 返回字段: ChargingCapacity/DischargingCapacity/Production/GridFeed-in/Consumption/ElectricityPurchasing
⚠️ granularity=2 时传 measurePoints 会报 2101006 "should be null"；measurePoints 仅在 granularity=1 时传
⚠️ ElectricityPurchasing 不含电网→电池充电电量
⚠️ ChargingCapacity 包含 PV 充电和市电充电的总量，不限于 PV 充电
```

### station/device

```
POST /v1.0/station/device
Body: { stationIds: [int], page: int, size: int }
返回: deviceListItems[], 含 deviceSn/deviceType/connectStatus(0=离线,1=在线)/collectionTime
⚠️ 入参是 stationIds 数组，不是单个 stationId
⚠️ MCP 有两个工具：便捷工具 `list_station_devices`（入参 station_id 单值，内部转为数组）；标准封装 `station_device`（入参 body，需直接传 {"stationIds": [...]}）
```

### station/listWithDevice

```
POST /v1.0/station/listWithDevice
Body: { page: int, size: int, deviceType: string(可选) }
返回: stationList[], 每个电站含 deviceTotal(int) + deviceListItems[]
⚠️ 设备列表字段名是 deviceListItems，不是 deviceList
```

### station/alertList

```
POST /v1.0/station/alertList
Body: { stationId: int, startTimestamp: int(10位秒), endTimestamp: int(10位秒), page: int, size: int }
⚠️ 必须传 startTimestamp 和 endTimestamp
⚠️ startTimestamp 与 endTimestamp 差值不得超过 180 天
```

### config/tou | config/battery | config/system

```
POST /v1.0/config/{tou|battery|system}
Body: { deviceSn: string }
⚠️ 设备需在线，离线返回 2104006 device offline
⚠️ 部分在线设备返回 2106001 config point not supported（设备型号不支持该配置项）
```

### device/measurePoints

```
POST /v1.0/device/measurePoints
Body: { deviceSn: string, deviceType: string(可选) }
⚠️ COLLECTOR/BATTERY 类型返回 2104005 device not supported
⚠️ INVERTER 类型 measurePoints 正常返回测点列表（alertList 偶发 2101040，见下方验证结果）
⚠️ PCS 类型正常返回 measurePoints 数组
```
### device/latest

```
POST /v1.0/device/latest
Body: { deviceList: [string] }
返回: deviceDataList[], 含 deviceSn + itemList(key/value/unit)
⚠️ 入参字段名是 deviceList（camelCase），不是 device_list（snake_case）
⚠️ 批量查询每次最多 10 台设备
⚠️ MCP 有两个工具：
  - get_device_latest（便捷工具）：参数名 device_list，内部自动转换为 {"deviceList": [...]}
  - device_latest（标准封装）：参数名 body，需直接传 {"deviceList": [...]}
  若用标准封装 device_latest 但传 body={"device_list": [...]}，服务端报 2101008 invalid param type（HTTP 500）
```

### strategy/dynamicControl/read

```
POST /v1.0/strategy/dynamicControl/read
Body: { deviceSn: string }
返回: orderId
→ 用 strategy/dynamicControl/readResult (body={orderId}) 轮询结果
⚠️ 设备需在线
```

## 🔒 安全

- 所有场景默认只读，不产生控制指令
- token 仅作为工具参数传入，不写入本 skill 或聊天历史
- 若某工具返回"无数据"，可能是电站无该数据类型或时间范围超保留期，应如实提示而非臆造数据

