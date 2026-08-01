---
name: paper-deep-reader
description: Produces source-grounded, figure/table-aware deep-reading reports for a single academic paper, with plain-language explanations, method reconstruction, equation walkthroughs, experiment-by-experiment evidence audits, and publication-ready Markdown with embedded visuals. Use when the user provides a paper PDF, URL, DOI, arXiv ID, title, or full text and asks for 论文解读、论文剖析、精读、逐图表分析、快速看懂、explain/analyze/deep-read this paper. Optimized for computer-vision researchers; not for full-paper translation or broad multi-paper surveys.
---

# Paper Deep Reader

把论文解读写成“可核查的技术教学”，而不是扩写摘要。默认读者是计算机视觉博士：语言尽量直白，技术细节必须足够复现论文的思想与证据链。

## 核心交付

默认生成：

```text
<paper-slug>-deep-read/
├── report.md
├── assets/
│   ├── pages/
│   ├── crops/
│   └── visual_manifest.json
└── source_map.json
```

- `report.md`：遵循 [references/report-template.md](references/report-template.md) 的六部分中文报告。
- `assets/`：论文关键图表的清晰裁图；图片应插在对应解读附近。
- `source_map.json`：从 [references/source-map-template.json](references/source-map-template.json) 建立，记录版本、来源、页码约定、核心主张及证据锚点。它服务于核查，不替代报告。

若用户指定只在聊天中回答、指定输出位置或要求其他语言/格式，遵从用户。不要改动原始论文文件。

## 先判断请求

1. **没有论文或可定位的标题**：只问一个问题，请用户提供 PDF、URL、DOI、arXiv ID、标题或全文。
2. **快速/值不值得读/速览**：执行“快读”，保留一句话结论、核心机制、2–4 个最关键图表、主结果和最大局限。
3. **解读/剖析/精读/详尽/逐图表**：执行“深读”（默认），覆盖完整论文及影响结论的附录。
4. **只问一个局部问题**：直接回答，但仍给出精确来源锚点；不要机械生成整份报告。
5. **全文翻译或中英对照**：交给全文翻译类 skill；本 skill 只负责解释、重构和审查。
6. **多论文综述**：交给文献综述类 skill；本 skill 可对其中一篇做深读。

能从用户措辞安全推断时，不要再询问阅读深度、语言或输出位置。默认使用简体中文和 Markdown。

典型调用：

- `精读 @paper.pdf，面向计算机视觉博士，逐图表解释。` → 深读报告。
- `快速看懂 2401.12345，告诉我值不值得复现。` → 快读并给决策。
- `只解释式(7)如何对应图3的模块。` → 定向问答与精确锚点。

## 每次调用要加载的材料

1. 深读或快读前，阅读 [references/reading-protocol.md](references/reading-protocol.md)。
2. 写报告前，阅读 [references/report-template.md](references/report-template.md)。
3. 判定论文类型后，只加载 [references/paper-type-lenses.md](references/paper-type-lenses.md) 中对应的类型与 CV 专项检查。
4. 交付前，阅读并执行 [references/quality-checklist.md](references/quality-checklist.md)。

不要一次性把所有参考文件重复读入上下文。

## 工作流

### 1. 建立可信来源包

按优先级使用：

1. 用户提供的 PDF/全文；
2. 官方 PDF、出版社/OpenReview/会议页面或 arXiv；
3. 与同一版本匹配的 LaTeX/HTML、补充材料；
4. 官方项目页和官方代码（仅在澄清实现细节时只读检查）；
5. 二手博客只用于背景，不能证明目标论文的主张。

若从 PDF 切换到 arXiv/LaTeX，核对标题、作者、版本日期和正文差异。记录实际使用的来源及缺失项。来源不完整时继续做最佳可行解读，但明确降低置信度；严禁补写看不到的公式、数字或图表。

### 2. 建立四张清单，再开始写作

完整阅读标题、摘要、引言、结论、方法、实验、关键附录，以及所有图表标题。建立：

- **章节清单**：每节解决什么问题。
- **图表清单**：所有编号图/表/算法的编号、页码、标题、作用和“关键/非关键”判定。
- **公式清单**：关键公式、符号、来源位置、对应算法步骤。
- **主张—证据清单**：每个核心贡献由哪张图、哪张表、哪项消融或哪条理论结果支撑。

先写一句链条：**问题 → 旧方法瓶颈 → 核心洞见 → 机制 → 证据 → 适用边界**。若这条链说不清，说明尚未读懂，继续查源。

### 3. 提取并核查图表

PDF 可访问时，优先执行脚本而不是手抄截图：

```bash
python3 <skill-dir>/scripts/extract_pdf_assets.py inventory PAPER.pdf OUTPUT/assets --dpi 180
```

若缺少 PyMuPDF，优先使用隔离环境：

```bash
uv run --isolated --with pymupdf \
  python <skill-dir>/scripts/extract_pdf_assets.py inventory PAPER.pdf OUTPUT/assets --dpi 180
```

脚本的自动裁图只是候选。必须逐张打开核查；不能裁掉坐标轴、图例、列名、单位、基线、脚注或失败案例。候选不合格时，根据页面预览像素坐标重裁：

```bash
python3 <skill-dir>/scripts/extract_pdf_assets.py crop PAPER.pdf OUTPUT/assets/crops/figure-3.png \
  --page 7 --bbox 120,180,1120,1030 --dpi 180
```

核查后更新 `visual_manifest.json`：为每项设置 `key: true/false`；关键项填写相对 `assets/` 的 `selected_asset`，把 `crop_review_required` 设为 `false`，并记录 `claim_ids` 和简短 `review_notes`。自动检测遗漏的编号图表要人工补入 manifest。

执行 [references/reading-protocol.md](references/reading-protocol.md) 的“逐图表协议”。每个**关键**图表都要嵌入原图并逐面板/逐轴/逐行解释；每个非关键编号图表也要在覆盖清单中说明其作用与为何略读。若源格式无法提取图片，使用明确的缺图占位和来源位置，不能伪造重绘。

### 4. 重构方法，而非复述章节

从输入到输出解释完整数据流。对每个承重模块说明：

- 它修复哪个失败模式；
- 输入、输出及形状/单位（若论文给出）；
- 内部变换、训练信号或优化目标；
- 训练阶段与推理阶段分别做什么；
- 与前后模块如何连接；
- 关键假设、代价和可能失效点；
- 与最接近旧方法的 **Before / After / Diff / Trade-off**。

用一个最小数值例子或具体 CV 场景走完主流程。类比只帮助建立直觉，随后必须回到论文的精确定义。

### 5. 解释数学，不堆公式

只保留决定机制、训练目标、理论保证或实验解释的关键公式。每个公式必须：

1. 与原文公式编号/章节/页码核对；
2. 解释每个符号、索引、算子及张量形状（可知时）；
3. 先说目标和直觉，再逐项解释；
4. 映射到算法步骤或系统行为；
5. 给一个小数值例子（适用时）；
6. 说明假设、近似、边界情况和可替代形式。

PDF 文本与公式图像/LaTeX 冲突时，以可见公式或匹配版本的 LaTeX 为准，并记录冲突。

### 6. 逐实验审查证据

每项重要实验分别回答：

- 实验问题/待证伪假设是什么？
- 数据、划分、预处理、模型、训练/推理预算、基线和指标是什么？
- 最关键的绝对数值、百分点差、相对变化和代价是什么？
- 结果支持什么，不支持什么？
- 基线是否公平，消融是否隔离变量，是否报告多随机种子/方差/显著性？
- 是否存在泄漏、挑图、隐藏调参、指标失真或计算成本遗漏？

把每个核心主张判为 **强支持 / 部分支持 / 弱支持 / 未支持**，并给出最省成本的证伪或补强实验。

### 7. 写成六部分、分层可读的报告

严格使用 [references/report-template.md](references/report-template.md) 的顶层六部分。报告开头让读者 3 分钟获得全局地图，后文再提供公式、模块、实验和图表细节。

对重要事实使用紧邻文本的来源锚点，例如：

- `[论文 §3.2，式(4)，PDF p.6]`
- `[图3(b)，PDF p.7]`
- `[表2，PDF p.9]`
- `[补充材料 §B.1]`

明确区分 **作者主张**、**论文直接证据**、**本文推断** 和 **外部背景**。不要把论文自称“首个/SOTA”当成已验证事实。

### 8. 校验后交付

先人工执行质量清单，再运行：

```bash
python3 <skill-dir>/scripts/validate_report.py OUTPUT/report.md \
  --manifest OUTPUT/assets/visual_manifest.json --strict
```

修复错误并重复运行，直到通过。若 PDF 没有可解析标题、论文没有图表，或图表只能人工识别，使用相应参数或在交付说明中写清边界；不要为了让校验通过而虚构内容。

## 完成标准

只有同时满足以下条件才算完成：

- 一句话总结不超过 50 个中文字符，并准确包含“做什么 + 为什么有效”；
- 读者能沿输入→模块→目标函数→输出重建方法；
- 所有编号图表均进入覆盖清单，所有关键图表已嵌图并详细解读；
- 核心公式符号完整、来源可定位、没有逻辑跳步；
- 每个主要结论都能回溯到实验、理论或明确标注的推断；
- 报告说明了最强证据、最弱主张、适用边界和最快证伪实验；
- 无 `TODO`、伪造数字、伪造引用、空占位或未核查自动裁图。
