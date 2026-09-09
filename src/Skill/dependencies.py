"""Skill 模块依赖注入。

门面模式：从 src/common 导入后重新导出，模块内其它文件不直接触碰 src.common。
"""
from src.common.dependencies import (
    check_token_blacklist,
    get_current_user,
    get_settings,
)
from src.common.models import HealthResponse

# 向后兼容：导出 HealthResponse 供路由使用
SkillHealthResponse = HealthResponse

__all__ = [
    "check_token_blacklist",
    "get_current_user",
    "get_settings",
    "HealthResponse",
    "SkillHealthResponse",
]
