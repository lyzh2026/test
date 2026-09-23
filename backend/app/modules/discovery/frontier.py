"""URLFrontier：优先级队列 + 同源路径配额熔断。

参考 Heritrix URL Frontier 设计：
- heapq 优先队列，按评分降序出队
- 同一路径前缀（前 3 层）超过配额则熔断，防止教师页/导航页洪水
- URL 去重
"""

import heapq
from urllib.parse import urlparse

from app.modules.discovery.scoring import ScoredLink


class URLFrontier:
    def __init__(self, *, default_quota: int = 20, max_size: int = 500):
        self._heap: list[tuple[int, int, ScoredLink]] = []  # (-score, counter, link)
        self._counter = 0
        self._seen: set[str] = set()
        self._prefix_counts: dict[str, int] = {}
        self._default_quota = default_quota
        self._max_size = max_size

    @staticmethod
    def _get_prefix(url: str) -> str:
        """提取路径前缀：取前 3 层路径。

        /info/1177/125704.htm → /info/1177/
        /news/2026/05/article.htm → /news/2026/
        """
        path = urlparse(url).path
        parts = [p for p in path.split("/") if p]
        return "/" + "/".join(parts[:3]) + "/" if len(parts) >= 3 else path

    def push(self, scored_link: ScoredLink, *, skip_quota: bool = False) -> bool:
        """入队。返回 True 表示成功，False 表示被配额熔断或去重。

        skip_quota=True 时跳过路径配额检查（用于 hub_base 等手动策展入口）。
        """
        url = scored_link.url
        if url in self._seen:
            return False
        if len(self._heap) >= self._max_size:
            return False

        if not skip_quota:
            prefix = self._get_prefix(url)
            count = self._prefix_counts.get(prefix, 0)
            if count >= self._default_quota:
                return False
            self._prefix_counts[prefix] = count + 1

        self._seen.add(url)
        heapq.heappush(self._heap, (-scored_link.score, self._counter, scored_link))
        self._counter += 1
        return True

    def pop(self) -> ScoredLink | None:
        """出队最高分的 URL。返回 None 表示队列空。"""
        if not self._heap:
            return None
        _, _, link = heapq.heappop(self._heap)
        return link

    @property
    def size(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def clear(self) -> int:
        """清空队列，返回被清除的 URL 数量。保留 _seen 去重集合。"""
        count = len(self._heap)
        self._heap.clear()
        self._prefix_counts.clear()
        return count
