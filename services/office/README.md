# services/office — 办公聚合服务(骨架)

Word 类与 PPT 类是两个子领域,office 是聚合服务(与 sources 同模式,§6.4/§8.6):
`modules/doc` 与 `modules/slides` 自包含脱耦;未来类型(sheets…)新增子模块。
产物落 workspace/exports/;chat 内产物卡片可快速预览(§10.2)。
