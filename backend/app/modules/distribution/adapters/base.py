"""分发通道适配器基类。"""
from abc import ABC, abstractmethod

from app.modules.distribution.schemas import WeeklyReport


class DistributionAdapter(ABC):
    """适配器接口：每个通道实现 send 方法。"""

    @abstractmethod
    async def send(self, report: WeeklyReport, config: dict) -> bool:
        """发送周报，成功返回 True，失败抛异常。"""
        ...
