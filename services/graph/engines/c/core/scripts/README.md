# scripts/ — 构建与测试入口

> **Voyager 入口：** 构建本仓 MCP 索引引擎请用 [`build.ps1`](build.ps1)（`make -f Makefile graph-engine`）。  
> **上游遗留：** [`setup.sh`](setup.sh) 仍是 DeusData `graph-engine` 安装叙事，勿当作 Voyager 产品安装器。  
> Makefile：构建入口为 `Makefile`（原 `Makefile.rp`）；上游 `Makefile.cbm` 别名已随改名删除。
>
> 上游的发布打包 / 压测 / 安全审计 / CI 门禁等运维脚本已在迁入 Voyager 时清理
> （Voyager 仅使用构建与基础测试链；见仓库 git 历史获取被清理脚本）。

## 保留的脚本

| 脚本 | 用途 |
|---|---|
| `build.sh` / `build.ps1` | 生产构建（产物 `graph-engine`） |
| `clean.sh` / `env.sh` / `path-safety.sh` | 清理、构建环境、路径安全前置 |
| `setup.sh` | 上游开发环境安装（Linux/macOS） |
| `test.sh` / `test-windows.ps1` / `run-tests-parallel.sh` | 测试链 |
| `check-no-test-skips.sh` / `check-nolint-whitelist.sh`(+`.txt`) / `lint-mem-gate.py`(+`.txt`) | 静态策略检查 |
| `lint.sh` | clang-tidy + cppcheck + clang-format |
| `smoke-test.sh` | 上游功能冒烟（`src/foundation/mem.c` 的内存 wiring 说明锚定于此） |
| `ci/` | test.sh 引用的二进制组成检查 |
| `gen-integrations-hash.sh` | 再生成 `assets/engine-integrations.json` 的哈希 |
| `gen-py-stdlib.py` | 再生成 Python LSP 标准库类型数据（见 THIRD_PARTY.md） |
| `extract_nomic_vectors.py` | 再生成 nomic 嵌入向量（见 THIRD_PARTY.md） |
| `vendored-checksums.txt` / `security-allowlist.txt` | vendored 完整性记录 / URL 允许列表记录 |
| `hooks/` | setup.sh 激活的 pre-commit 钩子 |

每个入口支持 `--help`，未知参数报 usage error。
