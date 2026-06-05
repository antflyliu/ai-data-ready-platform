# AI Data Readiness Platform 可扩展与优化分析

来源文档：`docs/从 ChatGPT-OpenDataLoader PDF分析到 AI Data Readiness Platform.md`

## 结论

这份对话文档的主线判断是成立的：从 **RAG 文档清洗** 切入，再升级到 **高质量数据集建设**，最后演进为 **AI Data Readiness Platform / CleanOps**，方向比单纯做 PDF 解析器或数据清洗脚本更有商业价值。

但当前方案有一个核心风险：它把很多长期能力同时放进早期蓝图，包括结构化数据治理、标准合规中心、行业规则包、数据交换、Agent CleanOps、数据集流通和质量技术基础行业包。方向可以保留，但必须重新分层，否则第一版会变成“大而全但不可交付”的平台。

最优策略应是：

```text
先做能被客户验收的 RAG 文档数据集就绪产品
再把质量评分、追溯、报告、规则包沉淀成平台内核
最后再扩展到结构化数据、行业标准合规和数据集生命周期运营
```

## 当前方案最有价值的部分

### 1. 切入口选择正确

RAG 文档清洗是合理的第一入口，原因是：

- 企业已经在做知识库、智能客服、企业大模型，需求真实。
- PDF / Word / PPT / HTML 文档质量问题直接影响 RAG 效果，痛点容易解释。
- 页眉页脚、页码、水印、重复段落、表格丢失、chunk 质量差等问题可观测、可报告。
- 相比传统数据治理，AI 知识库数据质量仍是增量市场。

需要坚持一个边界：第一阶段不是“全类型数据清洗平台”，而是“企业 RAG 文档数据集就绪工具”。

### 2. 把清洗报告升级成验收报告是关键产品化机会

对话里多次提到“清洗前后质量评分”“高质量数据集验收报告”。这是最应该保留并强化的产品卖点。

客户不会长期为“删除页眉页脚”本身付费，但会为以下结果付费：

- 知识库数据质量提升了多少。
- RAG 回答命中率是否提升。
- 引用是否更准确。
- 敏感信息是否被发现。
- 哪些内容被清洗、为什么被清洗、能否回滚。
- 项目能否验收、汇报、审计。

因此产品输出不应只是清洗后的 Markdown/JSON，而应是：

```text
RAG-ready 数据包
+ 清洗差异报告
+ 质量评分报告
+ 证据追溯记录
+ 数据集说明书
+ 验收报告
```

### 3. 标准合规方向有价值，但不能过早成为主线

《高质量数据集建设指引》和 GB/T 41795-2022 给了平台长期升级方向：质量评价、数据追溯、数据交换、数据元目录、清洗流程、合规报告。

但标准合规不适合成为 0-3 个月 MVP 的主卖点。更合理的处理方式是：

- 早期在底层数据模型中预留 `rule_id`、`rule_version`、`source_id`、`batch_id`、`before_value`、`after_value`、`review_status` 等追溯字段。
- 早期报告中使用标准术语组织质量维度。
- 标准合规中心、NQI 行业包、政企数据交换接口放到后续阶段。

也就是说，早期要“按标准设计内核”，但不要“按标准销售平台”。

## 主要可扩展优化点

### 1. 建立统一中间表示，而不是绑定某个 PDF Parser

对话从 OpenDataLoader PDF 开始，但平台不能绑定单一解析器。解析器能力、许可、成本、部署方式、表格表现、OCR 表现都会变化。

建议设计一个 `DocumentIR` 作为统一中间表示：

```text
Document
├── pages[]
├── elements[]
│   ├── id
│   ├── type: title | paragraph | table | image | header | footer | formula | list
│   ├── text
│   ├── markdown
│   ├── page
│   ├── bbox
│   ├── confidence
│   ├── source_parser
│   └── metadata
├── tables[]
├── images[]
└── parse_warnings[]
```

然后把 OpenDataLoader、Docling、MinerU、Marker、Unstructured、Azure Document Intelligence、PaddleOCR 等都做成 Adapter。

早期至少要支持：

- 一个主 parser。
- 一个 fallback parser。
- parser benchmark 记录。
- 每个文档的 parse warnings。

这样后续扩展 Word/PPT/HTML、扫描件 OCR、复杂表格识别时，不会重写清洗与评分逻辑。

### 2. 把质量评分拆成“场景评分”，不要做一个泛化总分

当前文档多次提到质量评分，但还没有定义评分公式。最大风险是做出一个看起来很好、客户却不信的“AI 分数”。

建议把评分分成三层：

```text
基础数据质量分
RAG 可用性分
合规与追溯分
```

RAG 文档清洗 MVP 只需要优先做这些指标：

| 维度 | 指标 | 说明 |
|---|---|---|
| 解析完整性 | 页面覆盖率、文本覆盖率、表格识别率 | 判断 parser 是否漏内容 |
| 噪声控制 | 页眉页脚命中率、重复段落率、水印噪声率 | 判断清洗是否有效 |
| Chunk 质量 | chunk 长度分布、标题归属率、跨页断裂率 | 判断是否适合 RAG |
| 引用可追溯 | page/bbox 保留率、chunk-source 映射率 | 判断答案能否回源 |
| 安全风险 | PII 命中数、敏感词命中数 | 判断是否可上线 |
| RAG 效果 | 检索命中率、引用准确率、标准问题集通过率 | 判断业务效果 |

质量分必须能 drill down 到证据：

```text
分数下降原因 -> 命中的规则 -> 涉及的文档/chunk -> 原文位置 -> 修复建议
```

### 3. 把“规则”做成资产，而不是一次性脚本

早期最有复用价值的不是模型，而是规则资产。

建议规则模型至少包含：

```yaml
id: remove_repeated_header
version: 1
scope: document
target: element
condition:
  type_in: [header, footer]
  repeated_across_pages_ratio_gte: 0.6
action:
  mark_as_noise: true
  exclude_from_export: true
review:
  required_when_confidence_lt: 0.8
```

规则需要支持：

- 版本管理。
- 命中统计。
- 回滚。
- 行业包复用。
- 人工审核状态。
- 报告引用。

这样未来“法律合同规则包”“制造业知识库规则包”“GB/T 41795 规则包”才有商业化基础。

### 4. 先做审计追溯内核，再做复杂工作流

文档里反复提到可解释、可回滚、数据追溯，这是正确的。建议把它作为平台内核，而不是后期补丁。

每一次清洗操作都应该生成事件：

```text
cleaning_event
├── event_id
├── dataset_id
├── document_id
├── element_id
├── rule_id
├── rule_version
├── action
├── before_snapshot
├── after_snapshot
├── confidence
├── review_status
├── operator
└── created_at
```

早期不一定要做复杂 UI，但必须保存这些事实。否则后续验收报告、回滚、规则优化、合规审计都会缺证据。

### 5. 把人机协同限定为“例外审核”，不要做通用标注平台

对话中有人机协同、专家审核、数据标注等方向。这是必要能力，但 MVP 不应做成完整标注平台。

早期只做三类审核队列：

- 低置信度清洗结果。
- 高风险敏感信息。
- 高影响 chunk 或关键文档。

审核动作只保留：

```text
接受清洗
撤销清洗
修改规则
标记误判
加入白名单/黑名单
```

这样既能支撑审计，又不会把产品复杂度拉爆。

### 6. 把 RAG 评测变成真实验收，不要只说“RAG 可用性提升”

当前文档里“RAG 可用性提升：明显”不够可售卖。必须定义可重复的评测方式。

建议每个试点项目要求客户提供或共同生成：

- 20-100 个标准问题。
- 每个问题的期望引用文档或章节。
- 可接受答案标准。
- 禁止回答或低置信度回答条件。

评测输出：

```text
清洗前 top-k 检索命中率
清洗后 top-k 检索命中率
引用准确率
答案可支持率
无关 chunk 命中率
低质量 chunk 占比
```

这会把“文档清洗”变成“RAG 效果优化”，销售价值更高。

### 7. 先做导出与集成，不要过早做完整生态

文档建议接入 Dify / FastGPT / RAGFlow / MaxKB / LangChain / LlamaIndex。方向对，但第一阶段不应逐个做深度插件。

MVP 先提供标准输出包：

```text
dataset.jsonl
chunks.jsonl
documents.jsonl
metadata.json
quality_report.md
quality_report.json
dataset_card.md
```

字段中保留：

```text
chunk_id
document_id
page
bbox
title_path
cleaning_rules_applied
quality_score
sensitive_flags
source_hash
```

然后优先做 1-2 个最常见平台的导入适配。不要同时承诺所有平台。

## 当前文档中的风险与盲点

### 1. 产品边界漂移

文档从 PDF 清洗迅速扩展到结构化数据、训练数据、政企标准合规、数据交易和 Agent CleanOps。长期方向可以，但早期如果不收敛，会导致：

- 研发资源分散。
- MVP 交付周期失控。
- 客户价值表达变模糊。
- 与云厂商和传统数据治理厂商正面竞争。

建议早期产品名可以叫 `CleanRAG` 或 `Document Data Readiness`，平台级名称 `AI Data Readiness Platform` 作为公司级愿景保留。

### 2. 缺少真实样本与 benchmark 设计

文档提到收集 1000 份真实 PDF / Word / PPT 测试集，但没有定义分层。

建议测试集按这些维度分层：

- 数字 PDF / 扫描 PDF。
- 单栏 / 多栏。
- 表格密集 / 文本密集。
- 有页眉页脚 / 无页眉页脚。
- 中英混排 / 纯中文。
- 法律 / 制造 / 金融 / 政务。
- 正常文档 / 低质量 OCR / 旧版扫描件。

每类样本要有人工标注的 gold set：

```text
应删除的 header/footer
应保留的正文
表格结构
标题层级
chunk 边界
敏感信息
```

没有 benchmark，质量评分和 parser 选型都无法证明。

### 3. 缺少数据权属、版权和模型调用策略

项目面向企业数据和高质量数据集建设，必须早期定义：

- 文档是否可以送外部 LLM。
- OCR / parser 是否本地运行。
- 数据是否加密存储。
- 清洗后数据集的权属归谁。
- 生成的图表描述、摘要、chunk 标题是否算衍生内容。
- 是否允许用客户数据改进模型或规则。

这些不是后期合规问题，而是早期架构问题。

### 4. 标准合规模块需要从“文本引用”变成“规则实现”

现在文档引用了 GB/T 41795 和高质量数据集建设指引，但还没有把标准落到可执行规则。

后续应把标准拆成：

```text
术语层：质量维度、数据类型、流程定义
元数据层：数据集说明书字段、数据元目录字段
规则层：可自动检测的规则
流程层：需要人工确认的审核步骤
报告层：验收报告模板和评分等级
```

只有“规则层 + 报告层”做出来，标准才是产品能力，不是销售话术。

### 5. 结构化数据清洗应延后，但数据模型要预留

结构化数据清洗是大市场，但也会直接撞上传统数据质量平台。建议 12 个月前不要把它作为主战场。

早期只需在模型上预留：

- dataset / asset / version / rule / metric / event 这些抽象。
- 文档 chunk 和表格记录都能挂到同一个质量评价体系。

这样未来能扩展到表数据，但不会影响第一阶段交付。

## 建议的 MVP 重新定义

### MVP 名称

```text
CleanRAG：企业 RAG 文档数据集就绪工具
```

### MVP 目标

让客户能把一批企业文档转成可用于 RAG 的数据包，并拿到可验收的质量报告。

### MVP 输入

第一版建议收敛到：

```text
PDF
Markdown
HTML
```

Word / PPT 可以先通过转换链路或后续版本支持，不要在第一个版本承诺完整保真。

### MVP 核心能力

```text
1. 文档批量导入
2. Parser adapter + DocumentIR
3. 页眉页脚 / 页码 / 水印 / 重复段落清洗
4. 标题层级和表格结构保留
5. Chunk 切分和 chunk 质量评分
6. 敏感信息检测
7. RAG-ready JSONL / Markdown 导出
8. 清洗差异报告 + 数据集说明书 + 质量评分报告
```

### 暂不做

```text
低代码工作流设计器
完整结构化数据库清洗
全行业规则包
标准合规中心 UI
数据交易 / 上架审查
Agent CleanOps
完整标注平台
所有 RAG 平台深度插件
```

## 建议的阶段路线

### 0-4 周：验证解析和清洗可行性

目标：证明“清洗前后质量可量化”。

交付：

- 100-200 份真实文档测试集。
- Parser 对比 benchmark。
- DocumentIR 原型。
- 页眉页脚和重复段落清洗规则。
- 第一版质量指标。
- CLI 或脚本式数据包导出。

### 4-8 周：做试点可用 MVP

目标：让一个客户可以跑完整流程。

交付：

- 批量导入。
- 规则执行和清洗事件日志。
- chunk 切分。
- JSONL / Markdown 导出。
- 质量报告。
- 数据集说明书。
- 基础敏感信息检测。

### 8-12 周：做可收费 PoC

目标：用验收报告卖项目。

交付：

- Web 控制台轻量版。
- 项目 / 数据集 / 版本管理。
- 审核队列。
- RAG 标准问题集评测。
- 清洗前后对比报告。
- 私有化部署包。
- 1 个目标行业 demo。

### 3-6 个月：平台内核

目标：沉淀可复用资产。

交付：

- 规则库和规则版本管理。
- 审计追溯模块。
- Dataset Card 自动生成。
- 质量评分模型配置。
- Dify / RAGFlow / FastGPT 中优先 1-2 个集成。
- 法律或制造业规则包。

### 6-12 个月：行业化

目标：从工具收入转为解决方案收入。

交付：

- 法律合同数据集清洗包。
- 制造业知识库清洗包。
- 金融制度条款清洗包。
- 行业验收报告模板。
- 标准术语和质量评价模板。
- 私有化交付手册。

## 需要立即补齐的项目文档

当前仓库只有原始资料，而且 `docs/` 被 `.gitignore` 忽略。建议尽快补齐并纳入版本管理的文档：

```text
README.md
docs/PRD-CleanRAG-MVP.md
docs/ARCHITECTURE.md
docs/DOCUMENT_IR.md
docs/QUALITY_SCORE_MODEL.md
docs/RULE_ENGINE_SPEC.md
docs/RAG_EVALUATION_PLAN.md
docs/DATASET_CARD_TEMPLATE.md
docs/ACCEPTANCE_REPORT_TEMPLATE.md
docs/ROADMAP.md
```

原始 ChatGPT 对话可以继续保留为 research material，但不适合作为团队执行依据。

## 优先级清单

### P0：必须先做

- 明确 MVP 只做 RAG 文档数据集就绪。
- 设计 DocumentIR。
- 设计清洗事件和追溯字段。
- 设计质量评分维度。
- 建立真实文档 benchmark。
- 输出验收报告模板。

### P1：试点前要做

- Web 控制台轻量版。
- 审核队列。
- 规则版本管理。
- RAG 问题集评测。
- 私有化部署包。
- 1 个行业 demo。

### P2：平台化后做

- 标准合规中心。
- 结构化数据清洗。
- 多行业规则包。
- 数据交换接口。
- 数据集生命周期运营。
- Agent CleanOps。

## 最终建议

保留原文档里的长期愿景，但把产品执行路径改成“窄入口、强内核、可扩展平台”：

```text
窄入口：RAG 文档数据集就绪
强内核：DocumentIR + 规则资产 + 质量评分 + 审计追溯 + 验收报告
可扩展平台：高质量数据集建设 + 标准合规 + 行业规则包 + CleanOps
```

这条路线的优势是：第一版能交付、第二版能复用、第三版能进入高客单价行业场景。
