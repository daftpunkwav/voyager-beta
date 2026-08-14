"""记忆系统测试(§9.11):四类记忆 + 门面聚合检索 + 保留策略。"""


from agent.memory import Memory


class TestStores:
    def test_profile_set_get_render(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("语言偏好", "中文")
        m.profile.set("主题", "深色")
        assert m.profile.get("语言偏好") == "中文"
        assert m.profile.get("不存在", "默认") == "默认"
        assert "语言偏好" in m.profile.render()
        m.profile.delete("主题")
        assert "主题" not in m.profile.all()
        m.close()

    def test_episodic_log_search_purge(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "用户在看 langgraph 的 README", run_id="r1")
        m.episodic.log("tool", "read_file", run_id="r1")
        assert len(m.episodic.recent()) == 2
        assert len(m.episodic.recent(kind="tool")) == 1
        assert m.episodic.search("langgraph")[0]["run_id"] == "r1"
        assert m.episodic.purge(older_than_days=0) == 2  # cutoff=now,全部超期
        assert m.episodic.recent() == []
        m.close()

    def test_semantic_triple_query(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.semantic.add("langgraph", "类型", "Agent 编排框架", node_id="n1")
        m.semantic.add("langgraph", "作者", "LangChain")
        assert len(m.semantic.query(subject="langgraph")) == 2
        assert m.semantic.query(keyword="编排")[0]["node_id"] == "n1"
        assert m.semantic.query(relation="作者")[0]["object"] == "LangChain"
        m.close()

    def test_working_bounded(self) -> None:
        m = Memory("/nonexistent-should-not-touch")  # 只用 working,不触碰磁盘
        for i in range(250):
            m.working.add("user", f"第{i}句")
        assert len(m.working.recent(500)) == 200  # maxlen 有界
        assert m.working.recent(1)[0]["content"] == "第249句"
        m.working.clear()
        assert m.working.recent() == []


class TestFacade:
    def test_recall_aggregates_with_source(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("兴趣", "langgraph")
        m.episodic.log("consider", "用户导入了 langgraph")
        m.semantic.add("langgraph", "类型", "框架")
        hits = m.recall("langgraph")
        sources = {h["from"] for h in hits}
        assert sources == {"profile", "episodic", "semantic"}
        m.close()

    def test_retention_zero_means_agent_managed(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "x")
        assert m.purge(retention_days=0) == {"episodic": 0}  # 不自动清
        assert len(m.episodic.recent()) == 1
        assert m.purge(retention_days=90)["episodic"] == 0  # 未超期
        m.close()
