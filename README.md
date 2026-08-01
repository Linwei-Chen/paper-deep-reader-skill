# Paper Deep Reader

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

面向计算机视觉研究者的论文深读 Agent Skill：从 PDF、URL、DOI、arXiv ID、标题或全文出发，生成**来源可追溯、逐图表解释、公式可复核、实验可审查**的中文 Markdown 报告。

它不是摘要扩写器。目标是让读者在最短时间内回答：

- 论文真正解决了什么问题？
- 新方法具体改了什么，为什么可能有效？
- 关键公式如何对应训练或推理流程？
- 每张核心图表到底证明了什么？
- 实验是否足以支撑作者的主张？
- 哪些结论值得相信、复现、引用或继续研究？

## 特性

- **三遍阅读法**：全局地图 → 机制重构 → 证据审查。
- **固定六部分报告**：兼顾快速理解与博士级技术深度。
- **全量图表账本**：所有编号图表均被记录；关键图表嵌入原图并逐面板、逐轴、逐行解释。
- **数学零跳步**：解释符号、张量形状、逐项作用、算法位置、数值例子及适用边界。
- **主张—证据映射**：区分作者主张、论文直接证据、报告推断和外部背景。
- **逐实验审查**：检查数据、划分、基线、指标、预算、消融、统计性、泄漏和计算成本。
- **论文类型路由**：方法、理论、数据集/基准、系统、综述采用不同审查标准。
- **CV 专项检查**：覆盖 backbone、预训练、分辨率、额外数据、测试时增强、生成指标、视觉挑样、VLM judge bias、3D/视频等问题。
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
精读 @paper.pdf，面向计算机视觉博士，逐图表解释。

快速看懂 2401.12345，告诉我值不值得复现。

详细剖析这篇论文，重点核查实验是否支撑核心主张。

只解释式(7)如何对应图3中的模块。
```

默认输出简体中文 Markdown。用户明确要求快读、其他语言、仅回答局部问题或指定输出位置时，会相应调整。

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
- `assets/crops/`：经人工核查的关键图表。
- `visual_manifest.json`：所有编号图表及其关键性、裁图状态和关联主张。
- `source_map.json`：论文版本、来源、页码约定和主张—证据映射。

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

生成候选图表：

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
- 一句话总结是否超过 50 字；
- 是否残留 `TODO` 或模板占位符；
- 本地图片是否存在；
- 所有编号图表是否进入覆盖清单；
- 关键图表是否已人工核查并嵌入报告；
- `source_map.json` 是否包含有效主张和证据。

## 仓库结构

```text
.
├── SKILL.md
├── README.md
├── DESIGN_NOTES.md
├── LICENSE
├── requirements.txt
├── references/
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
- 公式零跳步；
- 逐实验而非只报主表；
- 主张—证据可追溯；
- 输出必须支持“复现、引用、借鉴或跳过”的研究决策。

完整调研来源和取舍见 [`DESIGN_NOTES.md`](DESIGN_NOTES.md)。

## 限制

- 自动裁图是候选结果，不能替代人工视觉核查。
- 扫描 PDF 可能需要外部 OCR；本仓库不上传论文到第三方服务。
- 本 Skill 默认不运行论文代码、训练模型或声称完成实验复现。
- “新颖性”和“SOTA”必须通过额外文献检索才能独立验证，不能只依据论文自述。

## 贡献

欢迎提交 Issue 或 Pull Request，尤其是：

- 新版式或跨页表格的提取改进；
- 更多 CV 子方向审查清单；
- 真实论文上的失败案例；
- 报告校验规则与跨平台兼容性改进。

## License

[MIT](LICENSE)

---

**English summary:** A source-grounded Agent Skill for deep reading single academic papers, with figure/table coverage, equation walkthroughs, experiment-by-experiment evidence audits, CV-specific review lenses, and publication-ready Markdown output. The skill is primarily tested in Cursor.
