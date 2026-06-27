"""Paper Analysis Engine - API Client

Semantic Scholar + OpenAlex API 接入
"""

import requests
import time
import json
from typing import Dict, List, Optional
from urllib.parse import quote

from engine.config import config


class SemanticScholarClient:
    """Semantic Scholar API（免费 100 次/分钟）"""

    BASE = config.SEMANTIC_SCHOLAR_BASE
    SEARCH_FIELDS = (
        "title,abstract,authors,year,citationCount,referenceCount,"
        "fieldsOfStudy,url,openAccessPdf,influentialCitationCount,"
        "journal,externalIds"
    )

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._last_call = 0

    def _rate_limit(self):
        """确保不超过 100 次/分钟"""
        elapsed = time.time() - self._last_call
        if elapsed < 0.6:  # 100/min ≈ 每 0.6 秒一次
            time.sleep(0.6 - elapsed)
        self._last_call = time.time()

    def _headers(self) -> Dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def search(self, query: str, limit: int = 20, offset: int = 0) -> Dict:
        """搜索论文"""
        self._rate_limit()
        url = f"{self.BASE}/paper/search"
        params = {
            "query": query, "limit": limit, "offset": offset,
            "fields": self.SEARCH_FIELDS,
        }
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()

    def get_paper(self, paper_id: str) -> Dict:
        """获取单篇论文详情"""
        self._rate_limit()
        fields = self.SEARCH_FIELDS + ",references,citations"
        r = requests.get(
            f"{self.BASE}/paper/{paper_id}",
            headers=self._headers(),
            params={"fields": fields}
        )
        r.raise_for_status()
        return r.json()

    def search_batch(self, query: str, total: int = 100) -> List[Dict]:
        """批量搜索（自动翻页）"""
        results = []
        offset = 0
        while len(results) < total:
            data = self.search(query, limit=min(100, total - len(results)),
                              offset=offset)
            papers = data.get("data", [])
            if not papers:
                break
            results.extend(papers)
            offset += len(papers)
        return results

    @staticmethod
    def paper_to_dict(ss_paper: Dict) -> Dict:
        """将 SS API 响应转换为系统内部格式"""
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
    """OpenAlex API（2.5 亿 + 论文，完全免费）"""

    BASE = config.OPENALEX_BASE

    def search(self, query: str, limit: int = 20, page: int = 1) -> Dict:
        """搜索论文"""
        url = f"{self.BASE}/works"
        params = {
            "search": query,
            "per_page": limit,
            "page": page,
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def get_work(self, work_id: str) -> Dict:
        """获取单篇论文"""
        url = f"{self.BASE}/works/{work_id}"
        r = requests.get(url)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def work_to_dict(work: Dict) -> Dict:
        """OpenAlex → 内部格式"""
        authors_raw = work.get("authorships", [])
        authors = [{
            "name": a.get("author", {}).get("display_name", ""),
            "affiliation": (a.get("institutions", [{}])[0].get("display_name", "")
                          if a.get("institutions") else ""),
        } for a in authors_raw]

        return {
            "doi": work.get("doi", ""),
            "title": work.get("title", "Untitled"),
            "abstract": "",  # OpenAlex 基础版不返回摘要
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
