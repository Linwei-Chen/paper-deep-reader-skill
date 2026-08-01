# 设计调研与取舍

本文件记录 `paper-deep-reader` 的设计来源，供维护者审查；执行论文解读时无需加载。

## 调研对象

1. [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
   - 采用：明确触发描述、`SKILL.md` 保持精简、详细协议按需加载、脚本承担确定性操作。
2. [Mizoreww / paper-reading](https://github.com/Mizoreww/awesome-claude-code-config/tree/main/skills/paper-reading)
   - 采用：论文类型路由、PDF 图像提取、原始结果图必须保留、来源与代码证据分层。
3. [gyy0592 / paper-overview 与 paper-reader](https://github.com/gyy0592/claude-config/tree/main/skills)
   - 采用：先全局地图后公式级深读、Before/After/Diff/Insight、公式符号完整性与零跳步检查。
4. [c-narcissus / agent-paper-grounded-reading](https://github.com/c-narcissus/agent-paper-grounded-reading)
   - 采用：主张—证据可追溯、PDF/LaTeX 双源核查、图表和实验与论文叙事逻辑对齐。
5. [yishuai778 / paper-reading](https://github.com/yishuai778/paper-reading)
   - 采用：决策级输出、区分作者主张/证据/推断、判断是否值得复现或引用。
6. [Richard-ZSR / academic-paper-professor](https://github.com/Richard-ZSR/academic-paper-professor)
   - 采用：逐实验解析、精确数字与比较条件、历史与方法定位、最快证伪实验。
7. [debug-zhuweijian / paper-review](https://github.com/debug-zhuweijian/ai-research-toolkit/tree/main/modules/03-analysis/skills/paper-review)
   - 采用：研究顺序阅读、机制与证据优先、复现与迁移价值。
8. 本地 `nature-reader`、`alphaxiv`、`deepxiv`、`paper-claim-audit`
   - 采用：来源格式路由、渐进读取、反幻觉核验和主张—原始证据纪律。

## 主要设计决定

- **六段式结构保留**：直接兼容用户原始报告框架，不额外制造顶层章节。
- **分层阅读而非两份重复报告**：开头快速建立地图，后文逐模块、公式、实验和图表深挖。
- **全量图表账本 + 关键图表详解**：既防遗漏，又避免对装饰性图表平均用力。
- **原图优先**：重绘可帮助解释，但不能替代承载结论的原始结果图。
- **主张—证据分离**：论文说了什么与实验真正支持什么分别记录。
- **类型路由**：方法、理论、数据集、系统、综述使用不同审查标准。
- **CV 专项审查**：显式检查 backbone、预训练、分辨率、额外数据、测试时增强、泄漏、生成指标和定性挑样。
- **确定性校验**：脚本检查六段结构、占位符、图片链接、图表覆盖和 source map；模型负责解释与判断。
- **低依赖**：只把 PyMuPDF 作为可选图像工具；不强制 MinerU、OCR 服务、特定模型或 API。

## 未直接照搬的模式

- 不强制每次询问语言、深度或格式：能从请求推断时直接执行，减少交互成本。
- 不默认运行论文代码或复现实验：深读负责只读核查；复现应是单独任务。
- 不要求所有论文生成 HTML、静态站点或多代理流水线：Markdown 是用户指定的默认交付。
- 不设固定字数：以机制、证据、图表和边界是否完整作为完成标准。
- 不把自动 PDF 裁图视为可信结果：所有裁图必须视觉复核并在 manifest 中留痕。
