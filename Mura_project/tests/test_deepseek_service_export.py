from mura.deepseek import DeepSeekPipelineService
from mura.deepseek.service import DeepSeekPipelineService as BaseDeepSeekPipelineService


def test_public_deepseek_service_uses_the_single_base_class() -> None:
    assert DeepSeekPipelineService is BaseDeepSeekPipelineService
