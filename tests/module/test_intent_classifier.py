"""意图分类器单元测试"""
import pytest
from agent_core.agents.intent import IntentClassifier


@pytest.mark.asyncio
async def test_classify_scout_rule():
    clf = IntentClassifier(llm=None)
    result = await clf.classify("帮我快速分析一下这个仓库")
    assert result.agent_id == "scout"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_navigator_rule():
    clf = IntentClassifier(llm=None)
    result = await clf.classify("帮我规划学习路径")
    assert result.agent_id == "navigator"


@pytest.mark.asyncio
async def test_classify_multi_intent():
    clf = IntentClassifier(llm=None)
    result = await clf.classify("分析这个项目并且帮我规划学习路线")
    assert result.is_multi is True
    assert len(result.sub_intents) >= 2


@pytest.mark.asyncio
async def test_classify_fallback_hub():
    clf = IntentClassifier(llm=None)
    result = await clf.classify("你好啊")
    assert result.agent_id == "hub"
