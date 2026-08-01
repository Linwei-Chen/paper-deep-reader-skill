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
   - 采用：主张—证据可追溯、多源版本核查、图表和核心证据与论文叙事逻辑对齐。
5. [yishuai778 / paper-reading](https://github.com/yishuai778/paper-reading)
   - 采用：决策级输出、区分作者主张/证据/推断、判断是否值得复现或引用。
6. [Richard-ZSR / academic-paper-professor](https://github.com/Richard-ZSR/academic-paper-professor)
   - 采用：逐证据解析、精确结果与比较条件、历史与方法定位、最快证伪方案。
7. [debug-zhuweijian / paper-review](https://github.com/debug-zhuweijian/ai-research-toolkit/tree/main/modules/03-analysis/skills/paper-review)
   - 采用：研究顺序阅读、机制与证据优先、复现与迁移价值。
8. 本地 `nature-reader`、`alphaxiv`、`deepxiv`、`paper-claim-audit`
   - 采用：来源格式路由、渐进读取、反幻觉核验和主张—原始证据纪律。

## 主要设计决定

- **六段式结构保留**：直接兼容用户原始报告框架，不额外制造顶层章节。
- **分层阅读而非两份重复报告**：开头快速建立地图，后文逐步骤、形式化内容、证据和图表深挖。
- **全量图表账本 + 关键图表详解**：既防遗漏，又避免对装饰性图表平均用力。
- **原图优先**：重绘可帮助解释，但不能替代承载结论的原始结果图。
- **主张—证据分离**：论文说了什么与直接证据真正支持什么分别记录。
- **类型路由**：方法、理论、实证/观察、数据集、系统、综述使用不同审查标准。
- **领域路由**：不同学科使用不同的证据、测量、偏差和复核规范。
- **CV 作为可选深度 Lens**：保留 backbone、预训练、分辨率、生成指标和定性挑样等检查，但不作为默认假设。
- **确定性校验**：脚本检查六段结构、占位符、图片链接、图表覆盖和 source map；模型负责解释与判断。
- **低依赖**：只把 PyMuPDF 作为可选图像工具；不强制 MinerU、OCR 服务、特定模型或 API。

## v2 跨学科架构

v1 默认把读者设为计算机视觉博士。这能提高一个领域内的针对性，但会把三件不同的事混在一起：

1. 论文遵循哪一学科的证据规范；
2. 读者已经掌握什么；
3. 读者准备如何使用论文。

v2 将它们拆成五个正交维度：

```text
domain × audience × goal × depth × language
```

### 宽默认而非空泛默认

默认 `research-generalist` 不是“没有知识的普通读者”，而是：

- 具备科研方法、图表、公式和统计的基础；
- 不预设掌握目标细分领域；
- 需要解释领域术语与前置假设；
- 仍要求完整方法和证据深度。

这样既避免固定 CV 身份，也避免把报告降成大众科普。

### 三层路由相互独立

- **论文类型 Lens**：贡献由方法、理论、实证发现、数据资源、系统还是综合论证成立；
- **学科 Lens**：该领域接受什么证据、常见偏差是什么；
- **目标 Lens**：理解、审稿、复现、教学或迁移时应强调什么。

跨学科论文最多选择一个主领域和一个次领域，防止清单爆炸。CV 仍在计算机科学与 AI Lens 中获得细粒度支持。

### 结构化画像优于自由角色扮演

用户可以自然语言描述背景，Skill 将其解析为结构化字段。解析优先级是：

```text
用户本次要求 → .paper-reader.yaml → 对话偏好 → 自动识别 → 默认
```

画像只调整解释层，不调整事实层。项目配置不能执行命令、加载凭据或覆盖用户本次明确要求。

## 未直接照搬的模式

- 不强制每次询问语言、深度或格式：能从请求推断时直接执行，减少交互成本。
- 不默认运行论文代码或开展复现实验：深读负责只读核查；实际复现应是单独任务。
- 不要求所有论文生成 HTML、静态站点或多代理流水线：Markdown 是用户指定的默认交付。
- 不设固定字数：以机制、证据、图表和边界是否完整作为完成标准。
- 不把自动 PDF 裁图视为可信结果：所有裁图必须视觉复核并在 manifest 中留痕。
