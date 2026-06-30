"""领研网爬虫模块 - 抓取最新论文列表

领研网（https://www.linkresearcher.com/theses）使用 React SPA，服务器端渲染
返回的是缓存的旧数据（2024-2025 年）。要拿到最新论文（2026 年），必须用
真浏览器执行 JavaScript 后从 DOM 提取。

本模块使用 Playwright（headless Chromium）实现真浏览器渲染，并加了 30 分钟
缓存避免每次请求都启动浏览器（启动耗时 5-10 秒）。
"""

import re
import sys
import time
import hashlib
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.linkresearcher.com"
THESES_URL = f"{BASE_URL}/theses"

# Windows 控制台 UTF-8 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ==================== 缓存 ====================
# Playwright 启动一次需要 5-10 秒，所以加缓存避免频繁启动
# 缓存有效期内重复请求直接返回缓存数据
_CACHE = {
    "papers": [],       # 缓存的论文列表
    "fetched_at": 0,   # 上次抓取时间戳
    "pages": 0,        # 上次抓取的页数
}
CACHE_TTL = 1800  # 30 分钟


def _is_cache_valid(pages: int) -> bool:
    """检查缓存是否有效"""
    if not _CACHE["papers"]:
        return False
    if _CACHE["pages"] < pages:
        return False
    age = time.time() - _CACHE["fetched_at"]
    return age < CACHE_TTL


def _clear_cache():
    """清空缓存（强制下次重新抓取）"""
    _CACHE["papers"] = []
    _CACHE["fetched_at"] = 0
    _CACHE["pages"] = 0


# ==================== 主入口 ====================

def fetch_latest_papers(pages: int = 1) -> List[Dict]:
    """抓取领研网最新论文列表

    Args:
        pages: 抓取页数（每页 20 篇）

    Returns:
        论文列表，每篇包含: title, journal, date, authors, url, raw_id
    """
    # 检查缓存
    if _is_cache_valid(pages):
        cached = _CACHE["papers"][: pages * 20]
        print(f"  [领研网] 命中缓存: 返回 {len(cached)} 篇 (age={int(time.time() - _CACHE['fetched_at'])}s)")
        return cached

    # 用 Playwright 抓取
    try:
        papers = _fetch_with_playwright(pages)
    except Exception as e:
        print(f"  [领研网] Playwright 抓取失败: {e}")
        # 回退到 requests（虽然只能拿到旧的 SSR 数据，但至少不报错）
        papers = _fetch_with_requests(pages)

    if not papers:
        # 如果 Playwright 和 requests 都失败，返回缓存（即使过期）
        if _CACHE["papers"]:
            print(f"  [领研网] 抓取失败，返回过期缓存: {len(_CACHE['papers'])} 篇")
            return _CACHE["papers"][: pages * 20]
        return []

    # 更新缓存
    _CACHE["papers"] = papers
    _CACHE["fetched_at"] = time.time()
    _CACHE["pages"] = pages

    print(f"  [领研网] 共 {len(papers)} 篇（已更新缓存）")
    return papers


def _fetch_with_playwright(pages: int) -> List[Dict]:
    """用 Playwright 启动真浏览器渲染领研网首页

    Playwright 能执行 React 的 JS，拿到最新数据；
    requests 只能拿到 SSR 的旧缓存数据。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright 未安装，请运行 pip install playwright && playwright install chromium")

    print(f"  [领研网] 启动 Playwright Chromium 抓取 {pages} 页...")

    all_papers = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(THESES_URL, wait_until="networkidle", timeout=30000)

            # 提取第 1 页
            papers = _extract_papers_from_dom(page)
            all_papers.extend(papers)
            print(f"  [领研网] 第 1 页: {len(papers)} 篇")

            # 翻页：点击"下一页"按钮（如果存在）
            for page_num in range(2, pages + 1):
                # 领研网用 React 分页，UI 上有"下一页"按钮
                # 先尝试找 "下一页" 或 ">" 按钮
                next_button = _find_next_page_button(page)
                if not next_button:
                    print(f"  [领研网] 第 {page_num} 页: 没有下一页按钮，停止")
                    break

                # 点击并等待网络空闲
                next_button.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)  # 额外等待 React 重渲染

                papers = _extract_papers_from_dom(page)
                if not papers:
                    print(f"  [领研网] 第 {page_num} 页: 提取失败")
                    break
                all_papers.extend(papers)
                print(f"  [领研网] 第 {page_num} 页: {len(papers)} 篇")
        finally:
            browser.close()

    # 去重（不同页可能有重复）
    seen = set()
    unique = []
    for p in all_papers:
        key = p["title"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def _find_next_page_button(page):
    """在 DOM 上找'下一页'按钮"""
    # 尝试多种选择器
    selectors = [
        'button:has-text("下一页")',
        'a:has-text("下一页")',
        '.ant-pagination-next',
        '[aria-label="next"]',
        'li[title="下一页"]',
        # 领研网可能用图标按钮
        'button:has(svg.anticon-right)',
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return btn
        except Exception:
            continue
    return None


def _extract_papers_from_dom(page) -> List[Dict]:
    """从 Playwright 渲染后的 DOM 提取论文信息

    使用 JavaScript 一次性提取所有论文，比 Python 循环 query_selector 快得多。
    论文在 DOM 中的结构（从外层测试得知）：
        <a href="/theses/UUID">
          <div>中文标题</div>
          <div>论文标题：英文标题</div>
          <div>作者：xxx</div>
          <div>期刊：xxx</div>
          <div>发表日期：2026/06/26</div>
          <div>标签1</div><div>标签2</div>...
        </a>
    """
    papers = page.evaluate(
        """
        () => {
            const papers = [];
            // 找所有指向 /theses/UUID 的链接
            const links = document.querySelectorAll('a[href*="/theses/"]');
            links.forEach(link => {
                const href = link.href;
                // 跳过导航类链接
                if (href.endsWith('/theses') || href.endsWith('/theses/')) return;
                if (href.includes('/theses?')) return;

                const rawId = href.split('/theses/')[1] || '';
                if (!rawId || rawId.length < 8) return;

                // 找到论文卡片容器（向上遍历找到包含"期刊"的祖先 div）
                let card = link;
                for (let i = 0; i < 6; i++) {
                    if (card.parentElement) {
                        const text = card.innerText || '';
                        if (text.includes('期刊') && text.length > 50 && text.length < 2000) break;
                        card = card.parentElement;
                    }
                }
                const text = card.innerText || '';
                if (!text.includes('期刊')) return;

                // 解析字段
                const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);

                // 中文标题：通常在链接自身的文字里
                const title = (link.innerText || '').trim().split('\\n')[0] || lines[0] || '';

                // 提取各字段
                let enTitle = '', journal = '', date = '', authors = '';
                const tags = [];

                for (const line of lines) {
                    if (line.startsWith('论文标题：') || line.startsWith('论文标题:')) {
                        enTitle = line.replace(/^论文标题[：:]/, '').trim();
                    } else if (line.startsWith('期刊：') || line.startsWith('期刊:')) {
                        journal = line.replace(/^期刊[：:]/, '').trim();
                    } else if (line.startsWith('发表日期：') || line.startsWith('发表日期:')) {
                        date = line.replace(/^发表日期[：:]/, '').trim();
                    } else if (line.startsWith('作者：') || line.startsWith('作者:')) {
                        authors = line.replace(/^作者[：:]/, '').trim();
                    }
                }

                // 提取日期（如果"发表日期"行为空，扫描文本）
                if (!date) {
                    const m = text.match(/(202[0-9]\\/\\d{2}\\/\\d{2})/);
                    if (m) date = m[1];
                }

                if (!title || title.length < 3) return;

                papers.push({
                    id: rawId.substring(0, 16),
                    raw_id: rawId,
                    title: title,
                    en_title: enTitle,
                    journal: journal,
                    date: date,
                    authors: authors,
                    tags: tags.slice(0, 5),
                    url: href,
                    source: 'linkresearcher',
                });
            });
            return papers;
        }
        """
    )
    return papers or []


# ==================== requests 后备方案 ====================
# 当 Playwright 失败时使用（只能拿到 SSR 缓存的旧数据）

def _fetch_with_requests(pages: int) -> List[Dict]:
    """用 requests 抓取（后备方案，只能拿到旧的 SSR 数据）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    all_papers = []
    for page_num in range(1, pages + 1):
        url = THESES_URL if page_num == 1 else f"{THESES_URL}?page={page_num}"
        try:
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                print(f"  [领研网] 第 {page_num} 页请求失败: HTTP {resp.status_code}")
                continue
            papers = _parse_html(resp.text)
            all_papers.extend(papers)
            print(f"  [领研网] 第 {page_num} 页: 找到 {len(papers)} 篇")
            if page_num < pages:
                time.sleep(2)
        except Exception as e:
            print(f"  [领研网] 第 {page_num} 页抓取失败: {e}")

    # 去重
    seen = set()
    unique = []
    for p in all_papers:
        key = p["title"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _parse_html(html: str) -> List[Dict]:
    """解析领研网 SSR HTML（后备方案）

    注意：SSR 返回的是缓存的旧数据，最新论文请用 Playwright 渲染。
    """
    papers = []
    link_pattern = re.compile(
        r'href="(https://www\.linkresearcher\.com/theses/[0-9a-f\-]+)"',
        re.IGNORECASE
    )
    link_matches = list(link_pattern.finditer(html))

    for i, match in enumerate(link_matches):
        url = match.group(1)
        raw_id = url.split("/")[-1]
        start = match.end()
        end = link_matches[i + 1].start() if i + 1 < len(link_matches) else min(start + 5000, len(html))
        block = html[start:end]

        title = ""
        div_pattern = re.compile(r'>([^<]{5,})</div>', re.DOTALL)
        divs = div_pattern.findall(block[:2000])
        for div_text in divs:
            text = div_text.strip()
            if any(kw in text for kw in ["作者", "期刊", "发表日期", "标签", "doi", "DOI"]):
                continue
            if re.match(r'^\d{4}/\d{2}/\d{2}', text):
                continue
            if len(text) < 8 and not re.search(r'[\u4e00-\u9fff]', text):
                continue
            title = text
            break

        if not title or len(title) < 5:
            continue

        journal = ""
        jm = re.search(r'期刊[：:]\s*([^<\n]+)', block)
        if jm:
            journal = jm.group(1).strip()

        date = ""
        dm = re.search(r'发表日期[：:]\s*(\d{4}/\d{2}/\d{2})', block)
        if dm:
            date = dm.group(1)
        else:
            dm = re.search(r'(\d{4}/\d{2}/\d{2})', block)
            if dm:
                date = dm.group(1)

        authors = ""
        am = re.search(r'作者[：:]\s*([^<\n]+)', block)
        if am:
            authors = am.group(1).strip()

        papers.append({
            "id": hashlib.md5(title.encode()).hexdigest()[:16],
            "raw_id": raw_id,
            "title": title,
            "journal": journal,
            "date": date,
            "authors": authors,
            "tags": [],
            "url": url,
            "source": "linkresearcher",
        })

    return papers


# ==================== 详情页 ====================

def fetch_paper_detail(url: str) -> Optional[Dict]:
    """抓取领研网论文详情页

    获取中文概要、英文标题、DOI 等信息。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return None

        html = resp.text
        detail = {}

        en_match = re.search(r'论文标题[：:]\s*([^\n<]+)', html)
        if en_match:
            detail["en_title"] = en_match.group(1).strip()

        doi_match = re.search(r'DOI[：:]\s*([^\s<]+)', html)
        if doi_match:
            detail["doi"] = doi_match.group(1).strip()

        abstract_match = re.search(r'导读[：:]\s*([^<]+(?:。|；|\.\s))', html)
        if abstract_match:
            detail["abstract_cn"] = abstract_match.group(1).strip()

        journal_match = re.search(r'期刊[：:]\s*\*?([^<*]+)\*?', html)
        if journal_match:
            detail["journal"] = journal_match.group(1).strip()

        author_match = re.search(r'第一作者[：:]\s*([^\n<]+)', html)
        if author_match:
            detail["first_author"] = author_match.group(1).strip()

        year_match = re.search(r'发表年份[：:]\s*(\d{4})', html)
        if year_match:
            detail["year"] = int(year_match.group(1))

        return detail

    except Exception as e:
        print(f"  [领研网] 详情抓取失败: {e}")
        return None


def search_by_title(title: str) -> Optional[Dict]:
    """通过标题在领研网搜索论文"""
    search_url = f"{BASE_URL}/searchall"
    params = {"query": title, "tab": "theses"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        resp = requests.get(search_url, params=params, headers=headers, timeout=15, verify=False)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return None

        papers = _parse_html(resp.text)
        if papers:
            return papers[0]
        return None
    except Exception as e:
        print(f"  [领研网] 搜索失败: {e}")
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("  领研网爬虫测试（Playwright 模式）")
    print("=" * 60)

    papers = fetch_latest_papers(pages=1)

    print(f"\n找到 {len(papers)} 篇最新论文:\n")
    for i, p in enumerate(papers[:10], 1):
        print(f"  {i:2d}. [{p.get('date','')}] {p['title']}")
        if p.get('journal'):
            print(f"      期刊: {p['journal']}")
        if p.get('en_title'):
            print(f"      英文: {p['en_title'][:60]}")
        print(f"      链接: {p['url']}")
        print()
