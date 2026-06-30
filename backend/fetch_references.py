"""补充抓取论文引用关系 - 通过 OpenAlex API 获取 referenced_works

用法:
    python fetch_references.py              # 抓取所有OpenAlex论文的引用关系
    python fetch_references.py --limit 50   # 只抓取50篇
    python fetch_references.py --dry-run    # 只测试不写入
"""

import sys
import os
import json
import time
import sqlite3
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Windows 编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from db import get_connection, DB_PATH

OPENALEX_BASE = "https://api.openalex.org"
HEADERS = {"User-Agent": "PaperAnalysisEngine/1.0 (mailto:user@example.com)"}


def fetch_referenced_works(openalex_id: str, max_retries: int = 3) -> list:
    """通过 OpenAlex ID 获取论文的引用列表"""
    # 确保 ID 格式正确
    if not openalex_id:
        return []
    # OpenAlex ID 格式: W123456789
    work_id = openalex_id.strip()
    if not work_id.startswith("W"):
        return []

    url = f"{OPENALEX_BASE}/works/{work_id}"
    params = {"select": "id,referenced_works"}

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS,
                                timeout=20, verify=True)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 2, 30)
                print(f"      [限流] 等待 {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            ref_works = data.get("referenced_works", []) or []
            # 转换为短 ID (去掉 https://openalex.org/ 前缀)
            return [w.split("/")[-1] for w in ref_works if w]
        except requests.exceptions.SSLError:
            try:
                resp = requests.get(url, params=params, headers=HEADERS,
                                    timeout=20, verify=False)
                resp.raise_for_status()
                data = resp.json()
                ref_works = data.get("referenced_works", []) or []
                return [w.split("/")[-1] for w in ref_works if w]
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    print(f"      [SSL失败] {e}")
                    return []
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"      [请求失败] {e}")
                return []
    return []


def get_papers_needing_refs(limit: int = None) -> list:
    """获取需要补充引用关系的论文（OpenAlex来源且ref_ids为空）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, source, doi
        FROM papers
        WHERE (ref_ids IS NULL OR ref_ids = '[]' OR ref_ids = '')
          AND source = 'openalex'
        ORDER BY citations DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    if limit:
        rows = rows[:limit]
    return rows


def update_paper_refs(paper_id: str, references: list):
    """更新论文的引用关系"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE papers SET ref_ids = ? WHERE id = ?",
        (json.dumps(references, ensure_ascii=False), paper_id)
    )
    conn.commit()
    conn.close()


def main(limit: int = None, dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"  引用关系补充抓取")
    print(f"{'='*60}")

    papers = get_papers_needing_refs(limit)
    print(f"\n  待抓取论文数: {len(papers)}")
    if dry_run:
        print("  [DRY-RUN] 只测试不写入")
    print()

    success = 0
    failed = 0
    total_refs = 0

    for i, p in enumerate(papers, 1):
        pid = p["id"]
        title = (p.get("title") or "")[:50]
        print(f"  [{i}/{len(papers)}] {title}")
        print(f"       ID: {pid}")

        refs = fetch_referenced_works(pid)
        print(f"       引用数: {len(refs)}")

        if refs:
            total_refs += len(refs)
            if not dry_run:
                update_paper_refs(pid, refs)
            success += 1
        else:
            failed += 1

        # 避免 API 限流
        time.sleep(0.3)

        # 每20篇打印一次进度
        if i % 20 == 0:
            print(f"\n  --- 进度: {i}/{len(papers)} | 成功: {success} | 失败: {failed} | 总引用: {total_refs} ---\n")

    print(f"\n{'='*60}")
    print(f"  抓取完成!")
    print(f"  成功: {success} 篇")
    print(f"  失败: {failed} 篇")
    print(f"  总引用关系: {total_refs} 条")
    if not dry_run:
        print(f"  数据已更新到: {DB_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="补充抓取论文引用关系")
    parser.add_argument("--limit", type=int, default=None, help="限制抓取数量")
    parser.add_argument("--dry-run", action="store_true", help="只测试不写入")
    args = parser.parse_args()
    main(args.limit, args.dry_run)
