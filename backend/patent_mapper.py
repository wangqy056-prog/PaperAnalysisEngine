#!/usr/bin/env python
"""Patent Citation Mapper — 批量查询 BigQuery 专利数据库，建立论文-专利引用映射

核心优化：单次 JOIN 查询全部论文，扫描量 ~27GB（而非逐篇 61.7TB）

用法：
  python patent_mapper.py --test 5       # 测试模式：处理 5 篇
  python patent_mapper.py --limit 1151   # 批量模式：处理全部
"""

import os
import re
import argparse
from pathlib import Path

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# 设置 BigQuery 凭证路径
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
    """保存批量查询结果到 patent_citations，同时标记 queried"""
    conn = get_connection()
    patent_count = 0
    paper_hits = {}  # paper_id -> count

    for row in results:
        pid = row["paper_id"]
        pub_date = str(row["publication_date"]) if row["publication_date"] else None
        if pub_date and len(pub_date) == 8:
            pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"

        conn.execute("""
            INSERT OR REPLACE INTO patent_citations
                (paper_id, patent_id, assignee, publication_date, country_code, npl_text, matched_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            pid,
            row["publication_number"],
            row["assignee"],
            pub_date,
            row["country_code"],
            (row["npl_text"] or "")[:500],
            row["matched_by"],
        ))
        patent_count += 1
        paper_hits[pid] = paper_hits.get(pid, 0) + 1

    # 标记所有论文为已查询（包括无匹配的）
    conn.close()

    # 分开事务：先保存 citations，再标记 queried
    conn = get_connection()
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
#  BigQuery 批量搜索
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


def batch_search(client, papers):
    """批量搜索：上传搜索词到 BigQuery 临时表，单次 JOIN 查全部

    扫描量 ≈ 27GB（ patents 表 npl_text 列），而非 27GB × 1151 = 31TB
    """
    project = client.project
    dataset_id = f"{project}.pae_temp"
    table_id = f"{dataset_id}.search_terms"

    # 1. 创建临时 dataset
    client.create_dataset(dataset_id, exists_ok=True)

    # 2. 上传搜索词到临时表
    rows = [
        {"paper_id": p["id"], "term": extract_search_term(p["title"], n=3)}
        for p in papers
    ]
    # 过滤掉 term 太短（<3 字符）的，避免误匹配
    rows = [r for r in rows if len(r["term"]) >= 3]

    print(f"  上传 {len(rows)} 条搜索词到 BigQuery 临时表...")

    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("paper_id", "STRING"),
            bigquery.SchemaField("term", "STRING"),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    load_job = client.load_table_from_json(rows, table_id, job_config=job_config)
    load_job.result()  # 等待完成
    print(f"  临时表已创建: {table_id}")

    # 3. 单次 JOIN 查询
    query = f"""
        SELECT
          t.paper_id,
          p.publication_number,
          c.npl_text,
          p.publication_date,
          p.country_code,
          (SELECT STRING_AGG(DISTINCT a, ', ')
           FROM UNNEST(p.assignee) a) AS assignee,
          t.term AS matched_by
        FROM `{PATENTS_TABLE}` p,
        UNNEST(citation) AS c,
        `{table_id}` t
        WHERE c.npl_text IS NOT NULL
          AND LOWER(c.npl_text) LIKE CONCAT('%', LOWER(t.term), '%')
        LIMIT 5000
    """
    print(f"  执行批量 JOIN 查询（预计扫描 ~27GB）...")
    job = client.query(query)
    results = list(job.result())
    bytes_processed = job.total_bytes_processed or 0

    # 4. 清理临时表
    client.delete_table(table_id, not_found_ok=True)
    print(f"  临时表已清理")

    return results, bytes_processed


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

def run(limit=0, test_mode=0):
    ensure_patent_table()
    client = bigquery.Client()

    n = test_mode or limit
    if n:
        papers = get_unqueried_papers(n)
    else:
        papers = get_unqueried_papers()

    total_papers = len(papers)
    print(f"\n{'='*60}")
    print(f"  专利引用映射 (BigQuery 批量 JOIN)")
    print(f"  本次处理: {total_papers} 篇")
    print(f"{'='*60}\n")

    if not papers:
        print("  无待处理论文")
        return

    # 批量查询
    results, bytes_processed = batch_search(client, papers)

    # 保存结果
    patent_count, hit_count = save_results(results)

    # 标记无匹配的论文
    hit_pids = {r["paper_id"] for r in results}
    miss_pids = [p["id"] for p in papers if p["id"] not in hit_pids]
    mark_all_queried(miss_pids)

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
    print(f"  命中论文:   {hit_count}")
    print(f"  专利引用:   {patent_count}")
    print(f"  总专利引用: {total_patents}")
    print(f"  剩余待查:   {remaining}")
    print(f"  扫描总量:   {bytes_processed/1e9:.2f} GB")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="专利引用映射 — BigQuery 批量")
    parser.add_argument("--limit", type=int, default=0, help="处理论文数量（0=全部）")
    parser.add_argument("--test", type=int, default=0, help="测试模式：处理指定数量")
    args = parser.parse_args()

    if args.test:
        run(test_mode=args.test)
    else:
        run(limit=args.limit)
