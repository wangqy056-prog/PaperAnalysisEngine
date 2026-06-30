"""论文获取模块 - 接入 Semantic Scholar + OpenAlex + arXiv

修复内容：
1. Semantic Scholar: 重试机制 + 指数退避 + API Key 环境变量支持
2. OpenAlex: SSL 降级处理 + 重试机制
3. arXiv: 不变（已正常工作）
"""

import os
import time
import hashlib
import requests
import urllib3
from typing import List, Dict, Optional

# 禁用 InsecureRequestWarning（仅在 SSL 降级时）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _request_with_retry(session: requests.Session, url: str, max_retries: int = 3,
                         timeout: int = 20, **kwargs) -> Optional[requests.Response]:
    """带重试和 SSL 降级的请求"""
    for attempt in range(max_retries):
        try:
            # 第一次尝试正常 SSL
            resp = session.get(url, timeout=timeout, **kwargs)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 2, 30)  # 2, 4, 8... 最多30秒
                print(f"    [限流] 429, 等待 {wait}s 后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.SSLError:
            # SSL 失败，降级为不验证证书
            try:
                print(f"    [SSL] 降级重试 ({attempt+1}/{max_retries})")
                kwargs["verify"] = False
                resp = session.get(url, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    [连接] 失败, 等待 {wait}s 重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                raise
    return None


class SemanticScholarAPI:
    """Semantic Scholar API 封装"""
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RATE_LIMIT_DELAY = 2.0  # 增大间隔避免限流

    def __init__(self, api_key: Optional[str] = None):
        # 优先用参数，其次环境变量
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["x-api-key"] = self.api_key
            print(f"  [Semantic Scholar] 已加载 API Key")
            self.RATE_LIMIT_DELAY = 0.5  # 有 Key 时可以更快
        else:
            print(f"  [Semantic Scholar] 无 API Key (免费限速: 100次/5分钟)")

    def search(self, query: str, limit: int = 50, fields: str = None) -> List[Dict]:
        """搜索论文"""
        if fields is None:
            fields = "title,abstract,authors,venue,year,citationCount,referenceCount,fieldsOfStudy,url,openAccessPdf,externalIds"

        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": fields,
        }

        try:
            resp = _request_with_retry(
                self.session, f"{self.BASE_URL}/paper/search", params=params
            )
            if resp is None:
                return []
            data = resp.json()
            time.sleep(self.RATE_LIMIT_DELAY)
            results = [self._convert(p) for p in data.get("data", [])]
            print(f"    [Semantic Scholar] 找到 {len(results)} 篇")
            return results
        except Exception as e:
            print(f"  [Semantic Scholar] 搜索失败: {e}")
            return []

    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """获取单篇论文详情"""
        params = {
            "fields": "title,abstract,authors,venue,year,citationCount,referenceCount,fieldsOfStudy,url,openAccessPdf,externalIds"
        }
        try:
            resp = _request_with_retry(
                self.session, f"{self.BASE_URL}/paper/{paper_id}", params=params
            )
            if resp is None:
                return None
            time.sleep(self.RATE_LIMIT_DELAY)
            return self._convert(resp.json())
        except Exception as e:
            print(f"  [Semantic Scholar] 获取详情失败: {e}")
            return None

    def _convert(self, raw: dict) -> dict:
        """转换为统一格式"""
        ext_ids = raw.get("externalIds") or {}
        return {
            "id": raw.get("paperId", self._gen_id(raw.get("title", ""))),
            "doi": ext_ids.get("DOI"),
            "title": (raw.get("title") or "").strip(),
            "abstract": raw.get("abstract"),
            "authors": [a.get("name", "") for a in raw.get("authors", [])],
            "journal": raw.get("venue"),
            "year": raw.get("year"),
            "citations": raw.get("citationCount", 0),
            "references": [],
            "url": raw.get("url"),
            "pdf_url": (raw.get("openAccessPdf") or {}).get("url"),
            "fields": raw.get("fieldsOfStudy") or [],
            "source": "semantic_scholar",
        }

    @staticmethod
    def _gen_id(title: str) -> str:
        return hashlib.md5(title.encode()).hexdigest()[:16]


class OpenAlexAPI:
    """OpenAlex API 封装"""
    BASE_URL = "https://api.openalex.org"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, email: str = "user@example.com"):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"PaperAnalysisEngine/1.0 (mailto:{email})"

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        """搜索论文"""
        params = {
            "search": query,
            "per_page": min(limit, 200),
            "filter": "type:article",
        }
        try:
            resp = _request_with_retry(
                self.session, f"{self.BASE_URL}/works", params=params
            )
            if resp is None:
                return []
            data = resp.json()
            time.sleep(self.RATE_LIMIT_DELAY)
            results = [self._convert(p) for p in data.get("results", [])]
            print(f"    [OpenAlex] 找到 {len(results)} 篇")
            return results
        except Exception as e:
            print(f"  [OpenAlex] 搜索失败: {e}")
            return []

    def _convert(self, raw: dict) -> dict:
        """转换为统一格式"""
        doi = raw.get("doi", "")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")

        abstract = self._decode_abstract(raw.get("abstract_inverted_index"))

        primary_location = raw.get("primary_location") or {}
        source_info = primary_location.get("source") or {}
        open_access = raw.get("open_access") or {}

        authors = []
        for a in raw.get("authorships", []):
            author_obj = a.get("author") or {}
            name = author_obj.get("display_name", "")
            if name:
                authors.append(name)

        fields = []
        for c in raw.get("concepts", [])[:5]:
            name = c.get("display_name")
            if name:
                fields.append(name)

        # 提取引用关系 (referenced_works 是 OpenAlex ID 列表)
        referenced_works = raw.get("referenced_works", []) or []
        references = [w.split("/")[-1] for w in referenced_works if w]

        return {
            "id": raw.get("id", "").split("/")[-1] or hashlib.md5(raw.get("title", "").encode()).hexdigest()[:16],
            "doi": doi,
            "title": (raw.get("title") or "").strip(),
            "abstract": abstract,
            "authors": authors,
            "journal": source_info.get("display_name"),
            "year": raw.get("publication_year"),
            "citations": raw.get("cited_by_count", 0),
            "references": references,
            "url": raw.get("id"),
            "pdf_url": open_access.get("oa_url"),
            "fields": fields,
            "source": "openalex",
        }

    @staticmethod
    def _decode_abstract(inverted_index: Optional[dict]) -> Optional[str]:
        """解码 OpenAlex 倒排索引摘要"""
        if not inverted_index:
            return None
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(w for _, w in word_positions)


class ArXivAPI:
    """arXiv API 封装"""
    BASE_URL = "http://export.arxiv.org/api/query"
    RATE_LIMIT_DELAY = 3.0  # arXiv 要求间隔3秒

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        """搜索论文"""
        import xml.etree.ElementTree as ET

        params = {
            "search_query": f"all:{query}",
            "max_results": min(limit, 100),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        try:
            resp = _request_with_retry(
                requests, self.BASE_URL, params=params
            )
            if resp is None:
                return []
            time.sleep(self.RATE_LIMIT_DELAY)

            root = ET.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            papers = []
            for entry in root.findall("atom:entry", ns):
                arxiv_url = entry.find("atom:id", ns).text
                arxiv_id = arxiv_url.split("/")[-1]
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip()
                published = entry.find("atom:published", ns).text
                year = int(published[:4]) if published else None

                authors = [
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)
                ]

                papers.append({
                    "id": f"arxiv_{arxiv_id}",
                    "doi": None,
                    "title": title,
                    "abstract": summary,
                    "authors": authors,
                    "journal": "arXiv",
                    "year": year,
                    "citations": 0,
                    "references": [],
                    "url": arxiv_url,
                    "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}.pdf",
                    "fields": [c.get("term") for c in entry.findall("{http://arxiv.org/schemas/atom}primary_category")],
                    "source": "arxiv",
                })

            print(f"    [arXiv] 找到 {len(papers)} 篇")
            return papers
        except Exception as e:
            print(f"  [arXiv] 搜索失败: {e}")
            return []


# ==================== 统一搜索入口 ====================

class PaperFetcher:
    """多源论文获取统一入口"""

    def __init__(self, ss_api_key: Optional[str] = None):
        self.ss = SemanticScholarAPI(api_key=ss_api_key)
        self.oa = OpenAlexAPI()
        self.arxiv = ArXivAPI()

    def search(self, query: str, limit: int = 50, sources: List[str] = None) -> List[Dict]:
        """多源搜索并整合结果"""
        if sources is None:
            sources = ["ss", "oa", "arxiv"]

        all_results = []

        if "ss" in sources:
            print("  [搜索] Semantic Scholar...")
            all_results.extend(self.ss.search(query, limit))

        if "oa" in sources:
            print("  [搜索] OpenAlex...")
            all_results.extend(self.oa.search(query, limit))

        if "arxiv" in sources:
            print("  [搜索] arXiv...")
            all_results.extend(self.arxiv.search(query, limit))

        unique = self._deduplicate(all_results)
        unique.sort(key=lambda p: (-(p.get("citations") or 0), -(p.get("year") or 0)))

        print(f"  [合并] 去重后 {len(unique)} 篇 (源: {len(all_results)} 篇)")
        return unique[:limit]

    @staticmethod
    def _deduplicate(papers: List[Dict]) -> List[Dict]:
        """基于DOI和标题去重"""
        seen_dois = set()
        seen_titles = set()
        unique = []

        for paper in papers:
            doi = (paper.get("doi") or "").lower().strip()
            title = (paper.get("title") or "").lower().strip()

            if doi and doi in seen_dois:
                continue
            if title and title in seen_titles:
                continue

            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)

            unique.append(paper)

        return unique


if __name__ == "__main__":
    print("=" * 60)
    print("  API 连接测试")
    print("=" * 60)

    fetcher = PaperFetcher()

    # 测试各数据源
    for source_name, source_key in [("Semantic Scholar", "ss"), ("OpenAlex", "oa"), ("arXiv", "arxiv")]:
        print(f"\n--- {source_name} ---")
        results = fetcher.search("large language model", limit=3, sources=[source_key])
        print(f"  结果: {len(results)} 篇")
        for p in results:
            print(f"    [{p.get('year', '?')}] {p.get('title', '?')[:50]}... (引用: {p.get('citations', 0)})")
