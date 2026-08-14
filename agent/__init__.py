"""Agent Runtime:常驻进程,系统的决策者(§9)。

不因用户输入才工作:观察事件流,自主决定行动或沉默。
包结构即职责边界(§5):runtime / master / personas / subagent / policy /
memory / context / skills / hooks / tools / clients。

运行:仓库根目录 `python -m agent.main`(tests 经根 pyproject pythonpath ["."] 解析)。
"""

__version__ = "0.1.0"
