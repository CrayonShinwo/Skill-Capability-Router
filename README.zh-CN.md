# Skill-Capability-Router

通过**生成的技能能力注册表**,把任务路由到最合适的已安装 skill。面向大型技能库由统一工具管理(本机:CC Switch + Claude Code)的环境 —— 846 个技能、20 个分类、一张薄发现表。

- [English](README.md)
- `data/thin-table.md` —— 先查这里
- `data/semantic-table.md` —— 命中后读完整行
- `data/skills.json` —— 完整机器可读目录

## 是什么

| 部分 | 作用 |
| --- | --- |
| **Router skill**(`skill-capability-router`) | 运行时读注册表,把任务路由到确切技能。技能名 = 目录名,如 `xero-automation`。 |
| **生成器**(`scripts/generate_router.py`) | 扫描 CC Switch 技能数据库,确定性重建注册表。零第三方依赖。 |
| **发布目录**(`data/`) | 每个技能:规范名、显示名、分类、能力 `动词 + 宾语`、别名、来源、各客户端启用状态。 |

重复条目已归并:同一工具的下划线/连字符写法合并为一条(如 `anthropic-administrator-automation` 与 `anthropic_administrator-automation`),被合并的写法保留为别名。

## 快速开始

### 1. 安装 router skill

**CC Switch** —— 把本仓库加入技能仓库,然后启用 `skill-capability-router`。技能目录在 `.claude/skills/skill-capability-router/`。

**手动** —— 把该目录复制到 `~/.claude/skills/`(或其他客户端对应位置)。

### 2. 使用

直接用自然语言提问 —— *"automate Xero"*、*"发一条 Slack 消息"*、*"处理这个 PDF"*、*"查询 Snowflake"*、*"拉 CRM 线索"*。router skill 会查薄表并调用匹配的已安装技能。

### 3. 技能变动后重新生成

```bash
python scripts/generate_router.py                     # 默认读 ~/.cc-switch/cc-switch.db
python scripts/generate_router.py --db "C:\path\cc-switch.db"
python scripts/generate_router.py --json data/skills.json   # 用导出目录重跑,无需 DB
python scripts/generate_router.py --validate-only           # 只校验不写文件
```

## 仓库结构

```
.claude/skills/skill-capability-router/   可安装的 router skill(SKILL.md + agents/)
scripts/generate_router.py                确定性注册表生成器
scripts/test_router.py                    用自然语言任务跑路由实测
data/README.md                            生成的索引:文件说明、分类、用法
data/skills.json                          完整目录(规范条目 + 别名 + 启用状态)
data/thin-table.md                        按分类分组的发现表
data/semantic-table.md                    每技能完整行
data/manifest.json                        生成元信息 + 校验报告(gitignored)
```

## 分类

`finance-payments` · `crm-sales` · `marketing-email` · `seo-analytics` · `social-media` · `communication-collab` · `project-management` · `hr-recruiting` · `support-helpdesk` · `dev-tools` · `data-databases` · `ai-ml-media` · `documents-files` · `ecommerce-retail` · `travel-events` · `sports-gaming` · `health-fitness` · `logistics-field` · `education` · `general`

分类关键词表在生成器内(`CATEGORY_KEYWORDS` + `BASE_OVERRIDES`),可自行调整后重新生成,输出确定。

## 说明

- 发布目录反映作者的技能集与客户端启用状态,请按自己的环境重新生成。
- **不含机密。** `data/` 只有技能名、描述、分类、启用标志 —— 无 token、密钥、路径。
- `scripts/generate_router.py` 仅用标准库,已验证(868 行源 → 846 规范条目,0 错误)。`scripts/test_router.py` 用自然语言任务实测路由:`python scripts/test_router.py "query Snowflake"`。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
