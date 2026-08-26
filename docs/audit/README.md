# Voyager 审计与迁移报告

本目录归档 Voyager 项目在 2026-08 期间由 4 轮并行子代理产出的审计报告。所有报告为只读评估,未对任何代码做修改。

## 报告索引

| # | 文件 | 范围 | 字数 | 重点章节 |
|---|---|---|---|---|
| 01 | [01-architecture-and-parity.html](./01-architecture-and-parity.html) | 后端架构 + 7 项铁律落地 | 65 KB | 91 capability / 4 个 zero 矩阵 / 30 条问题 |
| 02 | [02-deep-module-audit.html](./02-deep-module-audit.html) | 深度:Parity + 12 agent 子模块 + 10 services + 7 platform 包 | 145 KB | 50 条 Parity 差异矩阵 / 12 子模块文件清单 |
| 03 | [03-frontend-design-migration.html](./03-frontend-design-migration.html) | 前端样设先行 + 模块独立开发 | 67 KB | 7 大类独立单元 / 5 阶段路径 / 甘特图 |
| 04 | [04-frontend-migration-detail.html](./04-frontend-migration-detail.html) | 旧 RepoPilot → 新 voyager 逐文件级迁移 | 94 KB | 84 IApiClient → 91 capability / 13 SSE 事件映射 / 80+ 组件矩阵 |

## 阅读顺序建议

1. **想快速了解项目**:只读 01 的摘要 + Parity 原则章节
2. **想理解架构设计**:读 01 的 §5-§7(总体架构 / 12 agent / 10 services / 7 platform)
3. **想看 Parity 怎么落地**:读 02 的 §2(50 条差异矩阵)
4. **想看样设怎么迁移**:读 03 的 §5-§7(design token 提取 / 5 阶段路径)
5. **想看具体每文件怎么搬**:读 04 的 §9(逐文件对应表) + §10(7 步迁移路径)
6. **想看风险与回滚**:读 01 的 §8 + 04 的 §11

## 后续

报告本身是过程性产物,所有结论已并入 `architecture.md` 与 `modules/*.md` 模块卡。
本目录保留作为审计追溯。
