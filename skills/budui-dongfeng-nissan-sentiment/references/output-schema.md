# 舆情数据输出格式规范

本文件定义 `budui-dongfeng-nissan-sentiment` 技能的 JSON 输出契约，供下游报告生成技能消费。

## 顶层结构

```json
{
  "meta": {
    "skill": "budui-dongfeng-nissan-sentiment",
    "version": "1.0.0",
    "generated_at": "2026-09-23T08:50:00+08:00",
    "car_model": "天籁",
    "query_keywords": ["东风日产 天籁"],
    "platforms_searched": ["微博", "汽车之家", "懂车帝", "小红书", "抖音", "知乎", "百度贴吧"],
    "total_items": 25,
    "sentiment_summary": {
      "positive": 10,
      "neutral": 8,
      "negative": 7
    }
  },
  "items": [ ... ]
}
```

## meta 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| skill | string | 是 | 固定值 `budui-dongfeng-nissan-sentiment` |
| version | string | 是 | 技能版本号 |
| generated_at | string (ISO 8601) | 是 | 数据生成时间，北京时间 |
| car_model | string | 是 | 监控车型名称 |
| query_keywords | string[] | 是 | 实际使用的搜索关键词列表 |
| platforms_searched | string[] | 是 | 本次搜索覆盖的平台列表 |
| total_items | integer | 是 | items 数组长度 |
| sentiment_summary | object | 是 | 情感分布统计 |
| sentiment_summary.positive | integer | 是 | 正面条目数 |
| sentiment_summary.neutral | integer | 是 | 中性条目数 |
| sentiment_summary.negative | integer | 是 | 负面条目数 |

## items 数组元素结构

```json
{
  "id": "item-001",
  "platform": "汽车之家",
  "source_url": "https://...",
  "title": "天籁2.0T高速油耗实测...",
  "content_snippet": "跑了500公里高速，平均油耗7.2L，比预期低不少...",
  "author": "车友小王",
  "published_at": "2026-09-22T14:30:00+08:00",
  "sentiment": "positive",
  "sentiment_score": 0.75,
  "topics": ["油耗", "高速性能"],
  "engagement": {
    "likes": 328,
    "comments": 45,
    "shares": 12
  }
}
```

## items 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 唯一标识，格式 `item-NNN` |
| platform | string | 是 | 来源平台名称 |
| source_url | string | 否 | 原文链接，无法获取时为 null |
| title | string | 是 | 帖子/文章标题 |
| content_snippet | string | 是 | 内容摘要，100-300字 |
| author | string | 否 | 发布者昵称，无法获取时为 null |
| published_at | string (ISO 8601) | 否 | 发布时间，无法获取时为 null |
| sentiment | enum | 是 | `positive` / `neutral` / `negative` |
| sentiment_score | float | 是 | 情感强度 0.0-1.0，neutral 范围 0.3-0.7 |
| topics | string[] | 是 | 话题标签，1-5个 |
| engagement | object | 否 | 互动数据，无法获取时为 null |
| engagement.likes | integer | 否 | 点赞数 |
| engagement.comments | integer | 否 | 评论数 |
| engagement.shares | integer | 否 | 转发/分享数 |

## 情感判定规则

### positive（正面）
- 明确表扬、推荐、满意表达
- 优点列举、好评体验分享
- 对比竞品后选择该车型
- sentiment_score ≥ 0.6

### neutral（中性）
- 纯事实陈述、参数对比、价格信息
- 提问求助、客观测评无明显倾向
- 新闻转载、官方公告转述
- 0.3 ≤ sentiment_score < 0.6

### negative（负面）
- 投诉、质量问题反馈、维权
- 明确不满、后悔购买、劝退
- 与竞品对比后的负面评价
- sentiment_score < 0.3

## 平台枚举

以下为优先搜索平台列表，实际输出以搜索结果为准：

- 微博
- 抖音
- 小红书
- 汽车之家
- 懂车帝
- 易车
- 百度贴吧
- 知乎
- B站
- 今日头条
- 腾讯新闻
- 网易汽车

## metadata.quantitative_data 字段规范（v0.2.0 新增）

当执行量化数据增强时，在 `metadata` 中新增 `quantitative_data` 对象，包含以下三个子结构：

### quantitative_data.koubei_scores

```json
{
  "koubei_scores": {
    "autohome_score": 4.55,
    "dongchedi_score": 4.67,
    "yiche_score": 8.55,
    "fault_per_100": 180,
    "net_recommendation": "杰兰路净推荐值中大型纯电轿车第一",
    "top_positive_tags": [
      {"tag": "座椅舒适", "count": 1065},
      {"tag": "后排空间够用", "count": 953},
      {"tag": "续航里程大", "count": 567}
    ],
    "top_negative_tags": [
      {"tag": "风噪大", "count": 197},
      {"tag": "储物空间小", "count": 188},
      {"tag": "车轮设计不好看", "count": 121}
    ],
    "competitors": {
      "零跑C10": {"autohome_score": 4.50, "dongchedi_score": 4.03, "fault_per_100": 163},
      "银河E8": {"autohome_score": 4.59},
      "深蓝SL03": {"yiche_score": 8.42}
    }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| autohome_score | float | 否 | 汽车之家车主口碑评分 |
| dongchedi_score | float | 否 | 懂车帝车主评分 |
| yiche_score | float | 否 | 易车车主评分 |
| fault_per_100 | integer | 否 | 百车故障数（2-12个月新车质量研究） |
| net_recommendation | string | 否 | 第三方净推荐值调研结果 |
| top_positive_tags | array | 否 | 高频好评标签，每项含 tag(关键词) 和 count(提及次数) |
| top_negative_tags | array | 否 | 高频差评标签，同上 |
| competitors | object | 否 | 竞品口碑数据，key为竞品名称，value为同结构评分对象 |

### quantitative_data.sales_trend

```json
{
  "sales_trend": {
    "monthly_data": [
      {"month": "2026-01", "retail": 520, "terminal": null},
      {"month": "2026-08", "retail": 928, "terminal": null}
    ],
    "latest_ranking": {
      "overall_rank": 288,
      "segment_rank": 20,
      "segment_name": "中大型车",
      "manufacturer_share_pct": 3.86
    },
    "trend_summary": "自4月峰值1635辆连续4个月环比下滑，8月较7月降26.3%",
    "decline_reasons": ["新车红利消退", "N6内卷分流", "5月召回事件"]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| monthly_data | array | 是 | 月度销量数组，每项含 month(YYYY-MM)、retail(零售量)、terminal(终端量，可选) |
| latest_ranking | object | 否 | 最新月份排名信息 |
| latest_ranking.overall_rank | integer | 否 | 整体市场排名 |
| latest_ranking.segment_rank | integer | 否 | 细分市场排名 |
| latest_ranking.segment_name | string | 否 | 细分市场名称 |
| latest_ranking.manufacturer_share_pct | float | 否 | 占厂商份额百分比 |
| trend_summary | string | 否 | 趋势文字总结 |
| decline_reasons | string[] | 否 | 销量下滑归因（基于公开信息推断） |

### quantitative_data.competitor_comparison

```json
{
  "competitor_comparison": {
    "matrix": [
      {"dimension": "汽车之家评分", "n7": "4.55", "competitor_a": "4.50", "competitor_b": "4.59", "competitor_c": "-"},
      {"dimension": "百车故障数", "n7": "180", "competitor_a": "163", "competitor_b": "-", "competitor_c": "-"}
    ],
    "competitors": ["零跑C10", "银河E8", "深蓝SL03"],
    "n7_advantages": ["双平台评分领先", "净推荐值第一", "品控稳定"],
    "n7_disadvantages": ["销量持续下滑", "风噪/储物为高频共性槽点"]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| matrix | array | 是 | 对比矩阵，每行为一个维度，列包含 n7 和各竞品值，"-"表示数据缺失 |
| competitors | string[] | 是 | 竞品名称列表，与 matrix 列顺序对应 |
| n7_advantages | string[] | 否 | N7竞争优势总结 |
| n7_disadvantages | string[] | 否 | N7竞争劣势总结 |

### metadata.notes

量化数据来源标注字段，格式示例：

```json
{
  "notes": "量化数据采集于2026-09-23，来源：汽车之家口碑页、懂车帝车型页、易车排行榜、杰兰路调研报告、乘联会零售数据。竞品数据完整度不一，缺失项以'-'标记。"
}
```

## Excel 导出格式规范（v0.2.0 新增）

当用户要求 Excel 导出时，基于同一 JSON 数据源生成 `.xlsx` 文件，包含以下 Sheet：

| Sheet名称 | 数据来源 | 行数说明 | 格式要点 |
|-----------|----------|----------|----------|
| 舆情明细 | items 全量 | header + items.length | 情感标签列条件着色(正面绿#C6EFCE/中性黄#FFEB9C/负面红#FFC7CE)；首行自动筛选 |
| 口碑评分 | quantitative_data.koubei_scores | 视数据而定 | 分区展示(N7评分区/标签词频区/竞品对比区)，各区带子标题 |
| 销量趋势 | quantitative_data.sales_trend | 视数据而定 | 含环比变化列，趋势总结和归因单独行展示 |
| 竞品对比 | quantitative_data.competitor_comparison | 视数据而定 | 优势项绿底、劣势项红底 |

通用格式：表头深蓝底(#4472C4)白字加粗；所有数据单元格细边框；长文本列自动换行；列宽适配内容。

## 下游消费指引

1. 读取 `meta.car_model` 确定报告主题车型
2. 使用 `meta.sentiment_summary` 生成情感分布图表
3. 遍历 `items` 按 `sentiment` 分组，提取典型声音作为报告素材
4. 按 `topics` 聚合可生成话题热度分析
5. `engagement` 非空时可用于识别高影响力舆情条目
6. `published_at` 可用于时间趋势分析
7. **（v0.2.0）** `metadata.quantitative_data` 存在时，可直接用于生成口碑评分图表、销量趋势折线图、竞品对比雷达图
8. **（v0.2.0）** `.xlsx` 文件可作为独立交付物供业务人员直接查看，无需解析 JSON
