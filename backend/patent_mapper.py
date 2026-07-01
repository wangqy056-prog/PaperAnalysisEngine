#!/usr/bin/env python
"""Patent Citation Mapper — 查询 BigQuery 专利数据库，建立论文-专利引用映射

用法：
  python patent_mapper.py --test 5       # 测试模式：处理 5 篇
  python patent_mapper.py --limit 100    # 批量模式：处理 100 篇
"""

import os
import re
import time
import argparse
from pathlib import Path

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# 设置 BigQuery 凭证路径（.env 中是相对路径，需要转为绝对路径）
_credentials_rel = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
if _credentials_rel and not os.path.isabs(_credentials_rel):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
        Path(__file__).parent.parent / _credentials_rel
    )

from db import get_connection
from google.cloud import bigquery

PATENTS_TABLE = "patents-public-data.patents.publications"


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


def get_papers_for_mapping(limit=100):
    """获取尚未查询专利的论文（排除已查询过的）"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.title, p.doi FROM papers p
        WHERE p.id NOT IN (SELECT paper_id FROM patent_query_log)
        ORDER BY p.id
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def mark_paper_queried(paper_id, match_count):
    """标记论文已查询，记录匹配数"""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO patent_query_log (paper_id, match_count)
        VALUES (?, ?)
    """, (paper_id, match_count))
    conn.commit()
    conn.close()


def save_patent_citations(paper_id, patents, search_term):
    """保存专利引用到数据库，返回插入条数"""
    conn = get_connection()
    count = 0
    for row in patents:
        pub_date = str(row["publication_date"]) if row["publication_date"] else None
        # YYYYMMDD → YYYY-MM-DD
        if pub_date and len(pub_date) == 8:
            pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"

        conn.execute("""
            INSERT OR REPLACE INTO patent_citations
                (paper_id, patent_id, assignee, publication_date, country_code, npl_text, matched_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            row["publication_number"],
            row["assignee"],
            pub_date,
            row["country_code"],
            (row["npl_text"] or "")[:500],
            search_term,
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


# ──────────────────────────────────────────────
#  BigQuery
# ──────────────────────────────────────────────

STOP_WORDS = frozenset(
    "the a an for of in on with to and or by from at is are was were be been "
    "being has have had do does did will would could should may might can shall "
    "not no as if then than that this these those it its".split()
)


def extract_search_term(title):
    """从标题中提取前 5 个有效词作为搜索关键词"""
    clean = re.sub(r"[^\w\s]", " ", title)
    words = clean.split()
    significant = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 1]
    return " ".join(significant[:5]) if significant else " ".join(words[:5])


def search_patents(client, search_term, limit=20):
    """在 BigQuery 专利库中搜索 NPL 引用包含该关键词的专利"""
    query = f"""
        SELECT
          p.publication_number,
          c.npl_text,
          p.publication_date,
          p.country_code,
          (SELECT STRING_AGG(DISTINCT a, ', ')
           FROM UNNEST(p.assignee) a) AS assignee
        FROM `{PATENTS_TABLE}` p,
        UNNEST(citation) AS c
        WHERE c.npl_text IS NOT NULL
          AND LOWER(c.npl_text) LIKE @pattern
        LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("pattern", "STRING", f"%{search_term.lower()}%"),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )
    return list(client.query(query, job_config=job_config).result())


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

def run(limit=100, test_mode=0):
    ensure_patent_table()
    client = bigquery.Client()

    n = test_mode or limit
    papers = get_papers_for_mapping(n)

    total_papers = len(papers)
    total_matched = 0
    papers_with_hits = 0

    print(f"\n{'='*60}")
    print(f"  专利引用映射 (BigQuery → patent_citations)")
    print(f"  本次处理: {total_papers} 篇")
    print(f"{'='*60}\n")

    for i, paper in enumerate(papers, 1):
        pid = paper["id"]
        title = paper["title"]
        term = extract_search_term(title)

        short_title = title[:55] + ("…" if len(title) > 55 else "")
        print(f"  [{i}/{total_papers}] {short_title}")
        print(f"           搜索词: {term[:60]}  →  ", end="", flush=True)

        try:
            results = search_patents(client, term)
            if results:
                cnt = save_patent_citations(pid, results, term)
                total_matched += cnt
                papers_with_hits += 1
                mark_paper_queried(pid, cnt)
                print(f"✅ {cnt} 条专利引用")
            else:
                mark_paper_queried(pid, 0)
                print("— 无匹配")
        except Exception as e:
            print(f"✗ 错误: {e}")

        # 避免 BigQuery 限流
        time.sleep(0.5)

    # 统计
    conn = get_connection()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE id NOT IN "
        "(SELECT paper_id FROM patent_query_log)"
    ).fetchone()[0]
    total_patents = conn.execute("SELECT COUNT(*) FROM patent_citations").fetchone()[0]
    conn.close()

    print(f"\n{'='*60}")
    print(f"  专利映射完成")
    print(f"  处理论文:   {total_papers}")
    print(f"  命中论文:   {papers_with_hits}")
    print(f"  专利引用:   {total_matched}")
    print(f"  总专利引用: {total_patents}")
    print(f"  剩余待查:   {remaining}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="专利引用映射 — BigQuery")
    parser.add_argument("--limit", type=int, default=100, help="每批处理论文数量（默认 100）")
    parser.add_argument("--test", type=int, default=0, help="测试模式：处理指定数量论文")
    args = parser.parse_args()

    if args.test:
        run(test_mode=args.test)
    else:
        run(limit=args.limit)
