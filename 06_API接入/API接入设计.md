# API接入设计

## 一、第三方API接入清单

### 1.1 核心数据源

| API | 官方文档 | 免费额度 | 数据量 | 优先级 |
|-----|---------|---------|--------|--------|
| **Semantic Scholar API** | https://api.semanticscholar.org | 100次/分钟 | 1.7亿+论文 | 高 |
| **OpenAlex API** | https://api.openalex.org | 无限制 | 2.5亿+论文 | 高 |
| **arXiv API** | https://info.arxiv.org/help/api | 无限制 | 200万+预印本 | 高 |
| **PubMed API** | https://pubmed.ncbi.nlm.nih.gov/help/api/ | 无限制 | 3600万+ | 中 |
| **Crossref API** | https://api.crossref.org | 50次/秒 | 1.2亿+ DOI | 中 |
| **Google Scholar** | 无官方API | - | 最全面 | 低 |

### 1.2 辅助数据源

| API | 用途 | 优先级 |
|-----|------|--------|
| **Unpaywall API** | 查找开放获取论文 | 中 |
| **Sci-Hub** | 下载论文全文（注意版权） | 中 |
| **PatentAPI** | 查询专利数据 | 中 |
| **Google Trends** | 分析研究趋势热度 | 低 |
| **World Bank API** | 获取市场数据 | 低 |

---

## 二、API接入实现

### 2.1 Semantic Scholar API

```python
import requests

class SemanticScholarAPI:
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def search_papers(self, query, limit=100):
        """搜索论文"""
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,authors,venue,year,citationCount,referenceCount,fieldsOfStudy,url,openAccessPdf"
        }
        
        response = requests.get(
            f"{self.BASE_URL}/paper/search",
            headers=headers,
            params=params
        )
        
        return response.json()
    
    def get_paper(self, paper_id):
        """获取单篇论文详细信息"""
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        
        params = {
            "fields": "title,abstract,authors,venue,year,citationCount,referenceCount,fieldsOfStudy,url,openAccessPdf,references,citations"
        }
        
        response = requests.get(
            f"{self.BASE_URL}/paper/{paper_id}",
            headers=headers,
            params=params
        )
        
        return response.json()
```

### 2.2 OpenAlex API

```python
import requests

class OpenAlexAPI:
    BASE_URL = "https://api.openalex.org"
    
    def search_papers(self, query, limit=100):
        """搜索论文"""
        params = {
            "search": query,
            "per_page": limit,
            "filter": "type:article"
        }
        
        response = requests.get(f"{self.BASE_URL}/works", params=params)
        return response.json()
    
    def get_paper(self, paper_id):
        """获取单篇论文详细信息"""
        response = requests.get(f"{self.BASE_URL}/works/{paper_id}")
        return response.json()
    
    def search_authors(self, query, limit=20):
        """搜索作者"""
        params = {
            "search": query,
            "per_page": limit
        }
        
        response = requests.get(f"{self.BASE_URL}/authors", params=params)
        return response.json()
    
    def search_concepts(self, query, limit=20):
        """搜索概念/主题"""
        params = {
            "search": query,
            "per_page": limit
        }
        
        response = requests.get(f"{self.BASE_URL}/concepts", params=params)
        return response.json()
```

### 2.3 arXiv API

```python
import requests
import xml.etree.ElementTree as ET

class ArXivAPI:
    BASE_URL = "http://export.arxiv.org/api/query"
    
    def search_papers(self, query, limit=100):
        """搜索论文"""
        params = {
            "search_query": query,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        
        response = requests.get(self.BASE_URL, params=params)
        root = ET.fromstring(response.content)
        
        papers = []
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            paper = {
                "id": entry.find("{http://www.w3.org/2005/Atom}id").text,
                "title": entry.find("{http://www.w3.org/2005/Atom}title").text,
                "summary": entry.find("{http://www.w3.org/2005/Atom}summary").text,
                "published": entry.find("{http://www.w3.org/2005/Atom}published").text,
                "authors": [
                    author.find("{http://www.w3.org/2005/Atom}name").text
                    for author in entry.findall("{http://www.w3.org/2005/Atom}author")
                ],
                "categories": [
                    cat.text for cat in entry.findall("{http://www.w3.org/2005/Atom}category")
                ]
            }
            papers.append(paper)
        
        return papers
    
    def get_paper(self, arxiv_id):
        """获取单篇论文"""
        params = {
            "id_list": arxiv_id
        }
        
        response = requests.get(self.BASE_URL, params=params)
        root = ET.fromstring(response.content)
        
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        if entry:
            return {
                "id": entry.find("{http://www.w3.org/2005/Atom}id").text,
                "title": entry.find("{http://www.w3.org/2005/Atom}title").text,
                "summary": entry.find("{http://www.w3.org/2005/Atom}summary").text,
                "published": entry.find("{http://www.w3.org/2005/Atom}published").text,
                "updated": entry.find("{http://www.w3.org/2005/Atom}updated").text
            }
        return None
```

---

## 三、API数据整合

### 3.1 数据清洗与标准化

```python
class DataIntegrator:
    """整合多源API数据"""
    
    def __init__(self):
        self.semantic_scholar = SemanticScholarAPI()
        self.openalex = OpenAlexAPI()
        self.arxiv = ArXivAPI()
    
    def search_papers(self, query, limit=50):
        """多源搜索并整合"""
        results = []
        
        # 并行调用多个API
        ss_results = self.semantic_scholar.search_papers(query, limit)
        oa_results = self.openalex.search_papers(query, limit)
        arxiv_results = self.arxiv.search_papers(query, limit)
        
        # 转换为统一格式
        for paper in ss_results.get("data", []):
            results.append(self._convert_ss_paper(paper))
        
        for paper in oa_results.get("results", []):
            results.append(self._convert_oa_paper(paper))
        
        for paper in arxiv_results:
            results.append(self._convert_arxiv_paper(paper))
        
        # 去重（基于DOI或标题）
        results = self._deduplicate(results)
        
        # 排序（基于引用量+时间）
        results = self._sort_results(results)
        
        return results[:limit]
    
    def _convert_ss_paper(self, paper):
        """转换Semantic Scholar格式"""
        return {
            "id": paper.get("paperId"),
            "doi": paper.get("doi"),
            "title": paper.get("title"),
            "abstract": paper.get("abstract"),
            "authors": [a.get("name") for a in paper.get("authors", [])],
            "journal": paper.get("venue"),
            "year": paper.get("year"),
            "citations": paper.get("citationCount"),
            "references": paper.get("referenceCount"),
            "url": paper.get("url"),
            "pdf_url": paper.get("openAccessPdf", {}).get("url"),
            "fields": paper.get("fieldsOfStudy"),
            "source": "semantic_scholar"
        }
    
    def _convert_oa_paper(self, paper):
        """转换OpenAlex格式"""
        return {
            "id": paper.get("id"),
            "doi": paper.get("doi"),
            "title": paper.get("title"),
            "abstract": paper.get("abstract"),
            "authors": [a.get("author", {}).get("display_name") for a in paper.get("authorships", [])],
            "journal": paper.get("primary_location", {}).get("source", {}).get("display_name"),
            "year": paper.get("publication_year"),
            "citations": paper.get("cited_by_count"),
            "references": None,
            "url": paper.get("id"),
            "pdf_url": paper.get("open_access", {}).get("oa_url"),
            "fields": None,
            "source": "openalex"
        }
    
    def _convert_arxiv_paper(self, paper):
        """转换arXiv格式"""
        return {
            "id": paper.get("id"),
            "doi": None,
            "title": paper.get("title"),
            "abstract": paper.get("summary"),
            "authors": paper.get("authors"),
            "journal": "arXiv",
            "year": int(paper.get("published", "")[:4]) if paper.get("published") else None,
            "citations": None,
            "references": None,
            "url": paper.get("id"),
            "pdf_url": paper.get("id").replace("abs", "pdf") + ".pdf",
            "fields": paper.get("categories"),
            "source": "arxiv"
        }
    
    def _deduplicate(self, results):
        """去重"""
        seen_dois = set()
        seen_titles = set()
        unique_results = []
        
        for paper in results:
            doi = paper.get("doi")
            title = paper.get("title", "").strip().lower()
            
            if doi and doi in seen_dois:
                continue
            if title and title in seen_titles:
                continue
            
            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)
            
            unique_results.append(paper)
        
        return unique_results
    
    def _sort_results(self, results):
        """排序"""
        def sort_key(paper):
            citations = paper.get("citations", 0) or 0
            year = paper.get("year", 0) or 0
            return (-citations, -year)
        
        return sorted(results, key=sort_key)
```

---

## 四、API调用策略

### 4.1 限流与重试

```python
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class APIClient:
    """带限流和重试的API客户端"""
    
    def __init__(self, max_retries=3, backoff_factor=1):
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.rate_limit = {
            "semantic_scholar": {"limit": 100, "remaining": 100, "reset_time": 0},
            "openalex": {"limit": float('inf'), "remaining": float('inf'), "reset_time": 0}
        }
    
    def _wait_for_rate_limit(self, source):
        """等待限流恢复"""
        limit_info = self.rate_limit.get(source, {})
        if limit_info.get("remaining", 1) <= 0:
            reset_time = limit_info.get("reset_time", 0)
            wait_time = max(0, reset_time - time.time()) + 1
            time.sleep(wait_time)
            limit_info["remaining"] = limit_info.get("limit", 100)
    
    def call_api(self, source, func, *args, **kwargs):
        """调用API并处理限流"""
        self._wait_for_rate_limit(source)
        
        try:
            response = func(*args, **kwargs)
            
            # 更新限流信息
            if hasattr(response, 'headers'):
                remaining = response.headers.get("x-ratelimit-remaining")
                reset_time = response.headers.get("x-ratelimit-reset")
                if remaining:
                    self.rate_limit[source]["remaining"] = int(remaining)
                if reset_time:
                    self.rate_limit[source]["reset_time"] = int(reset_time)
            
            return response
        
        except requests.exceptions.RequestException as e:
            self.rate_limit[source]["remaining"] -= 1
            raise e
```

---

## 五、论文全文获取

### 5.1 全文获取策略

```python
class FullTextFetcher:
    """获取论文全文"""
    
    def __init__(self):
        self.unpaywall_api = "https://api.unpaywall.org/v2"
    
    def get_fulltext(self, doi):
        """获取论文全文"""
        # 1. 先查Unpaywall
        unpaywall_result = self._check_unpaywall(doi)
        if unpaywall_result and unpaywall_result.get("is_oa"):
            return unpaywall_result.get("best_oa_location", {}).get("url")
        
        # 2. 查Semantic Scholar开放获取
        # (已经在搜索时获取)
        
        # 3. 尝试arXiv
        arxiv_url = self._check_arxiv(doi)
        if arxiv_url:
            return arxiv_url
        
        # 4. 尝试作者个人主页
        # (需要额外搜索)
        
        return None
    
    def _check_unpaywall(self, doi):
        """检查Unpaywall"""
        response = requests.get(f"{self.unpaywall_api}/{doi}", params={"email": "your@email.com"})
        return response.json()
    
    def _check_arxiv(self, doi):
        """检查arXiv"""
        # 通过DOI查找arXiv版本
        params = {
            "search_query": f"doi:{doi}"
        }
        response = requests.get("http://export.arxiv.org/api/query", params=params)
        root = ET.fromstring(response.content)
        
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            arxiv_id = entry.find("{http://www.w3.org/2005/Atom}id").text
            return arxiv_id.replace("abs", "pdf") + ".pdf"
        
        return None
```

---

**最后更新**：2026-06-27