"""Paper Analysis Engine - API Client

engine 侧的 API 客户端薄包装层。
实际 HTTP 请求委托给 backend.paper_fetcher（有重试+SSL降级），不再自己发请求。
保留 paper_to_dict() / work_to_dict() 供 CLI (main.py) 使用。
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到 sys.path，使 backend 包可被导入
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.paper_fetcher import SemanticScholarAPI, OpenAlexAPI


class SemanticScholarClient:
    """Semantic Scholar API 客户端（委托 backend.paper_fetcher.SemanticScholarAPI）

    保留 engine 侧的接口签名供 main.py CLI 使用，
    但实际 HTTP 请求由 backend 的重试逻辑处理。
    """

    def __init__(self, api_key: str = None):
        self._api = SemanticScholarAPI(api_key=api_key)

    def search(self, query: str, limit: int = 20, offset: int = 0) -> Dict:
        """搜索论文，返回 backend 格式的结果列表

        注意：backend 版本返回 List[Dict]（已转换），非原始 JSON。
        为兼容旧调用方，包装为 {"data": [...]} 格式。
        """
        results = self._api.search(query, limit=limit)
        return {"data": results}

    def get_paper(self, paper_id: str) -> Dict:
        """获取单篇论文详情"""
        return self._api.get_paper(paper_id) or {}

    def search_batch(self, query: str, total: int = 100) -> List[Dict]:
        """批量搜索（自动翻页）"""
        results = []
        batch_size = 100
        while len(results) < total:
            batch = self._api.search(query, limit=min(batch_size, total - len(results)))
            if not batch:
                break
            results.extend(batch)
        return results

    @staticmethod
    def paper_to_dict(ss_paper: Dict) -> Dict:
        """将 SS API 响应转换为系统内部格式

        兼容 backend._convert() 的输出格式和原始 SS API 响应。
        """
        # 如果已经是 backend 转换后的格式（有 'id' 字段），直接返回
        if "id" in ss_paper and "source" in ss_paper:
            return ss_paper

        # 兼容原始 SS API 响应格式（旧代码路径）
        authors_raw = ss_paper.get("authors", [])
        authors = [{"name": a.get("name"), "authorId": a.get("authorId")}
                   for a in authors_raw]

        return {
            "title": ss_paper.get("title", ""),
            "abstract": ss_paper.get("abstract", ""),
            "authors": authors,
            "year": ss_paper.get("year"),
            "citations": ss_paper.get("citationCount", 0),
            "reference_count": ss_paper.get("referenceCount", 0),
            "journal": ss_paper.get("journal", {}).get("name", "") if ss_paper.get("journal") else "",
            "field": ", ".join(ss_paper.get("fieldsOfStudy", []) or []),
            "url": ss_paper.get("url", ""),
            "pdf_url": ss_paper.get("openAccessPdf", {}).get("url", ""),
            "influential_citation_count": ss_paper.get("influentialCitationCount", 0),
            "source": "semantic_scholar",
            "source_id": ss_paper.get("paperId", ""),
        }


class OpenAlexClient:
    """OpenAlex API 客户端（委托 backend.paper_fetcher.OpenAlexAPI）

    保留 engine 侧的接口签名供 main.py CLI 使用，
    但实际 HTTP 请求由 backend 的重试逻辑处理。
    """

    def __init__(self, email: str = "user@example.com"):
        self._api = OpenAlexAPI(email=email)

    def search(self, query: str, limit: int = 20, page: int = 1) -> Dict:
        """搜索论文，返回 backend 格式的结果列表

        为兼容旧调用方，包装为 {"results": [...]} 格式。
        """
        results = self._api.search(query, limit=limit)
        return {"results": results}

    def get_work(self, work_id: str) -> Dict:
        """获取单篇论文"""
        # backend 没有 get_work，用 search 代替
        # 如果需要单篇查询，直接调用 API
        import requests
        try:
            resp = requests.get(f"{self._api.BASE_URL}/works/{work_id}", timeout=20)
            resp.raise_for_status()
            return self._api._convert(resp.json())
        except Exception:
            return {}

    @staticmethod
    def work_to_dict(work: Dict) -> Dict:
        """将 OpenAlex API 响应转换为系统内部格式

        兼容 backend._convert() 的输出格式和原始 OpenAlex API 响应。
        """
        # 如果已经是 backend 转换后的格式（有 'id' 字段），直接返回
        if "id" in work and "source" in work:
            return work

        # 兼容原始 OpenAlex API 响应格式（旧代码路径）
        authors_raw = work.get("authorships", [])
        authors = [{
            "name": a.get("author", {}).get("display_name", ""),
            "affiliation": (a.get("institutions", [{}])[0].get("display_name", "")
                          if a.get("institutions") else ""),
        } for a in authors_raw]

        return {
            "doi": work.get("doi", ""),
            "title": work.get("title", "Untitled"),
            "abstract": "",
            "authors": authors,
            "year": work.get("publication_year"),
            "citations": work.get("cited_by_count", 0),
            "reference_count": len(work.get("referenced_works", [])),
            "journal": (work.get("primary_location", {}).get("source", {}).get("display_name", "")
                       if work.get("primary_location") else ""),
            "field": work.get("primary_topic", {}).get("display_name", ""),
            "url": work.get("id", ""),
            "source": "openalex",
            "source_id": work.get("id", "").split("/")[-1] if work.get("id") else "",
        }
