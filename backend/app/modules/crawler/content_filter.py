"""ContentFilterPipeline：Pruning（去噪）+ BM25（核心内容提取）。

数据流：
  raw_html → Pruning.prune() → pruned_html → BM25Filter.filter() → filtered_html
"""
import logging
import re
from typing import List, Tuple

import numpy as np
from bs4 import BeautifulSoup
from lxml import etree, html as lxml_html

from app.core.config import settings

logger = logging.getLogger(__name__)

# jieba 中文分词（可选依赖）
try:
    import jieba
    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False
    logger.warning("jieba not installed; Chinese BM25 tokenization disabled")

# 低价值 class/id 关键词黑名单
_LOW_VALUE_KEYWORDS = {
    "sidebar", "ad", "advertisement", "comment", "comments", "related",
    "footer", "header", "nav", "navigation", "menu", "widget", "social",
    "share", "tags", "tag", "breadcrumb", "toolbar", "tooltip", "popup",
    "modal", "overlay", "banner", "copyright", "disclaimer", "promo",
    "recommend", "hot", "aside", "sidebar-right", "sidebar-left",
}


class Pruning:
    """HTML 去噪：移除低密度节点和低价值区块。"""

    @staticmethod
    def prune(html_str: str) -> str:
        if not html_str or len(html_str) < 500:
            return html_str
        try:
            tree = lxml_html.fromstring(html_str)
        except Exception:
            return html_str

        # 移除低价值节点
        _remove_low_value_nodes(tree)
        # 移除低文本密度节点
        _remove_low_density_nodes(tree, settings.CONTENT_FILTER_PRUNING_MIN_DENSITY)
        # 序列化回字符串
        result = etree.tostring(tree, encoding="unicode", method="html")
        return result


def _remove_low_value_nodes(tree: etree._Element):
    """移除 class/id 匹配黑关键词的节点。"""
    for node in list(tree.iter()):
        if node.tag not in ("div", "section", "aside", "nav", "footer", "header"):
            continue
        cls = node.get("class", "") or ""
        nid = node.get("id", "") or ""
        combined = f"{cls} {nid}".lower()
        for kw in _LOW_VALUE_KEYWORDS:
            if kw in combined:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                break


def _remove_low_density_nodes(tree: etree._Element, min_density: float):
    """移除文本密度（文本长度 / HTML 长度）低于阈值的块级节点。"""
    for node in list(tree.iter()):
        if node.tag not in ("div", "section", "article", "p", "td"):
            continue
        text = _get_text_content(node)
        if not text:
            continue
        raw_html = etree.tostring(node, encoding="unicode", method="html")
        if not raw_html:
            continue
        density = len(text) / max(len(raw_html), 1)
        if density < min_density:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def _get_text_content(node: etree._Element) -> str:
    """获取节点下的纯文本内容。"""
    texts = [node.text or ""]
    for child in node.iter():
        texts.append(child.tail or "")
        # 跳过 script/style 的子内容
        if child.tag in ("script", "style"):
            continue
        texts.append(child.text or "")
    return " ".join(t for t in texts if t).strip()


class BM25Filter:
    """BM25 核心内容提取：按相关性评分保留 Top-K 文本块。

    使用 <title> 和 <meta keywords> 中的词作为查询。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def filter(self, html_str: str) -> str:
        if not html_str or len(html_str) < 500:
            return html_str
        try:
            soup = BeautifulSoup(html_str, "lxml")
        except Exception:
            return html_str

        # 1. 提取查询词
        query_terms = self._extract_query_terms(soup)
        if not query_terms:
            logger.debug("BM25: no query terms from title/meta, returning pruned html as-is")
            return html_str

        # 2. 将 HTML 拆分为文本块
        blocks = self._split_blocks(soup)
        if not blocks:
            return html_str

        # 3. 计算每个块的 BM25 分数
        blocks = self._score_blocks(blocks, query_terms)

        # 4. 按分数阈值 + 最长连续序列选择正文主体块
        selected = self._select_main_content(blocks)

        # 5. 重建 HTML
        result = "".join(b[0] for b in selected)
        return result

    def _extract_query_terms(self, soup: BeautifulSoup) -> List[str]:
        """从 title 和 meta keywords 提取查询词。"""
        terms: List[str] = []
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            terms.extend(self._tokenize(title_tag.get_text(strip=True)))
        meta_kw = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "keywords"})
        if meta_kw and meta_kw.get("content"):
            terms.extend(self._tokenize(meta_kw["content"]))
        # 如果没有 keywords，尝试 description
        if not terms:
            meta_desc = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
            if meta_desc and meta_desc.get("content"):
                terms.extend(self._tokenize(meta_desc["content"]))
        # 去重
        return list(set(t for t in terms if len(t) > 1))

    def _tokenize(self, text: str) -> List[str]:
        """中英文分词，英文按空格拆分，中文使用 jieba 切词。"""
        tokens = []
        for part in re.findall(r"[a-zA-Z]+|[一-龥]+", text):
            if not part:
                continue
            if re.match(r"^[a-zA-Z]+$", part):
                tokens.append(part.lower())
            elif _JIEBA_AVAILABLE:
                tokens.extend(w.lower() for w in jieba.lcut(part) if len(w) > 1)
            elif len(part) >= 2:
                tokens.append(part)
        return tokens

    def _split_blocks(self, soup: BeautifulSoup) -> List[Tuple[str, int, str]]:
        """按语义标签分块，返回 [(html_fragment, position_index, full_text)]。"""
        blocks: List[Tuple[str, int, str]] = []
        tags = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "blockquote", "pre"])
        for idx, tag in enumerate(tags):
            text = tag.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            blocks.append((str(tag), idx, text))
        return blocks

    def _score_blocks(self, blocks: List[Tuple[str, int, str]], query_terms: List[str]) -> List[Tuple[str, float, int]]:
        """为每个块计算 BM25 分数。"""
        n_blocks = len(blocks)
        if n_blocks == 0:
            return [(b[0], 0.0, b[1]) for b in blocks]

        # 文档频率：每个词出现在多少个块中
        df: dict = {}
        for _, _, text in blocks:
            terms = set(self._tokenize(text))
            for t in terms:
                df[t] = df.get(t, 0) + 1

        # 平均块长度
        avg_len = sum(len(b[2]) for b in blocks) / n_blocks

        # 计算每个块的分数
        scored: List[Tuple[str, float, int]] = []
        for html_frag, idx, text in blocks:
            score = 0.0
            block_terms = self._tokenize(text)
            block_len = len(text)
            for term in query_terms:
                if term not in df:
                    continue
                # 词频在当前块中的出现次数
                tf = block_terms.count(term)
                if tf == 0:
                    continue
                idf = np.log((n_blocks - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (block_len / avg_len))
                score += idf * (numerator / denominator) if denominator > 0 else 0
            scored.append((html_frag, score, idx))

        return scored

    def _select_main_content(
        self, blocks: List[Tuple[str, float, int]], score_ratio: float = 0.15
    ) -> List[Tuple[str, float, int]]:
        """通过分数阈值 + 最长连续序列选择正文主体块。

        原理：文章正文由连续的文本块构成，侧边栏/导航是离散的。
        用分数阈值标记"高相关"块后，取最长的连续序列即为正文。

        score_ratio: 低于最高分 * score_ratio 的块视为低分块
        """
        if not blocks:
            return blocks

        max_score = max(b[1] for b in blocks)
        if max_score <= 0:
            return blocks

        threshold = max_score * score_ratio

        # 找最长连续高分区
        best_start = best_len = 0
        cur_start = cur_len = 0

        for i, (_, score, _) in enumerate(blocks):
            if score >= threshold:
                if cur_len == 0:
                    cur_start = i
                cur_len += 1
            else:
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = cur_start
                cur_len = 0

        if cur_len > best_len:
            best_len = cur_len
            best_start = cur_start

        # 最佳区域太小（仅 1 块），回退到全部保留
        if best_len <= 1:
            return blocks

        return blocks[best_start:best_start + best_len]


# 便捷入口（模块级单例，避免每次创建新实例）
_bm25_singleton = BM25Filter()
content_filter_pipeline = lambda html: _bm25_singleton.filter(Pruning.prune(html))
