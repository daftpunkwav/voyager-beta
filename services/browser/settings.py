"""browser 服务设置项(§8.7):headless、允许域名。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="browser.headless",
        module="browser",
        type=SettingType.BOOL,
        default=True,
        description="是否无头运行浏览器",
    ),
    SettingDef(
        key="browser.allowed_domains",
        module="browser",
        type=SettingType.JSON,
        default=[],
        description="允许自动化的域名白名单(空=继承 agent 网络权限)",
    ),
]
