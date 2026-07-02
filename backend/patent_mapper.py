#!/usr/bin/env python
"""Patent Citation Mapper — 通过 PatentsView 免费 API 查询论文-专利引用映射

替代原 BigQuery 方案，无需 GCP 私钥，纯 HTTP 调用。

用法：
  python patent_mapper.py --test 5       # 测试模式：处理 5 篇
  python patent_mapper.py --limit 1151   # 批量模式：处理全部
"""

import os
import re
import time
import argparse
import requests
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db import get_connection

# PatentsView API 已于 2026-03-20 迁移到 USPTO Open Data Portal
# 新端点：https://search.patentsview.org/api/v1/patent/ (GET)
# 旧端点：https://api.patentsview.org/patents/query (POST) 已废弃返回 HTML
PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"
PATENTSVIEW_OLD_URL = "https://api.patentsview.org/patents/query"


# ──────────────────────────────────────────────
#  数据库
# ──────────────────────────────────────────────

def ensure_patent_table():
    """创建 patent_citations 和 patent_query_log 表"""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patent_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT NOT NULL,
            patent_id TEXT NOT NULL,
            assignee TEXT,
            publication_date TEXT,
            country_code TEXT,
            npl_text TEXT,
            matched_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(paper_id, patent_id)
        );
        CREATE TABLE IF NOT EXISTS patent_query_log (
            paper_id TEXT PRIMARY KEY,
            match_count INTEGER DEFAULT 0,
            queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def get_all_papers():
    """获取所有论文（id, title）"""
    conn = get_connection()
    rows = conn.execute("SELECT id, title FROM papers ORDER BY id").fetchall()
    conn.close()
    return rows


def get_unqueried_papers(limit=0):
    """获取尚未查询专利的论文"""
    conn = get_connection()
    if limit:
        rows = conn.execute("""
            SELECT p.id, p.title FROM papers p
            WHERE p.id NOT IN (SELECT paper_id FROM patent_query_log)
            ORDER BY p.id LIMIT ?
        """, (limit,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.id, p.title FROM papers p
            WHERE p.id NOT IN (SELECT paper_id FROM patent_query_log)
            ORDER BY p.id
        """).fetchall()
    conn.close()
    return rows


def mark_paper_queried(paper_id, match_count):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO patent_query_log (paper_id, match_count)
        VALUES (?, ?)
    """, (paper_id, match_count))
    conn.commit()
    conn.close()


def save_results(results):
    """保存查询结果到 patent_citations，同时标记 queried

    字段映射（PatentsView → patent_citations 表）：
      patent_id       → patent_id
      patent_title    → npl_text
      patent_date     → publication_date
      assignee_entity → assignee
      paper_id        → paper_id
      matched_by      → matched_by
      country_code    → "US"
    """
    if not results:
        return 0, 0

    conn = get_connection()
    patent_count = 0
    paper_hits = {}

    for row in results:
        pid = row["paper_id"]
        pub_date = row.get("publication_date") or ""
        if pub_date and len(pub_date) == 8:
            pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"

        conn.execute("""
            INSERT OR REPLACE INTO patent_citations
                (paper_id, patent_id, assignee, publication_date, country_code, npl_text, matched_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            pid,
            row["patent_id"],
            row.get("assignee") or "",
            pub_date,
            row.get("country_code") or "US",
            (row.get("npl_text") or "")[:500],
            row.get("matched_by") or "",
        ))
        patent_count += 1
        paper_hits[pid] = paper_hits.get(pid, 0) + 1

    # 标记有匹配的论文
    for pid, cnt in paper_hits.items():
        conn.execute("""
            INSERT OR REPLACE INTO patent_query_log (paper_id, match_count)
            VALUES (?, ?)
        """, (pid, cnt))
    conn.commit()
    conn.close()

    return patent_count, len(paper_hits)


def mark_all_queried(paper_ids):
    """标记无匹配的论文为已查询"""
    if not paper_ids:
        return
    conn = get_connection()
    for pid in paper_ids:
        conn.execute("""
            INSERT OR REPLACE INTO patent_query_log (paper_id, match_count)
            VALUES (?, 0)
        """, (pid,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  PatentsView API 搜索
# ──────────────────────────────────────────────

STOP_WORDS = frozenset(
    "the a an for of in on with to and or by from at is are was were be been "
    "being has have had do does did will would could should may might can shall "
    "not no as if then than that this these those it its".split()
)


def extract_search_term(title, n=3):
    """从标题中提取前 n 个有效词"""
    clean = re.sub(r"[^\w\s]", " ", title)
    words = clean.split()
    significant = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 1]
    return " ".join(significant[:n]) if significant else " ".join(words[:n])


_api_available = None  # 缓存 API 可用性检测结果


def check_api_available():
    """检测 PatentsView API 是否可用（DNS 解析 + HTTP 连通性）

    返回: (可用端点 URL, None) 或 (None, 错误原因)
    """
    global _api_available
    if _api_available is not None:
        return _api_available

    import socket
    import json as _json

    # 1. 尝试新端点 (search.patentsview.org)
    try:
        socket.getaddrinfo("search.patentsview.org", 443, socket.AF_INET, socket.SOCK_STREAM)
        # DNS 可解析，测试 HTTP 连通性
        test_params = {
            "q": _json.dumps({"_text_any": {"patent_title": "test"}}),
            "f": _json.dumps(["patent_id"]),
            "o": _json.dumps({"per_page": 1})
        }
        resp = requests.get(PATENTSVIEW_URL, params=test_params, timeout=15)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            _api_available = (PATENTSVIEW_URL, None)
            return _api_available
    except (socket.gaierror, Exception):
        pass

    # 2. 尝试旧端点 (api.patentsview.org)
    try:
        socket.getaddrinfo("api.patentsview.org", 443, socket.AF_INET, socket.SOCK_STREAM)
        test_payload = {"q": {"_text_any": {"patent_title": "test"}}, "f": ["patent_id"], "o": {"per_page": 1}}
        resp = requests.post(PATENTSVIEW_OLD_URL, json=test_payload, timeout=15)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            _api_available = (PATENTSVIEW_OLD_URL, None)
            return _api_available
    except (socket.gaierror, Exception):
        pass

    _api_available = (None, "PatentsView API 不可用（DNS 无法解析或服务已迁移）")
    return _api_available


def search_patents_by_paper(paper_id, title):
    """通过 PatentsView 免费 API 查询引用该论文的专利

    处理流程：
    1. 用 extract_search_term(title, n=3) 提取搜索关键词
    2. 发送请求到 PatentsView（带 30 秒超时）
    3. 解析响应中的 patents 列表
    4. 映射为 patent_citations 表需要的字段格式

    注意：
    - PatentsView 要求 ≤1 请求/秒，调用方需控制频率
    - 如果请求失败（非 200），返回空列表 []
    - 如果解析异常，也要兜住，不中断主流程
    """
    search_term = extract_search_term(title, n=3)
    if not search_term or len(search_term) < 3:
        return [], search_term

    api_url, error = check_api_available()
    if api_url is None:
        return [], search_term

    import json as _json

    try:
        if api_url == PATENTSVIEW_URL:
            # 新端点：GET 请求
            params = {
                "q": _json.dumps({"_text_any": {"patent_title": search_term}}),
                "f": _json.dumps(["patent_id", "patent_title", "patent_date", "assignees.assignee_entity"]),
                "o": _json.dumps({"per_page": 50})
            }
            resp = requests.get(api_url, params=params, timeout=30)
        else:
            # 旧端点：POST 请求
            payload = {
                "q": {"_text_any": {"patent_npl_text": search_term}},
                "f": ["patent_id", "patent_title", "patent_date", "assignee_entity"]
            }
            resp = requests.post(api_url, json=payload, timeout=30)

        if resp.status_code != 200:
            return [], search_term

        data = resp.json()
        patents = data.get("patents", [])

        results = []
        for p in patents:
            assignees = p.get("assignees", [])
            assignee_name = ""
            if assignees and isinstance(assignees, list):
                first = assignees[0]
                if isinstance(first, dict):
                    assignee_name = first.get("assignee_entity", "")
                else:
                    assignee_name = str(first)

            results.append({
                "paper_id": paper_id,
                "patent_id": p.get("patent_id", ""),
                "npl_text": p.get("patent_title", ""),
                "publication_date": p.get("patent_date", ""),
                "assignee": assignee_name,
                "country_code": "US",
                "matched_by": search_term,
            })

        return results, search_term

    except Exception:
        return [], search_term


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

def run(limit=0, test_mode=0):
    ensure_patent_table()

    # 检测 API 可用性
    api_url, error = check_api_available()
    if api_url is None:
        print(f"\n{'='*60}")
        print(f"  ⚠️  PatentsView API 不可用")
        print(f"  原因: {error}")
        print(f"")
        print(f"  PatentsView 已于 2026-03-20 迁移到 USPTO Open Data Portal")
        print(f"  新端点 search.patentsview.org 在当前网络环境下无法访问")
        print(f"")
        print(f"  解决方案:")
        print(f"  1. 配置代理/VPN 后重新运行")
        print(f"  2. 在海外服务器上运行此脚本")
        print(f"  3. 使用 EPO OPS API 作为替代（需注册 API Key）")
        print(f"{'='*60}")
        return

    n = test_mode or limit
    if n:
        papers = get_unqueried_papers(n)
    else:
        papers = get_unqueried_papers()

    total_papers = len(papers)
    print(f"\n{'='*60}")
    print(f"  专利引用映射 (PatentsView API)")
    print(f"  本次处理: {total_papers} 篇")
    print(f"  API: {api_url}")
    print(f"{'='*60}\n")

    if not papers:
        print("  无待处理论文")
        return

    total_patents = 0
    hit_papers = 0
    miss_pids = []

    for i, (paper_id, title) in enumerate(papers, 1):
        results, search_term = search_patents_by_paper(paper_id, title)

        if results:
            patent_count, hit_count = save_results(results)
            total_patents += patent_count
            hit_papers += hit_count
        else:
            miss_pids.append(paper_id)

        # 每处理 50 篇打印进度
        if i % 50 == 0 or i == total_papers:
            print(f"  [{i}/{total_papers}] {title[:40]}... → {len(results)} patents")

        # PatentsView 限速：≤1 请求/秒
        time.sleep(1.3)

    # 批量标记无匹配的论文
    mark_all_queried(miss_pids)

    # 统计
    conn = get_connection()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE id NOT IN "
        "(SELECT paper_id FROM patent_query_log)"
    ).fetchone()[0]
    db_total = conn.execute("SELECT COUNT(*) FROM patent_citations").fetchone()[0]
    conn.close()

    print(f"\n{'='*60}")
    print(f"  专利映射完成")
    print(f"  处理论文:   {total_papers}")
    print(f"  命中论文:   {hit_papers}")
    print(f"  本次专利:   {total_patents}")
    print(f"  总专利引用: {db_total}")
    print(f"  剩余待查:   {remaining}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="专利引用映射 — PatentsView API")
    parser.add_argument("--limit", type=int, default=0, help="处理论文数量（0=全部）")
    parser.add_argument("--test", type=int, default=0, help="测试模式：处理指定数量")
    args = parser.parse_args()

    if args.test:
        run(test_mode=args.test)
    else:
        run(limit=args.limit)
