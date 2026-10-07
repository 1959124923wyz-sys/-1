# 德国犯罪地图：16州数据源与覆盖矩阵

更新：2026-10-07

## 目标与口径

最终产品保持一张德国全国地图，只分“暴力犯罪 / 财产犯罪”两个一级模式。数据固定分为三层：

- **官方结构面**：BKA PKS 2025 县/市（Kreis / kreisfreie Stadt）年度统计，负责全国完整覆盖。
- **90天动态点**：警方/检方公开通报，负责“最近发生了什么”。它不是全量案件数据库，点少不能解释为犯罪少。
- **高精度层**：只有存在足够细、可持续更新的官方数据时才启用。Berlin 是当前模板。

覆盖等级只表示**本站目前的数据采集能力**，不表示治安好坏：
- **高覆盖**：结构面 + 州/城市细分官方数据 + 直接警方通报。
- **标准覆盖**：结构面 + 州级直接警方通报适配器。
- **基础覆盖**：结构面 + 全国公开警方通报抓取。

## 当前基线（90天事件库）

截至本轮检查，cases.json 共 580 条并全部完成地理编码。按 state 字段统计：
NRW 151、Berlin 108、Niedersachsen 70、Rheinland-Pfalz 61、Baden-Württemberg 58、Hessen 55、Bayern 26、Thüringen 20、Schleswig-Holstein 8、Hamburg 6、Mecklenburg-Vorpommern 6、Bremen 5、Saarland 2、Sachsen 1、Brandenburg 0、Sachsen-Anhalt 0，另有 3 条 state 未识别。

这个分布说明当前全国动态点层存在明显的**来源偏差**：不能继续用“关键词命中多少”近似各州真实犯罪量。下一阶段改为“按州/警务机构白名单直接抓取”。

## 16州矩阵

| 州 | 当前等级 | 可达到 | 已验证的高价值来源 | 近期点源策略 | 优先级 |
|---|---|---|---|---|---|
| Berlin | 高覆盖 | 高覆盖 | Polizei Berlin PKS / Polizeimeldungen / 已接官方盗窃开放数据 | 现有直接归档 | 模板 |
| Brandenburg | 基础 | 标准 | Polizei Brandenburg 分地区 RSS + 官方 PKS（DL-DE/BY-2.0） | 直接 RSS | **P1** |
| Sachsen | 基础 | 标准 | Medienservice Sachsen + Kriminalitätsatlas 2025（到 Gemeinde） | 各 Polizeidirektion RSS/归档 | **P2** |
| Sachsen-Anhalt | 基础 | 标准 | Polizei Sachsen-Anhalt 大型官方新闻归档 + 地区 PKS | 直接官方归档 | **P3** |
| Bayern | 基础 | 标准 | Bayerische Polizei RSS + 各 Polizeipräsidium 新闻 | RSS + 归档 | **P4** |
| Hamburg | 基础 | 标准 | Polizei Hamburg Newsroom + Stadtteilatlas 2025 | 直接 Newsroom | **P5** |
| Baden-Württemberg | 基础 | 标准 | Sicherheitsbericht 2025 + 各 Polizeipräsidium 发布 | 机构白名单 | P6 |
| Bremen | 基础 | 标准 | Polizei Bremen Pressestelle + Bremen/Bremerhaven PKS | 直接归档，Ort/ Zeit 结构较好 | P7 |
| Hessen | 基础 | 标准 | Polizei Hessen Presse-Feed + 各 Präsidium PKS | 扩展现有 RSS | P8 |
| Mecklenburg-Vorpommern | 基础 | 标准 | Landespolizei MV 当前/归档发布 + PKS | 官方页/机构白名单 | P9 |
| Rheinland-Pfalz | 基础 | 标准 | 州 PKS + Mainz/Koblenz/Trier/Kaiserslautern/Ludwigshafen 等区域 PKS | Präsidium 白名单 | P10 |
| Niedersachsen | 基础 | 标准 | 州 PKS + 大量地方警务机构发布 | 机构白名单 | P11 |
| Nordrhein-Westfalen | 基础 | 标准 | NRW PKS + 各 Kreispolizeibehörde 发布 | KPB 白名单；现有点已较多 | P12 |
| Saarland | 基础 | 标准 | Saarland 官方明确使用 Presseportal 汇总全州警情 | 警务机构白名单 | P13 |
| Schleswig-Holstein | 基础 | 标准 | LKA PKS 2025 + XLS Tabellenanhang | 机构白名单 | P14 |
| Thüringen | 基础 | 标准 | 各 Landespolizeiinspektion 发布 / Presseportal | LPI 白名单 | P15 |

## 实施顺序

第一批只做 5 个适配器：**Brandenburg → Sachsen → Sachsen-Anhalt → Bayern → Hamburg**。

原因不是主观偏好，而是“缺口 × 官方来源质量 × 实现成本”的组合：
- Brandenburg 和 Sachsen-Anhalt 当前90天库为 0，Sachsen 仅 1 条，明显不是实际犯罪为零；
- 三州均已有可系统遍历的官方发布源；
- Bayern 面积和人口大，当前仅 26 条，覆盖偏低；
- Hamburg 是高密度城市州，Newsroom 与 Stadtteilatlas 都适合做第二个城市级样板。

第二批再做 Bremen / Hessen / Baden-Württemberg / Mecklenburg-Vorpommern，之后处理 NRW / Niedersachsen / Rheinland-Pfalz 等“来源机构多、现有 Presseportal 点已较多”的州。

## 统一适配器契约

每个州适配器只输出同一种事件结构：

```
event_id
event_date
publication_date
state
city
location
lat / lon
geocode_precision
category[]
subcategory
severity
source_agency
source_url
source_type
date_confidence
privacy_protected
```

关键规则：
1. 同一事件允许多标签，不因为跨类别去重而删除 homicide / robbery 等标签。
2. 90天历史回填与每日增量任务分开；每日只抓最近约7天重叠窗口。
3. 地理编码失败有 TTL，不能永久缓存失败；经纬度必须通过德国国界和州边界校验。
4. 性犯罪默认降精度显示；公开报道也不在地图上暴露可识别受害者信息。
5. 某州抓取失败时保留上一版数据，不能用空数据覆盖线上。
6. “0个公开通报点”只能显示为“未发现/覆盖不足”，不能显示为“0犯罪”。

## UI 原则

地图视觉优先级固定为：**地图 > 当前地区核心数字 > 覆盖状态 > 事件列表**。

不再新增常驻的大型说明框。覆盖状态只用一行紧凑标签呈现，例如：
- `高覆盖 · 柏林细分统计 + 官方90天热力 + 警方通报`
- `基础覆盖 · 全国PKS + 公开通报；点位非全量`

更完整的方法说明放在折叠信息或项目文档中，不占地图画面。
