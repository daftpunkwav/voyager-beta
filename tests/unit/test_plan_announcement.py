"""plan_execute 过早把「执行计划」当最终答复的检测"""
from agent_core.agents.react import is_plan_announcement


def test_detects_hub_execution_plan_list():
    text = (
        "执行计划：\n"
        "1. 调度 mentor 制定面向 RAG/Chatbot 的 LangChain.js 自学路径\n"
        "2. 调度 curator 整理 LangChain.js 入门与实战资源\n"
        "3. 调度 navigator 输出分阶段路线图与阶段产出\n"
        "4. 待 3 位专家返回后 Hub 汇总输出完整 Markdown 学习计划\n"
        "现开始分派第 1、2、3 步任务。"
    )
    assert is_plan_announcement(text, agent_id="hub") is True


def test_detects_short_hub_dispatch_promise():
    """用户可见卡住点：只承诺调度、不调工具、不写正文。"""
    text = "收到，这就调度 Mentor 给你出一份 CrewAI 的讲解 + 系统学习方案。"
    assert is_plan_announcement(text, agent_id="hub") is True


def test_detects_im_dispatching_now():
    assert is_plan_announcement("好的，正在调度 scout 做速览。", agent_id="hub") is True


def test_rejects_no_further_dispatch_closing():
    text = "专家结果已足够，无需再调度 mentor。"
    assert is_plan_announcement(text, agent_id="hub") is False


def test_rejects_real_learning_answer():
    text = (
        "## LangChain.js 入门路径\n\n"
        "你已有 JavaScript 基础，建议按下面三周推进：\n\n"
        "### 第 1 周：核心抽象\n"
        "- PromptTemplate / ChatPromptTemplate\n"
        "- LCEL Runnable 链路\n\n"
        "### 第 2 周：RAG\n"
        "- Document loader、splitter、vector store\n"
        "- Retriever + 问答链\n"
    )
    assert is_plan_announcement(text, agent_id="hub") is False


def test_short_unrelated_text_not_plan():
    assert is_plan_announcement("你好，有什么可以帮你？", agent_id="hub") is False
