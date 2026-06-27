"""Paper Analysis Engine - CLI Entry Point

MVP 功能：
1. 搜索论文 → 自动评级
2. 查看论文详情 + 评级
3. Top N 排名
"""

import json
import sys
from typing import Optional

from engine.database import db
from engine.rating import engine as rating_engine
from engine.api_client import SemanticScholarClient


def init():
    """初始化数据库"""
    print("[INIT] 初始化数据库...")
    db.init_db()
    print("[OK] 数据库就绪")


def search_and_analyze(query: str, limit: int = 10):
    """搜索论文并自动评级"""
    print(f"\n[SEARCH] {query}\n")

    ss = SemanticScholarClient()
    results = ss.search(query, limit=limit)
    papers = results.get("data", [])

    if not papers:
        print("[NO] 未找到相关论文")
        return

    ranked = []
    for ss_paper in papers:
        paper = SemanticScholarClient.paper_to_dict(ss_paper)
        paper["id"] = paper["source_id"]

        # 保存到数据库
        db.insert_paper(paper)

        # 评级
        rating = rating_engine.calculate(paper)
        db.save_rating({
            "paper_id": paper["id"],
            "academic_impact": rating.academic_impact,
            "commercial_potential": rating.commercial_potential,
            "innovation_index": rating.innovation_index,
            "reproducibility": rating.reproducibility,
            "combo_value": rating.combo_value,
            "overall_score": rating.overall_score,
            "grade": rating.grade,
            "dimension_details": rating.dimension_details,
            "decay_adjustment": rating.decay_adjustment,
        })

        ranked.append((rating, paper))

    # 按评分降序排列
    ranked.sort(key=lambda x: x[0].overall_score, reverse=True)

    # 输出
    print(f"{'排名':<4} {'评分':<6} {'等级':<4} {'引用':<6} {'年份':<4} 标题")
    print("-" * 80)
    for i, (rating, paper) in enumerate(ranked, 1):
        print(f"{i:<4} {rating.overall_score:<6.1f} {rating.grade:<4} "
              f"{paper['citations']:<6} {paper.get('year','?'):<4} "
              f"{paper['title'][:60]}")
    print(f"\n共 {len(ranked)} 篇论文\n")


def show_paper(paper_id: str):
    """查看论文详情 + 评级"""
    paper = db.get_paper(paper_id)
    if not paper:
        print(f"[NO] 论文 {paper_id} 未找到")
        return

    rating = db.get_paper_rating(paper_id)

    print(f"\n[PAPER] {paper['title']}")
    print(f"   作者: {', '.join(a['name'] for a in paper['authors'][:5])}")
    print(f"   年份: {paper.get('year','?')}  |  引用: {paper['citations']}  |  "
          f"期刊: {paper.get('journal','?')}")
    print(f"   领域: {paper.get('field','')}")

    if rating:
        print(f"\n   [Score] {rating['overall_score']:.1f}  [{rating['grade']}级]")
        print(f"   +-- 学术影响力:  {rating['academic_impact']:.1f}")
        print(f"   +-- 商业转化潜力: {rating['commercial_potential']:.1f}")
        print(f"   +-- 创新指数:    {rating['innovation_index']:.1f}")
        print(f"   +-- 可复现性:    {rating['reproducibility']:.1f}")
        print(f"   +-- 组合价值:    {rating['combo_value']:.1f}")
        if rating.get("decay_adjustment"):
            print(f"   [Decay] 时间衰减调整: {rating['decay_adjustment']:.1f}")
    else:
        print("\n   [WARN] 尚未评级")

    if paper.get("abstract"):
        print(f"\n   [Abstract] {paper['abstract'][:200]}...")

    print()


def top_papers(limit: int = 20):
    """Top N 排名"""
    papers = db.get_top_papers(limit)
    if not papers:
        print("[NO] 暂无评级数据，请先搜索论文")
        return

    print(f"\n[Top {len(papers)}]\n")
    for i, p in enumerate(papers, 1):
        print(f"{i}. [{p['grade']}] {p['overall_score']:.0f}分 | "
              f"引用{p.get('citations','?')} | {p.get('year','?')}年 | "
              f"{p['title'][:50]}")
    print()


def main():
    if len(sys.argv) < 2:
        print("Paper Analysis Engine — 学术论文智能评级系统")
        print("\n用法:")
        print("  python main.py init             初始化数据库")
        print("  python main.py search <关键词>   搜索论文并评级")
        print("  python main.py show <paper_id>   查看论文详情")
        print("  python main.py top [数量]        查看 Top N 排名")
        return

    cmd = sys.argv[1]

    if cmd == "init":
        init()
    elif cmd == "search":
        query = " ".join(sys.argv[2:]) or "machine learning"
        search_and_analyze(query)
    elif cmd == "show":
        paper_id = sys.argv[2] if len(sys.argv) > 2 else ""
        show_paper(paper_id)
    elif cmd == "top":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        top_papers(limit)
    else:
        print(f"[ERR] 未知命令: {cmd}")


if __name__ == "__main__":
    main()
