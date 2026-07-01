#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量 AI 分析论文 - 为每篇论文生成深度分析并缓存到数据库"""

import sys
import os
import sqlite3
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_connection, init_db
from llm_analyzer import (
    summarize_paper, translate_abstract, plain_language_summary,
    assess_value, functional_description, deep_analysis,
    CURRENT_PROVIDER
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papers.db")


def ensure_ai_table():
    """确保 ai_analyses 表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            content TEXT,
            provider TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(paper_id, analysis_type)
        )
    """)
    conn.commit()
    conn.close()


def get_papers_without_analysis(limit=200):
    """获取没有 AI 分析的论文"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM papers
        WHERE id NOT IN (SELECT DISTINCT paper_id FROM ai_analyses)
        ORDER BY id
        LIMIT ?
    """, (limit,))
    papers = cursor.fetchall()
    conn.close()
    return papers


def get_total_papers():
    """获取论文总数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def get_analyzed_count():
    """获取已分析论文数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT paper_id) FROM ai_analyses")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def save_analysis(paper_id, analysis_type, content):
    """保存分析结果到数据库"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO ai_analyses (paper_id, analysis_type, content, provider)
        VALUES (?, ?, ?, ?)
    """, (paper_id, analysis_type, content, CURRENT_PROVIDER))
    conn.commit()
    conn.close()


def get_paper(paper_id):
    """获取论文完整数据"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    columns = [desc[0] for desc in cursor.description]
    conn.close()
    return dict(zip(columns, row))


def batch_analyze(limit=200):
    """批量分析论文"""
    init_db()
    ensure_ai_table()

    total = get_total_papers()
    analyzed = get_analyzed_count()
    pending = total - analyzed

    print(f"\n{'='*60}")
    print(f"  批量 AI 分析 (LLM: {CURRENT_PROVIDER})")
    print(f"{'='*60}")
    print(f"  论文总数: {total}")
    print(f"  已分析:   {analyzed}")
    print(f"  待分析:   {pending}")
    print(f"  本次处理: {min(limit, pending)}")
    print(f"{'='*60}\n")

    if pending == 0:
        print("  [OK] 所有论文已完成 AI 分析")
        return

    papers = get_papers_without_analysis(limit)
    if not papers:
        print("  [OK] 没有待分析的论文")
        return

    success = 0
    failed = 0

    for i, (paper_id,) in enumerate(papers, 1):
        paper = get_paper(paper_id)
        if not paper:
            print(f"  [{i}/{len(papers)}] [SKIP] 未找到: {paper_id}")
            failed += 1
            continue

        title = paper.get("title", "N/A")
        print(f"  [{i}/{len(papers)}] 分析: {title[:50]}...", end="", flush=True)

        try:
            # 1. 生成深度分析（综合报告）
            deep = deep_analysis(paper)
            save_analysis(paper_id, "deep_analysis", deep)

            # 2. 生成摘要
            summary = summarize_paper(paper)
            save_analysis(paper_id, "summary", summary)

            # 3. 生成翻译
            translation = translate_abstract(paper)
            save_analysis(paper_id, "translation", translation)

            print(f" [OK]")
            success += 1

            # 速率控制
            time.sleep(0.5)

        except Exception as e:
            print(f" [FAIL] {e}")
            failed += 1
            continue

    print(f"\n{'='*60}")
    print(f"  批量分析完成")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    print(f"  剩余待分析: {max(0, pending - success)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="批量 AI 分析论文")
    parser.add_argument("--limit", type=int, default=200, help="每次处理数量 (默认 200)")
    args = parser.parse_args()

    batch_analyze(args.limit)
