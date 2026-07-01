"""一次性脚本：用统一后的评级引擎重新评级全部论文

读取所有论文 → 用 engine.rating 算法计算 → 更新数据库 → 打印对比摘要
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 确保能 import backend 和 engine
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 设置数据库路径环境变量
os.environ.setdefault("DATABASE_PATH", str(Path(__file__).resolve().parent / "papers.db"))

from backend.db import get_connection, init_db, insert_rating, get_stats
from backend.rating_engine import rate_paper


def get_old_stats():
    """获取旧评分统计"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(overall_score), MAX(overall_score), MIN(overall_score) FROM ratings")
        row = cursor.fetchone()
        old_avg = round(row[0], 1) if row[0] else 0
        old_max = round(row[1], 1) if row[1] else 0
        old_min = round(row[2], 1) if row[2] else 0

        cursor.execute("SELECT grade, COUNT(*) FROM ratings GROUP BY grade ORDER BY grade")
        old_dist = {row[0]: row[1] for row in cursor.fetchall()}
        return old_avg, old_max, old_min, old_dist
    finally:
        conn.close()


def get_all_papers():
    """获取所有论文"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, abstract, journal, year, citations, authors, fields, doi, url, pdf_url, source FROM papers")
        papers = []
        for row in cursor.fetchall():
            p = dict(row)
            # 解析 JSON 字段
            for key in ("authors", "fields"):
                v = p.get(key)
                if isinstance(v, str):
                    try:
                        p[key] = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        p[key] = []
                elif v is None:
                    p[key] = []
            papers.append(p)
        return papers
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("  重评级脚本 - 使用 engine/rating.py 统一算法")
    print("=" * 60)

    # 初始化数据库（触发迁移确保表结构正确）
    init_db()

    # 获取旧统计
    old_avg, old_max, old_min, old_dist = get_old_stats()
    print(f"\n📊 旧评分统计:")
    print(f"  平均分: {old_avg} | 最高分: {old_max} | 最低分: {old_min}")
    print(f"  等级分布: {old_dist}")

    # 获取所有论文
    papers = get_all_papers()
    total = len(papers)
    print(f"\n📝 共 {total} 篇论文需要重评级")

    # 逐篇重评级
    success = 0
    errors = 0
    error_list = []
    new_scores = []

    for i, paper in enumerate(papers, 1):
        try:
            rating = rate_paper(paper)
            insert_rating(paper["id"], rating)
            new_scores.append(rating["overall_score"])
            success += 1

            if i % 100 == 0:
                print(f"  进度: {i}/{total} ({i*100//total}%)")
        except Exception as e:
            errors += 1
            error_list.append((paper.get("id", "?"), str(e)))
            print(f"  [ERROR] {paper.get('id', '?')}: {e}")

    # 计算新统计
    if new_scores:
        new_avg = round(sum(new_scores) / len(new_scores), 1)
        new_max = round(max(new_scores), 1)
        new_min = round(min(new_scores), 1)
    else:
        new_avg = new_max = new_min = 0

    # 从数据库获取最终等级分布
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT grade, COUNT(*) FROM ratings GROUP BY grade ORDER BY grade")
        new_dist = {row[0]: row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    # 打印对比
    print(f"\n{'=' * 60}")
    print(f"  📊 重评级完成！")
    print(f"{'=' * 60}")
    print(f"\n  处理结果: 成功 {success} | 失败 {errors} | 总计 {total}")
    print(f"\n  📈 新旧对比:")
    print(f"  {'指标':<12} {'旧值':>8} → {'新值':>8} {'变化':>8}")
    print(f"  {'-'*40}")
    print(f"  {'平均分':<12} {old_avg:>8} → {new_avg:>8} {new_avg - old_avg:>+8.1f}")
    print(f"  {'最高分':<12} {old_max:>8} → {new_max:>8} {new_max - old_max:>+8.1f}")
    print(f"  {'最低分':<12} {old_min:>8} → {new_min:>8} {new_min - old_min:>+8.1f}")
    print(f"\n  📊 等级分布:")
    print(f"  {'等级':<6} {'旧':>6} → {'新':>6} {'变化':>6}")
    print(f"  {'-'*28}")
    all_grades = sorted(set(list(old_dist.keys()) + list(new_dist.keys())))
    for g in all_grades:
        old_v = old_dist.get(g, 0)
        new_v = new_dist.get(g, 0)
        print(f"  {g:<6} {old_v:>6} → {new_v:>6} {new_v - old_v:>+6}")

    if error_list:
        print(f"\n  ⚠️ 异常论文 ({len(error_list)} 篇):")
        for pid, err in error_list[:10]:
            print(f"    {pid}: {err}")

    print(f"\n✅ 重评级完成！")


if __name__ == "__main__":
    main()
