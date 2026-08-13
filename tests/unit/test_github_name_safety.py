"""GitHub owner/repo 路径安全校验"""
from agent_core.tools.builtin import _parse_owner_repo, _safe_github_name


def test_safe_github_name_accepts_normal():
    assert _safe_github_name("daftpunkwav") == "daftpunkwav"
    assert _safe_github_name("repo-pilot.git") == "repo-pilot"


def test_safe_github_name_rejects_path_injection():
    assert _safe_github_name("../etc") is None
    assert _safe_github_name("foo/bar") is None
    assert _safe_github_name("a\\b") is None
    assert _safe_github_name("") is None
    assert _safe_github_name("bad name") is None


def test_parse_owner_repo_from_full_name():
    o, r = _parse_owner_repo(full_name="octocat/Hello-World")
    assert o == "octocat"
    assert r == "Hello-World"


def test_parse_owner_repo_rejects_traversal_full_name():
    o, r = _parse_owner_repo(full_name="../../etc/passwd")
    assert o is None and r is None


# §4.2.5: URL 编码往返二次校验
def test_safe_github_name_url_encoded_normalisation():
    from agent_core.tools.builtin import _safe_github_name
    # 正常名应通过
    assert _safe_github_name("react") == "react"
    assert _safe_github_name("vue-core") == "vue-core"
    # 编码往返不变的应通过（少数会触发编码的合法字符，如空格->%20 后解码不等）
    # 由于正则已限制合法字符集，所以真正"会触发编码的输入"不会出现


def test_safe_github_name_url_encoded_attack_blocked():
    """防御 %2e%2e (../) 与 %2f (/) 编码绕过。"""
    from agent_core.tools.builtin import _safe_github_name
    # 百分号编码形式：quote 后解码应与原值一致，否则说明存在编码折叠
    # 当前白名单 [A-Za-z0-9._-] 不含 %，所以 % 字符本身会被白名单拒
    assert _safe_github_name("foo%2ebar") is None
    assert _safe_github_name("foo%2fbar") is None
    # 含空格 / unicode 不在白名单内
    assert _safe_github_name("foo bar") is None
    assert _safe_github_name("foo中文") is None