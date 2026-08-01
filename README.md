# Paper Deep Reader

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](CHANGELOG.md)

面向跨学科科研人员的来源可追溯论文深读 Agent Skill。它从 PDF、URL、DOI、预印本 ID、标题或全文出发，自动适配**论文领域、读者背景与研究目标**，生成逐图表、可复核、可审查的 Markdown 报告。

它不是摘要扩写器。目标是让读者在最短时间内回答：

- 论文真正解决了什么问题？
- 新方法、理论或研究设计具体改变了什么？
- 关键公式、定义或论证如何对应研究过程？
- 每张核心图表到底证明了什么？
- 实验、证明、观测或材料是否足以支撑作者主张？
- 哪些结论值得相信、复现、引用或继续研究？

## 特性

- **三遍阅读法**：全局地图 → 机制重构 → 证据审查。
- **结构化读者画像**：`domain × audience × goal × depth × language` 独立配置。
- **宽默认、按需专门化**：默认面向有科研训练的通用研究者；支持领域专家、跨学科读者和学生。
- **多目标路由**：理解、审稿、复现、教学和跨领域迁移采用不同解读重点。
- **固定六部分报告**：兼顾快速理解与研究级技术深度。
- **全量视觉账本**：记录 Figure、Table、Algorithm、Scheme、Plate、Box 等编号对象；关键视觉证据嵌入原图并详细解释。
- **形式化零跳步**：解释公式、定义、定理、统计量或分析框架的组成、作用、研究位置和边界。
- **主张—证据映射**：区分作者主张、论文直接证据、报告推断和外部背景。
- **逐证据单元审查**：覆盖实验、证明、观测、案例、定性材料与综合分析。
- **论文类型路由**：方法、理论、实证/观察、数据集/基准、系统、综述采用不同审查标准。
- **跨学科 Lens**：计算机/AI、生物医学、物理/数学、化学/材料、工程、社会科学、地球环境与人文定性研究。
- **CV 深度支持**：保留 backbone、预训练、生成指标、视觉挑样、VLM judge bias、3D/视频等专项检查，但不再作为默认读者假设。
- **可发布 Markdown**：报告、图片资产和机器可读 source map 一起输出。
- **确定性校验**：脚本检查报告结构、占位符、图片路径、图表覆盖和证据映射。

## 安装

### Cursor

```bash
git clone https://github.com/Linwei-Chen/paper-deep-reader-skill.git \
  ~/.cursor/skills/paper-deep-reader
```

新开一个 Cursor 对话后即可使用。更新：

```bash
git -C ~/.cursor/skills/paper-deep-reader pull
```

### 其他 Agent Skills 兼容工具

该仓库采用通用 `SKILL.md` 结构。可复制到对应工具的个人 Skills 目录，例如：

```bash
# Claude Code
git clone https://github.com/Linwei-Chen/paper-deep-reader-skill.git \
  ~/.claude/skills/paper-deep-reader

# Codex
git clone https://github.com/Linwei-Chen/paper-deep-reader-skill.git \
  ~/.codex/skills/paper-deep-reader
```

当前主要在 Cursor 中验证；其他工具需要能够读取 `SKILL.md`、执行 Python 脚本并访问本地论文文件。

## 使用示例

```text
精读 @paper.pdf，面向跨学科科研人员，逐图表解释。

快速看懂 2401.12345，告诉我值不值得复现。

读者是做机器学习的博士，但不了解蛋白质组学。
请解释这篇生物医学论文，并判断能否迁移到表征学习。

像审稿人一样严格分析这篇材料学论文。

只解释式(7)如何对应图3中的步骤。
```

默认跟随用户语言，无语言信号时输出简体中文 Markdown。用户明确要求快读、其他语言、仅回答局部问题或指定输出位置时，会相应调整。

## 读者画像与项目配置

默认画像：

```yaml
domain: auto
audience: research-generalist
goal: understand
depth: deep
language: auto
```

五个维度独立解析：

- `domain`：论文所属学科证据规范；
- `audience`：`research-generalist`、`domain-researcher`、`cross-disciplinary` 或 `student`；
- `goal`：`understand`、`review`、`reproduce`、`teach` 或 `transfer`；
- `depth`：`quick`、`deep` 或 `targeted`；
- `language`：跟随用户或明确指定。

用户可以直接用自然语言描述，不必编写 YAML。若希望在一个项目中长期保存偏好：

```bash
cp .paper-reader.example.yaml /path/to/project/.paper-reader.yaml
```

解析优先级为：

```text
本次用户要求 → 项目 .paper-reader.yaml → 对话偏好 → 自动识别 → 默认画像
```

配置只改变解释方式和重点，不改变论文事实、证据等级或缺失信息。

## 默认输出

```text
<paper-slug>-deep-read/
├── report.md
├── assets/
│   ├── pages/
│   ├── crops/
│   ├── visual_ledger.md
│   └── visual_manifest.json
└── source_map.json
```

- `report.md`：六部分完整解读。
- `assets/pages/`：PDF 页面预览。
- `assets/crops/`：经人工核查的关键视觉证据。
- `visual_manifest.json`：所有编号视觉对象及其关键性、裁图状态和关联主张。
- `source_map.json`：论文版本、来源、读者画像、页码约定和主张—证据映射。

## PDF 图表提取

报告校验器只使用 Python 标准库。PDF 图表提取器额外需要 [PyMuPDF](https://pymupdf.readthedocs.io/)。

推荐使用隔离环境：

```bash
uv run --isolated --with pymupdf \
  python scripts/extract_pdf_assets.py inventory paper.pdf output/assets --dpi 180
```

也可安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

生成 Figure、Table、Algorithm、Scheme、Plate、Box 等候选视觉对象：

```bash
python3 scripts/extract_pdf_assets.py inventory \
  paper.pdf output/assets --dpi 180
```

候选裁图必须人工打开核查。若坐标轴、图例、标题、脚注或面板不完整，可按页面预览的像素坐标重新裁剪：

```bash
python3 scripts/extract_pdf_assets.py crop \
  paper.pdf output/assets/crops/figure-3.png \
  --page 7 --bbox 120,180,1120,1030 --dpi 180
```

## 报告校验

```bash
python3 scripts/validate_report.py output/report.md \
  --manifest output/assets/visual_manifest.json \
  --strict
```

严格模式会检查：

- 六个顶层部分是否完整且顺序正确；
- 一句话总结是否过长（中文 50 字，非中文 30 词）；
- 是否残留 `TODO` 或模板占位符；
- 本地图片是否存在；
- 所有编号视觉对象是否进入覆盖清单；
- 关键视觉对象是否已人工核查并嵌入报告；
- `source_map.json` 是否包含有效主张和证据。

## 仓库结构

```text
.
├── .paper-reader.example.yaml
├── SKILL.md
├── README.md
├── DESIGN_NOTES.md
├── CHANGELOG.md
├── LICENSE
├── requirements.txt
├── references/
│   ├── audience-profiles.md
│   ├── domain-lenses.md
│   ├── reading-protocol.md
│   ├── report-template.md
│   ├── paper-type-lenses.md
│   ├── quality-checklist.md
│   └── source-map-template.json
└── scripts/
    ├── extract_pdf_assets.py
    └── validate_report.py
```

## 设计原则与来源

设计吸收了 Agent Skills 官方渐进加载原则，以及多个公开论文阅读 Skill 中的优秀模式，包括：

- 先概览、后深读；
- 原始图表优先；
- 形式化内容零跳步；
- 逐证据单元而非只报主结果；
- 主张—证据可追溯；
- 论文类型、学科 Lens、读者背景和研究目标相互独立；
- 输出必须支持“复现、引用、借鉴或跳过”的研究决策。

完整调研来源和取舍见 [`DESIGN_NOTES.md`](DESIGN_NOTES.md)。

## 限制

- 自动裁图是候选结果，不能替代人工视觉核查。
- 扫描 PDF 可能需要外部 OCR；本仓库不上传论文到第三方服务。
- 本 Skill 默认不运行论文代码、开展实验或声称完成实际复现。
- “新颖性”和“SOTA”必须通过额外文献检索才能独立验证，不能只依据论文自述。
- 领域 Lens 是审查清单，不替代具备资质的临床、法律、安全或伦理判断。

## 贡献

欢迎提交 Issue 或 Pull Request，尤其是：

- 新版式或跨页表格的提取改进；
- 新学科与子领域审查 Lens；
- 更完善的读者画像和目标预设；
- 真实论文上的失败案例；
- 报告校验规则与跨平台兼容性改进。

## License

[MIT](LICENSE)

---

**English summary:** A source-grounded Agent Skill for deep reading individual academic papers across disciplines. It adapts to the paper domain, reader expertise, and goals; inventories key visuals; reconstructs formal and methodological logic; audits claim-to-evidence links; and produces publication-ready Markdown. Computer vision remains deeply supported as an optional domain lens. The skill is primarily tested in Cursor.
