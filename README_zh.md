# JobBot Skill

[English](README.md) · [中文设计](DESIGN_zh.md) · [English design](DESIGN.md) · [Agent 入口](SKILL.md)

JobBot 是在 agent 对话中运行的独立求职 skill：先建立可复用的经历与偏好档案，再查找机会，为具体岗位完成准确、有竞争力的简历。资料保存在用户选择的本地工作区，无需原 JobBot 服务、数据库、Node.js 或 Web UI。

英文是执行指引、参考资料、schema 和命令的主要维护语言；本文件提供中文概览，详细产品决策见 [DESIGN_zh.md](DESIGN_zh.md)。对话和简历可以使用用户确认的语言。

## 使用流程

1. 全面收集或复用经历与求职偏好。可以提供旧简历、GitHub、作品集、成绩单或直接讲经历；不需要先确定岗位，也不按 JD 删减长期档案。
2. 查找公司与岗位，或读取用户提供的网页、截图、PDF、文字。按宿主能力选择 API、搜索、网页阅读或 computer use；图片使用原生视觉，无需固定 OCR 流程。
3. 先检查就业国家等硬约束，再比较城市偏好、搬迁条件及岗位要求。评分 worker 给出判断，脚本计算匹配分，独立审核后先向用户展示优势、差距和不确定项。
4. 从资料库选择多段互补经历，再读取已有细节深化和编排。不重复访谈已知事实；核心贡献仍不清楚、存在矛盾或用户希望量化时，通过针对性多轮问答补充。
5. 确认目标国家的文档设置，由主 agent 撰写和润色，脚本生成 LaTeX、PDF、文本及页面图像。
6. 独立内容／视觉评审当前版本，给出分数和可执行意见。通过后校验并交付；材料不足则回到针对性收集，更新受影响档案及审核后继续；已有材料写得不足则由主 agent 重写，再生成与审核，沿用原轮次预算。

审核强度按目标岗位的实际职责校准：具体实现可以支撑初级岗位，要求独立负责的岗位则需要更强的决策与交付证据。匹配和内容评审采用同一职责范围，不补写无依据的高级职责。数值通过门槛不变，职级解释由宿主执行。见 [职级校准](references/level-calibration.md)。

已有可用档案时，第二、第三份简历可以跳过收集。`intake.json` 记录最近一次与用户实际核对的时间；约三个月可以提醒询问新进展，不是资料过期或生成门槛。生成简历不会刷新该时间。宿主记忆是可选能力，读取与写入分别征得用户同意。

所有中间产物也保存在工作区：来源、阅读和分析结果、相关用户回答与确认、选择方案、草稿、失败尝试、审核反馈和修改记录。已有归属文件与快照保留内容，`runs/<run-id>/` 索引记录阶段状态、产物路径／哈希和下一步，便于中断后继续；交接前保存，覆盖前保留旧版。该协议由宿主 agent 执行，CLI 尚无自动检查点引擎，具体见[存储规范](references/workspace-storage.md)。

岗位本地信息默认七天后提醒重新核实，`expires_at` 与招聘方公布的截止日期分开。过期不等于关闭；无法核实不会延长有效期。原始材料、核查记录和历史产物继续保留。

默认所有委派调用共享两个并发名额，评分 worker 另有两个并发上限；实际派发、选模和尝试次数由宿主维护。评分可使用已授权且实际可用的低成本模型，写作仍由主 agent 负责。支持 Claude/Anthropic、OpenAI、DeepSeek 等模型的通用配置与结果格式，不捆绑厂商客户端或后台调度器。

文档质量默认要求总分至少 80、每个必要角色至少 70、没有严重问题，内容／视觉权重为 60%／40%。初稿后最多自动重写两次。评审不可用时保留待审核状态，不算零分；预算耗尽则保留标明状态的草稿和问题。视觉审核必须看完每页，并绑定精确 PDF SHA-256。不会自动投递，也不会生成没有真实依据的候选人声明；合理的用户估算可以使用，但不能仅因为数字好看而编造。

事实纠正和用户要求的改稿通过 `document_quality.py --prepare --new-version --reason REASON` 建立关联版本；更换主会话通过 `--handoff` 记录真实新 writer。两者保留历史并共享已有总预算，耗尽后只有明确获授权的 `--grant-rounds N` 才能增加次数，不能重置计数。内容寻址快照跨轮次复用相同字节。公开 GitHub 导入不读取环境 token，并记录有上限的分页覆盖范围。详见[文档生命周期](references/document-quality-loop.md)及[导入边界](references/candidate-intake.md)。

文件夹导入拒绝托管 `objects/` 快照及其子目录。单纯 JSON 空白／键顺序变化和随之刷新的方案绑定哈希不会获得新轮次；来源和生成物的审核仍要求精确字节哈希。

## 运行与当前边界

材料不足时，流程回到针对性的多轮收集，不无限润色单薄草稿。宿主先检索，保存问题和真实回答，更新受影响事实及审核。内容评分明确考察经历实质；有效的内容 `collect_evidence` 请求会由脚本阻止通过（`needs_material`，到预算上限则为 `exhausted`），缺失评审仍为 `blocked`。恢复需要来源上下文实际变化，并沿用原轮次预算。对话和充分性判断由宿主负责；拒绝或暂无法回答时保留明确受限／待处理的草稿。见[材料补充循环](references/material-recovery.md)。

定制简历时，重点呈现多段互补经历中的具体贡献、实现和有依据的交付成果。Skills 保持紧凑，落实用户的章节顺序和增加项目内容的要求，把篇幅留给更有价值的项目／工作证据。内容审核检查档案材料是否被充分利用，视觉审核检查实际篇幅和层级。这些是宿主判断，不是自动深度／面积评分，也不要求固定项目数量。当前渲染器沿用已存技能分类，没有单份文档重分组功能。见[经历编排指引](references/experience-selection.md)。

- 核心需要 Python 3.10+，只使用标准库。
- PDF 生成使用可选 TeX 引擎：普通英文默认 pdfLaTeX，中文／CJK 使用 XeLaTeX 或 LuaLaTeX 及已安装的 ctex／Fandol；检查使用 Poppler。资料收集无需这些工具。
- 宿主提供阅读、搜索、真实独立审核及所需原生视觉能力。CLI 不调用模型、不派发 agent，也不强制早期阶段审核；文档循环脚本会校验评分、哈希与重写预算，已有循环会在最终审核时复核。旧的无循环审核记录仍保持兼容。
- 新档案 v3 支持工作、项目、研究、课程及其他经历的独立记录和关联事实；v2 仍可读取，并提供保留历史的显式升级。新简历方案 v2 绑定写作规则，可调整章节顺序。原创 0BSD 模板支持中英文标题，暂不支持照片；更多布局、按任务判断准备度、独立搜索 adapter 和通用 JD／文档版本迁移仍待实现。`prepare-resume` 仍要求 onboarding 分区全部确认，已有确认可跨岗位复用。

可将材料放进专门的文件夹，用 `scripts/intake_folder.py --workspace WORKSPACE --folder MATERIALS --import` 做增量导入；按内容哈希复用原件、保留新版本，导入后仍由 agent 阅读并区分用户确认。`writing-rules.json` 保存长期措辞及内容排除规则，与求职偏好分开。参见[经历模型](references/experience-model.md)、[写作规则](references/writing-rules.md)及[场景评测](evals/README.md)。

从 agent 的 [SKILL.md](SKILL.md) 入口使用，选择源码目录之外的工作区；JSON 由 agent 维护。以下是仓库根目录下的示例：

```bash
python3 scripts/jobbot_skill.py init --workspace ~/job-search --country US
python3 scripts/jobbot_skill.py workspace-status --workspace ~/job-search
python3 scripts/jobbot_skill.py --help
```

`US` 只是示例，应使用用户实际的目标国家，并分别记录居住地、工作许可、就业国家限制与文档设置。导入材料及确认材料归属，不等于自动确认材料里的所有个人声明。完整生成命令见 [英文 README](README.md)，存储约定见 [workspace-storage.md](references/workspace-storage.md)。

## 开发说明

[场景评测](evals/README.md) 提供可复用的虚构案例与验证流程。执行报告和生成物保存在外部工作区；准备样例和程序记账测试不等于真实 Agent 执行或视觉审核。

[AGENTS.md](AGENTS.md) 规定仓库约束；[DESIGN.md](DESIGN.md) 与 [DESIGN_zh.md](DESIGN_zh.md) 维护相同设计决策，修改时同步更新。执行指引和角色提示词继续以英文维护，避免多套流程漂移。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/jobbot_skill.py --help
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

最后一条命令替换为实际安装的 `skill-creator` 路径。项目原创代码及新简历布局采用 [0BSD](LICENSE)。外部安装的 TeX 包和字体保持各自许可；没有打包第三方简历模板。来源与许可约定见[模板说明](references/template-provenance.md)。
