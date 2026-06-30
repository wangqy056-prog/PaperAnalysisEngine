"""命令行工具 - 论文搜索、查看、分析、导出、组合分析、趋势统计"""

import sys
import io
import os
import json
import csv
import argparse
from datetime import datetime
from collections import Counter, defaultdict

# Windows 编码兼容
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from db import init_db, search_papers, get_paper, get_all_ratings, get_stats, insert_rating, get_connection
from rating_engine import rate_paper, generate_tags, predict_commercialization, estimate_trl

# LLM 分析（延迟导入，避免未安装时报错）
try:
    from llm_analyzer import (
        summarize_paper, translate_abstract, plain_language_summary,
        assess_value, functional_description, deep_analysis,
        compare_papers_ai, switch_provider, call_llm,
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


# ==================== 显示工具 ====================

LEVEL_COLORS = {
    "S": "\033[93m",  # 金色
    "A": "\033[92m",  # 绿色
    "B": "\033[94m",  # 蓝色
    "C": "\033[33m",  # 橙色
    "D": "\033[31m",  # 红色
}
RESET = "\033[0m"


def color_level(level: str) -> str:
    color = LEVEL_COLORS.get(level, "")
    return f"{color}[{level}]{RESET}"


def bar(value, max_val=100, width=20):
    """生成文本进度条"""
    filled = int(value / max_val * width) if max_val > 0 else 0
    return "#" * filled + "." * (width - filled)


def print_paper_list(papers: list, show_rating: bool = True):
    if not papers:
        print("\n  [!] 未找到论文")
        return

    print(f"\n  共找到 {len(papers)} 篇论文:\n")

    for i, p in enumerate(papers, 1):
        title = (p.get("title") or "无标题")[:65]
        year = p.get("year") or "N/A"
        citations = p.get("citations") or 0
        journal = (p.get("journal") or "N/A")[:20]

        rating_str = ""
        if show_rating and "rating_level" in p:
            level = p.get("rating_level", "?")
            score = p.get("overall_score", 0)
            rating_str = f" {color_level(level)} {score}"

        print(f"  {i:3d}. [{year}] {title}")
        print(f"       引用:{citations:>5} | 期刊:{journal}{rating_str}")

        authors = p.get("authors")
        if authors:
            if isinstance(authors, str):
                authors = json.loads(authors)
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += f" 等{len(authors)}人"
            print(f"       作者: {author_str}")

        print()


def print_paper_detail(paper: dict):
    if not paper:
        print("\n  [!] 未找到该论文")
        return

    print(f"\n{'='*60}")
    print(f"  {paper.get('title', '无标题')}")
    print(f"{'='*60}")

    authors = paper.get("authors")
    if isinstance(authors, str):
        authors = json.loads(authors)
    if authors:
        print(f"\n  作者: {', '.join(authors)}")

    print(f"  期刊: {paper.get('journal', 'N/A')}")
    print(f"  年份: {paper.get('year', 'N/A')}")
    print(f"  引用: {paper.get('citations', 0)}")

    if paper.get("doi"):
        print(f"  DOI:  {paper['doi']}")
    if paper.get("url"):
        print(f"  链接: {paper['url']}")
    if paper.get("pdf_url"):
        print(f"  PDF:  {paper['pdf_url']}")

    fields = paper.get("fields")
    if isinstance(fields, str):
        fields = json.loads(fields)
    if fields:
        print(f"  领域: {', '.join(fields[:5])}")

    abstract = paper.get("abstract")
    if abstract:
        print(f"\n  摘要:")
        words = abstract.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 82:
                print(line)
                line = f"  {word}"
            else:
                line += f" {word}"
        if line.strip():
            print(line)

    rating = paper.get("rating")
    if rating:
        print(f"\n  {'-'*56}")
        print(f"  评级结果:")
        print(f"  {'-'*56}")
        level = rating.get("rating_level", "?")
        score = rating.get("overall_score", 0)
        print(f"  综合评分: {score} {color_level(level)}")
        print(f"  {'-'*56}")

        dimensions = [
            ("学术影响力", rating.get("academic_impact", 0)),
            ("商业潜力  ", rating.get("commercial_potential", 0)),
            ("创新指数  ", rating.get("innovation_index", 0)),
            ("可复现性  ", rating.get("reproducibility", 0)),
            ("组合价值  ", rating.get("combo_value", 0)),
        ]
        for name, val in dimensions:
            print(f"  {name}: {bar(val)} {val}")

    print(f"{'='*60}")


def print_ratings_summary(ratings: list):
    if not ratings:
        print("\n  [!] 暂无评级数据，请先导入论文")
        return

    print(f"\n  评级排行榜 (Top {len(ratings)}):\n")
    print(f"  {'#':>3}  {'等级':>4}  {'评分':>5}  {'年份':>4}  {'引用':>5}  标题")
    print(f"  {'-'*70}")

    for i, r in enumerate(ratings, 1):
        level = r.get("rating_level", "?")
        score = r.get("overall_score", 0)
        year = r.get("year", "N/A")
        citations = r.get("citations", 0)
        title = (r.get("title") or "无标题")[:40]

        print(f"  {i:3d}  {color_level(level)}  {score:>5.1f}  {year}  {citations:>5}  {title}")


def print_stats(stats: dict):
    print(f"\n{'='*60}")
    print(f"  数据库统计")
    print(f"{'='*60}")
    print(f"  论文总数:   {stats.get('total_papers', 0)}")
    print(f"  评级总数:   {stats.get('total_ratings', 0)}")
    print(f"  标签总数:   {stats.get('total_tags', 0)}")
    print(f"  平均评分:   {stats.get('avg_score', 0)}")
    print(f"  最高评分:   {stats.get('max_score', 0)}")
    print(f"  最低评分:   {stats.get('min_score', 0)}")

    dist = stats.get("level_distribution", {})
    if dist:
        print(f"\n  评级分布:")
        for level in ["S", "A", "B", "C", "D"]:
            count = dist.get(level, 0)
            if count:
                b = "#" * min(count, 20)
                print(f"    {level}: {b} {count}")

    print(f"{'='*60}")


# ==================== 新增：导出功能 ====================

def cmd_export(args):
    """导出论文数据为 CSV/JSON"""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 获取数据
    if args.query:
        papers = search_papers(args.query, limit=9999)
    else:
        cursor.execute("SELECT * FROM papers ORDER BY citations DESC")
        papers = [dict(r) for r in cursor.fetchall()]

    if not papers:
        print("\n  [!] 没有可导出的论文")
        conn.close()
        return

    # 获取评级数据
    cursor.execute("""
        SELECT r.*, p.title FROM ratings r
        JOIN papers p ON r.paper_id = p.id
    """)
    ratings_map = {r["paper_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    # 合并论文和评级
    for p in papers:
        r = ratings_map.get(p["id"], {})
        p["rating_level"] = r.get("rating_level", "")
        p["overall_score"] = r.get("overall_score", 0)
        p["academic_impact"] = r.get("academic_impact", 0)
        p["commercial_potential"] = r.get("commercial_potential", 0)
        p["innovation_index"] = r.get("innovation_index", 0)

    filepath = args.output

    if args.format == "csv":
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "标题", "年份", "期刊", "引用量", "作者",
                            "等级", "综合评分", "学术影响力", "商业潜力", "创新指数",
                            "DOI", "URL", "来源"])
            for p in papers:
                authors = p.get("authors", "[]")
                if isinstance(authors, str):
                    try:
                        authors = ", ".join(json.loads(authors))
                    except:
                        pass
                writer.writerow([
                    p.get("id", ""),
                    p.get("title", ""),
                    p.get("year", ""),
                    p.get("journal", ""),
                    p.get("citations", 0),
                    authors,
                    p.get("rating_level", ""),
                    p.get("overall_score", 0),
                    p.get("academic_impact", 0),
                    p.get("commercial_potential", 0),
                    p.get("innovation_index", 0),
                    p.get("doi", ""),
                    p.get("url", ""),
                    p.get("source", ""),
                ])
        print(f"\n  [OK] 导出 {len(papers)} 篇论文到 {filepath} (CSV)")

    elif args.format == "json":
        export_data = []
        for p in papers:
            authors = p.get("authors", "[]")
            if isinstance(authors, str):
                try:
                    authors = json.loads(authors)
                except:
                    authors = []
            fields = p.get("fields", "[]")
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                except:
                    fields = []
            export_data.append({
                "id": p.get("id"),
                "title": p.get("title"),
                "abstract": p.get("abstract"),
                "authors": authors,
                "journal": p.get("journal"),
                "year": p.get("year"),
                "citations": p.get("citations", 0),
                "doi": p.get("doi"),
                "url": p.get("url"),
                "pdf_url": p.get("pdf_url"),
                "fields": fields,
                "source": p.get("source"),
                "rating": {
                    "level": p.get("rating_level"),
                    "overall_score": p.get("overall_score", 0),
                    "academic_impact": p.get("academic_impact", 0),
                    "commercial_potential": p.get("commercial_potential", 0),
                    "innovation_index": p.get("innovation_index", 0),
                },
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"\n  [OK] 导出 {len(papers)} 篇论文到 {filepath} (JSON)")

    elif args.format == "bibtex":
        with open(filepath, "w", encoding="utf-8") as f:
            for p in papers:
                # 生成 BibTeX key
                authors = p.get("authors", "[]")
                if isinstance(authors, str):
                    try:
                        authors = json.loads(authors)
                    except:
                        authors = []
                first_author = authors[0].split()[-1] if authors else "Unknown"
                year = p.get("year", "XXXX")
                key = f"{first_author}{year}"

                f.write(f"@article{{{key},\n")
                f.write(f"  title = {{{p.get('title', '')}}},\n")
                if authors:
                    f.write(f"  author = {{{' and '.join(authors)}}},\n")
                f.write(f"  journal = {{{p.get('journal', '')}}},\n")
                f.write(f"  year = {{{year}}},\n")
                if p.get("doi"):
                    f.write(f"  doi = {{{p['doi']}}},\n")
                if p.get("url"):
                    f.write(f"  url = {{{p['url']}}},\n")
                f.write(f"}}\n\n")
        print(f"\n  [OK] 导出 {len(papers)} 篇论文到 {filepath} (BibTeX)")


# ==================== 新增：组合分析 ====================

def cmd_combine(args):
    """组合分析 - 找出与指定论文有协同效应的论文"""
    init_db()
    paper = get_paper(args.paper_id)

    if not paper:
        print(f"\n  [!] 未找到论文: {args.paper_id}")
        return

    print(f"\n{'='*60}")
    print(f"  组合分析: {paper.get('title', '无标题')[:50]}")
    print(f"{'='*60}")

    # 获取论文特征
    abstract = (paper.get("abstract") or "").lower()
    title = (paper.get("title") or "").lower()
    paper_text = f"{title} {abstract}"

    # 该论文的方法/技术
    methods = ["machine learning", "deep learning", "statistical", "experimental",
               "simulation", "analytical", "empirical", "theoretical", "quantum",
               "neural network", "transformer", "reinforcement learning"]
    paper_methods = [m for m in methods if m in paper_text]

    # 该论文的应用领域
    domains = ["medical", "finance", "manufacturing", "energy", "transportation",
               "healthcare", "education", "security", "robotics", "materials",
               "chemistry", "physics", "biology"]
    paper_domains = [d for d in domains if d in paper_text]

    print(f"\n  论文方法: {', '.join(paper_methods) or '未检测到'}")
    print(f"  应用领域: {', '.join(paper_domains) or '未检测到'}")

    # 获取所有其他论文
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM papers WHERE id != ? ORDER BY citations DESC", (args.paper_id,))
    other_papers = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not other_papers:
        print("\n  [!] 数据库中没有其他论文可供组合分析")
        return

    # 计算协同度
    combos = []
    for other in other_papers[:200]:  # 限制分析数量
        other_abstract = (other.get("abstract") or "").lower()
        other_title = (other.get("title") or "").lower()
        other_text = f"{other_title} {other_abstract}"

        other_methods = [m for m in methods if m in other_text]
        other_domains = [d for d in domains if d in other_text]

        # 方法互补性 (不同方法 → 更高互补)
        unique_methods = set(other_methods) - set(paper_methods)
        method_complement = len(unique_methods) / max(1, len(methods))

        # 场景扩展 (不同领域 → 更高扩展)
        unique_domains = set(other_domains) - set(paper_domains)
        scenario_expansion = len(unique_domains) / max(1, len(domains))

        # 技术叠加 (有共同方法 → 可叠加)
        common_methods = set(other_methods) & set(paper_methods)
        tech_synergy = len(common_methods) / max(1, len(set(paper_methods) | set(other_methods)))

        # 引用协同 (高引用论文组合价值更高)
        citation_factor = min(1.0, (other.get("citations", 0) or 0) / 500)

        # 综合协同度
        synergy = (
            method_complement * 0.30 +
            scenario_expansion * 0.25 +
            tech_synergy * 0.25 +
            citation_factor * 0.20
        ) * 100

        if synergy > 0:
            combos.append({
                "paper": other,
                "synergy": round(synergy, 1),
                "unique_methods": list(unique_methods),
                "unique_domains": list(unique_domains),
                "common_methods": list(common_methods),
            })

    # 排序
    combos.sort(key=lambda x: x["synergy"], reverse=True)

    # 显示结果
    print(f"\n  找到 {len(combos)} 篇潜在协同论文（分析前200篇）:")
    print(f"  {'-'*56}\n")

    for i, combo in enumerate(combos[:args.limit], 1):
        p = combo["paper"]
        title = (p.get("title") or "无标题")[:45]
        year = p.get("year", "N/A")
        citations = p.get("citations", 0)

        print(f"  {i:3d}. 协同度: {combo['synergy']:>5.1f}  [{year}] {title}")
        print(f"       引用:{citations:>5}")

        if combo["unique_methods"]:
            print(f"       互补方法: {', '.join(combo['unique_methods'][:3])}")
        if combo["unique_domains"]:
            print(f"       扩展领域: {', '.join(combo['unique_domains'][:3])}")
        if combo["common_methods"]:
            print(f"       共同技术: {', '.join(combo['common_methods'][:3])}")

        # 建议
        if combo["synergy"] >= 60:
            suggestion = ">> 强烈推荐组合研究"
        elif combo["synergy"] >= 40:
            suggestion = ">> 值得关注，有协同潜力"
        else:
            suggestion = ">> 弱关联"
        print(f"       {suggestion}\n")

    # 总结
    if combos:
        top = combos[0]
        print(f"  {'='*56}")
        print(f"  最佳组合:")
        print(f"  {top['paper'].get('title', 'N/A')[:50]}")
        print(f"  协同度: {top['synergy']}")
        print(f"  理由: 方法互补 + 场景扩展 + 技术叠加")
        print(f"{'='*60}")


# ==================== 新增：趋势统计 ====================

def cmd_trends(args):
    """趋势统计 - 按年份/领域/期刊分析"""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    if args.dimension == "year":
        # 年份趋势
        cursor.execute("""
            SELECT p.year, COUNT(*) as count, AVG(r.overall_score) as avg_score,
                   AVG(p.citations) as avg_citations
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            WHERE p.year IS NOT NULL
            GROUP BY p.year
            ORDER BY p.year
        """)
        rows = cursor.fetchall()

        if not rows:
            print("\n  [!] 没有年份数据")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  年份趋势分析")
        print(f"{'='*60}")
        print(f"\n  {'年份':>6}  {'论文数':>6}  {'平均评分':>8}  {'平均引用':>8}  分布")
        print(f"  {'-'*56}")

        max_count = max(r["count"] for r in rows)

        for r in rows:
            year = r["year"]
            count = r["count"]
            avg_score = r["avg_score"] or 0
            avg_citations = r["avg_citations"] or 0
            b = "#" * int(count / max_count * 20) if max_count > 0 else ""

            print(f"  {year:>6}  {count:>6}  {avg_score:>8.1f}  {avg_citations:>8.0f}  {b}")

        # 趋势分析
        if len(rows) >= 2:
            recent = rows[-1]["count"]
            older = rows[-2]["count"]
            if recent > older:
                trend = "↑ 上升"
            elif recent < older:
                trend = "↓ 下降"
            else:
                trend = "→ 持平"
            print(f"\n  趋势: {trend}")

    elif args.dimension == "journal":
        # 期刊分布
        cursor.execute("""
            SELECT p.journal, COUNT(*) as count, AVG(r.overall_score) as avg_score,
                   SUM(p.citations) as total_citations
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            WHERE p.journal IS NOT NULL AND p.journal != ''
            GROUP BY p.journal
            ORDER BY count DESC
            LIMIT ?
        """, (args.limit,))
        rows = cursor.fetchall()

        if not rows:
            print("\n  [!] 没有期刊数据")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  期刊分布 (Top {len(rows)})")
        print(f"{'='*60}")
        print(f"\n  {'期刊':>30}  {'论文数':>6}  {'平均评分':>8}  {'总引用':>8}")
        print(f"  {'-'*56}")

        for r in rows:
            journal = (r["journal"] or "N/A")[:30]
            count = r["count"]
            avg_score = r["avg_score"] or 0
            total_citations = r["total_citations"] or 0

            print(f"  {journal:>30}  {count:>6}  {avg_score:>8.1f}  {total_citations:>8}")

    elif args.dimension == "field":
        # 领域分布（基于标签）
        cursor.execute("""
            SELECT t.name, t.category, COUNT(pt.paper_id) as count,
                   AVG(r.overall_score) as avg_score
            FROM tags t
            JOIN paper_tags pt ON t.id = pt.tag_id
            LEFT JOIN ratings r ON pt.paper_id = r.paper_id
            GROUP BY t.name, t.category
            ORDER BY count DESC
            LIMIT ?
        """, (args.limit,))
        rows = cursor.fetchall()

        if not rows:
            print("\n  [!] 没有标签数据，请先分析论文生成标签")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  领域/标签分布 (Top {len(rows)})")
        print(f"{'='*60}")
        print(f"\n  {'标签':>20}  {'类别':>12}  {'论文数':>6}  {'平均评分':>8}")
        print(f"  {'-'*56}")

        for r in rows:
            name = (r["name"] or "N/A")[:20]
            category = r["category"] or ""
            count = r["count"]
            avg_score = r["avg_score"] or 0

            print(f"  {name:>20}  {category:>12}  {count:>6}  {avg_score:>8.1f}")

    elif args.dimension == "rating":
        # 评级趋势
        cursor.execute("""
            SELECT r.rating_level, COUNT(*) as count,
                   AVG(r.overall_score) as avg_score,
                   AVG(r.academic_impact) as avg_academic,
                   AVG(r.commercial_potential) as avg_commercial,
                   AVG(r.innovation_index) as avg_innovation,
                   AVG(r.reproducibility) as avg_reproducibility
            FROM ratings r
            GROUP BY r.rating_level
            ORDER BY r.rating_level
        """)
        rows = cursor.fetchall()

        if not rows:
            print("\n  [!] 没有评级数据")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  评级维度分析")
        print(f"{'='*60}")
        print(f"\n  {'等级':>4}  {'数量':>4}  {'综合':>6}  {'学术':>6}  {'商业':>6}  {'创新':>6}  {'复现':>6}")
        print(f"  {'-'*56}")

        for r in rows:
            level = r["rating_level"]
            count = r["count"]
            avg = r["avg_score"] or 0
            academic = r["avg_academic"] or 0
            commercial = r["avg_commercial"] or 0
            innovation = r["avg_innovation"] or 0
            repro = r["avg_reproducibility"] or 0

            print(f"  {color_level(level)}  {count:>4}  {avg:>6.1f}  {academic:>6.1f}  {commercial:>6.1f}  {innovation:>6.1f}  {repro:>6.1f}")

        # 五维平均
        cursor.execute("""
            SELECT AVG(academic_impact) as a, AVG(commercial_potential) as c,
                   AVG(innovation_index) as i, AVG(reproducibility) as r,
                   AVG(combo_value) as v
            FROM ratings
        """)
        avg = cursor.fetchone()
        print(f"\n  全库平均:")
        print(f"  学术: {avg['a'] or 0:.1f}  商业: {avg['c'] or 0:.1f}  创新: {avg['i'] or 0:.1f}  复现: {avg['r'] or 0:.1f}  组合: {avg['v'] or 0:.1f}")

    conn.close()
    print(f"\n{'='*60}")


# ==================== 新增：标签统计 ====================

def cmd_tags(args):
    """标签统计"""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    if args.paper_id:
        # 查看某篇论文的标签
        cursor.execute("""
            SELECT t.name, t.category, pt.confidence
            FROM tags t
            JOIN paper_tags pt ON t.id = pt.tag_id
            WHERE pt.paper_id = ?
            ORDER BY pt.confidence DESC
        """, (args.paper_id,))
        rows = cursor.fetchall()

        if not rows:
            print(f"\n  [!] 论文 {args.paper_id} 没有标签，请先运行 analyze")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  论文标签: {args.paper_id}")
        print(f"{'='*60}\n")

        category_map = {
            "discipline": "学科",
            "technology": "技术",
            "innovation_type": "类型",
            "trl": "成熟度",
        }

        for r in rows:
            cat = category_map.get(r["category"], r["category"])
            print(f"  [{cat}] {r['name']} (置信度: {r['confidence']})")

    else:
        # 全部标签统计
        cursor.execute("""
            SELECT t.name, t.category, COUNT(pt.paper_id) as count
            FROM tags t
            LEFT JOIN paper_tags pt ON t.id = pt.tag_id
            GROUP BY t.name, t.category
            ORDER BY count DESC
            LIMIT ?
        """, (args.limit,))
        rows = cursor.fetchall()

        if not rows:
            print("\n  [!] 没有标签数据，请先运行 analyze 生成标签")
            conn.close()
            return

        print(f"\n{'='*60}")
        print(f"  标签统计 (Top {len(rows)})")
        print(f"{'='*60}\n")
        print(f"  {'标签':>20}  {'类别':>12}  {'论文数':>6}  分布")
        print(f"  {'-'*56}")

        max_count = max(r["count"] for r in rows) or 1

        for r in rows:
            name = (r["name"] or "N/A")[:20]
            category = r["category"] or ""
            count = r["count"]
            b = "#" * int(count / max_count * 20)

            print(f"  {name:>20}  {category:>12}  {count:>6}  {b}")

    conn.close()
    print(f"\n{'='*60}")


# ==================== 新增：论文对比 ====================

def cmd_compare(args):
    """对比两篇论文"""
    init_db()
    paper1 = get_paper(args.id1)
    paper2 = get_paper(args.id2)

    if not paper1:
        print(f"\n  [!] 未找到论文: {args.id1}")
        return
    if not paper2:
        print(f"\n  [!] 未找到论文: {args.id2}")
        return

    r1 = paper1.get("rating") or {}
    r2 = paper2.get("rating") or {}

    print(f"\n{'='*70}")
    print(f"  论文对比分析")
    print(f"{'='*70}")

    # 标题
    print(f"\n  论文A: {(paper1.get('title') or 'N/A')[:50]}")
    print(f"  论文B: {(paper2.get('title') or 'N/A')[:50]}")

    # 基本信息
    print(f"\n  {'指标':>15}  {'论文A':>20}  {'论文B':>20}  {'差异':>10}")
    print(f"  {'-'*70}")

    metrics = [
        ("年份", paper1.get("year"), paper2.get("year")),
        ("引用量", paper1.get("citations", 0), paper2.get("citations", 0)),
        ("期刊", (paper1.get("journal") or "N/A")[:20], (paper2.get("journal") or "N/A")[:20]),
    ]

    for name, v1, v2 in metrics:
        v1_str = str(v1)[:20]
        v2_str = str(v2)[:20]
        try:
            diff = float(v2) - float(v1)
            diff_str = f"{diff:+.1f}" if isinstance(diff, float) else ""
        except (ValueError, TypeError):
            diff_str = ""
        print(f"  {name:>15}  {v1_str:>20}  {v2_str:>20}  {diff_str:>10}")

    # 评级对比
    if r1 or r2:
        print(f"\n  {'维度':>15}  {'论文A':>10}  {'论文B':>10}  {'差异':>10}  对比")
        print(f"  {'-'*70}")

        dimensions = [
            ("学术影响力", r1.get("academic_impact", 0), r2.get("academic_impact", 0)),
            ("商业潜力", r1.get("commercial_potential", 0), r2.get("commercial_potential", 0)),
            ("创新指数", r1.get("innovation_index", 0), r2.get("innovation_index", 0)),
            ("可复现性", r1.get("reproducibility", 0), r2.get("reproducibility", 0)),
            ("组合价值", r1.get("combo_value", 0), r2.get("combo_value", 0)),
            ("综合评分", r1.get("overall_score", 0), r2.get("overall_score", 0)),
        ]

        for name, v1, v2 in dimensions:
            diff = v2 - v1
            if abs(diff) < 1:
                bar_str = "  ≈  接近"
            elif diff > 0:
                bar_str = "  <<< B 更优"
            else:
                bar_str = "  A 更优 >>>"
            print(f"  {name:>15}  {v1:>10.1f}  {v2:>10.1f}  {diff:>+10.1f}  {bar_str}")

        # 等级
        l1 = r1.get("rating_level", "?")
        l2 = r2.get("rating_level", "?")
        print(f"\n  等级:  A={color_level(l1)}  B={color_level(l2)}")

    # TRL 对比
    trl1 = estimate_trl(paper1)
    trl2 = estimate_trl(paper2)
    print(f"\n  TRL:   A=TRL {trl1}  B=TRL {trl2}")

    # 建议
    print(f"\n  {'='*70}")
    if r1 and r2:
        s1 = r1.get("overall_score", 0)
        s2 = r2.get("overall_score", 0)
        if abs(s1 - s2) < 5:
            print(f"  结论: 两篇论文综合评分接近，建议都关注")
        elif s1 > s2:
            print(f"  结论: 论文A综合评分更高 ({s1} vs {s2})，推荐优先阅读A")
        else:
            print(f"  结论: 论文B综合评分更高 ({s2} vs {s1})，推荐优先阅读B")

        # 互补性
        if trl1 != trl2:
            print(f"  互补: TRL差距={abs(trl1 - trl2)}，技术成熟度不同，有互补潜力")
        if r1.get("academic_impact", 0) > r2.get("academic_impact", 0) and \
           r2.get("commercial_potential", 0) > r1.get("commercial_potential", 0):
            print(f"  互补: A学术更强，B商业更强，组合研究可覆盖产学研全链")
    print(f"{'='*70}")


# ==================== 新增：删除论文 ====================

def cmd_delete(args):
    """删除论文"""
    init_db()
    paper = get_paper(args.paper_id)

    if not paper:
        print(f"\n  [!] 未找到论文: {args.paper_id}")
        return

    title = paper.get("title", "N/A")
    print(f"\n  即将删除:")
    print(f"  ID: {args.paper_id}")
    print(f"  标题: {title}")

    if not args.force:
        confirm = input("\n  确认删除? (y/N): ")
        if confirm.lower() != "y":
            print("  已取消")
            return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM paper_tags WHERE paper_id = ?", (args.paper_id,))
    cursor.execute("DELETE FROM ratings WHERE paper_id = ?", (args.paper_id,))
    cursor.execute("DELETE FROM papers WHERE id = ?", (args.paper_id,))
    conn.commit()
    conn.close()

    print(f"\n  [OK] 已删除论文: {title[:40]}")


# ==================== 新增：AI 智能分析 ====================

def cmd_ai(args):
    """AI 智能分析论文"""
    if not LLM_AVAILABLE:
        print("\n  [!] LLM 模块未安装，请确保 llm_analyzer.py 存在")
        return

    init_db()
    paper = get_paper(args.paper_id)
    if not paper:
        print(f"\n  [!] 未找到论文: {args.paper_id}")
        return

    title = paper.get("title", "N/A")
    print(f"\n{'='*60}")
    print(f"  AI 智能分析: {title[:50]}")
    print(f"{'='*60}")

    if args.action == "summary":
        print("\n  [AI 摘要]\n")
        print(summarize_paper(paper))

    elif args.action == "translate":
        print("\n  [摘要翻译]\n")
        print(translate_abstract(paper))

    elif args.action == "plain":
        print("\n  [通俗解读]\n")
        print(plain_language_summary(paper))

    elif args.action == "value":
        print("\n  [价值评估]\n")
        print(assess_value(paper))

    elif args.action == "function":
        print("\n  [功能说明]\n")
        print(functional_description(paper))

    elif args.action == "all":
        print("\n  正在执行深度分析（5项）...\n")
        results = deep_analysis(paper)

        sections = [
            ("AI 摘要", "summary"),
            ("摘要翻译", "translation"),
            ("通俗解读", "plain_summary"),
            ("价值评估", "value_assessment"),
            ("功能说明", "functional_desc"),
        ]

        for title_text, key in sections:
            print(f"\n  {'='*56}")
            print(f"  {title_text}")
            print(f"  {'='*56}")
            print(results.get(key, "生成失败"))

    print(f"\n{'='*60}")


def cmd_ai_compare(args):
    """AI 对比两篇论文"""
    if not LLM_AVAILABLE:
        print("\n  [!] LLM 模块未安装")
        return

    init_db()
    paper1 = get_paper(args.id1)
    paper2 = get_paper(args.id2)

    if not paper1:
        print(f"\n  [!] 未找到论文: {args.id1}")
        return
    if not paper2:
        print(f"\n  [!] 未找到论文: {args.id2}")
        return

    print(f"\n{'='*60}")
    print(f"  AI 对比分析")
    print(f"{'='*60}")
    print(f"  论文A: {paper1.get('title', 'N/A')[:40]}")
    print(f"  论文B: {paper2.get('title', 'N/A')[:40]}")
    print(f"{'='*60}\n")

    result = compare_papers_ai(paper1, paper2)
    print(result)
    print(f"\n{'='*60}")


def cmd_ai_switch(args):
    """切换 LLM 提供商"""
    if not LLM_AVAILABLE:
        print("\n  [!] LLM 模块未安装")
        return

    switch_provider(args.provider)


# ==================== 收藏夹命令 ====================

def cmd_fav(args):
    """收藏夹管理"""
    from favorites_manager import (
        ensure_default_collections, list_collections, create_collection,
        add_to_collection, remove_from_collection, list_papers_in_collection
    )
    ensure_default_collections()

    if args.fav_cmd == "list" or not args.fav_cmd:
        collections = list_collections()
        print(f"\n  收藏夹列表 ({len(collections)}个):\n")
        for c in collections:
            print(f"  [{c['id']}] {c['name']} - {c['paper_count']}篇")
            if c.get('description'):
                print(f"      {c['description']}")

    elif args.fav_cmd == "create":
        cid = create_collection(args.name, args.desc)
        if cid > 0:
            print(f"\n  [OK] 创建成功，ID={cid}: {args.name}")

    elif args.fav_cmd == "add":
        if add_to_collection(args.collection_id, args.paper_id, args.notes):
            print(f"\n  [OK] 已收藏到收藏夹 {args.collection_id}")
        else:
            print(f"\n  [!] 收藏失败或已存在")

    elif args.fav_cmd == "remove":
        if remove_from_collection(args.collection_id, args.paper_id):
            print(f"\n  [OK] 已移除")
        else:
            print(f"\n  [!] 移除失败")


# ==================== 推荐命令 ====================

def cmd_rec(args):
    """论文推荐"""
    from recommendation_engine import get_recommendations, get_user_profile

    profile = get_user_profile()
    print(f"\n  用户画像: 浏览{profile['viewed_papers']}篇, 收藏{profile['favorited_papers']}篇, 评分{profile['rated_papers']}篇")

    if profile['top_fields']:
        print(f"  偏好领域: {', '.join(f'{f}({c})' for f, c in profile['top_fields'][:5])}")

    recs = get_recommendations(args.strategy, top_n=args.top)
    if not recs:
        print("\n  [!] 暂无推荐，请先浏览/收藏一些论文")
        return

    print(f"\n  推荐 {len(recs)} 篇论文 (策略: {args.strategy}):\n")
    for i, r in enumerate(recs, 1):
        title = (r.get('title') or '')[:55]
        level = r.get('rating_level', '?')
        score = r.get('overall_score', 0)
        rec_score = r.get('recommend_score', 0)
        print(f"  {i:2d}. [{level}] {title}")
        print(f"      评分:{score:.1f} 推荐分:{rec_score:.2f}")
        if r.get('match_reason'):
            print(f"      理由: {r['match_reason'][:60]}")
        print()


# ==================== 报告命令 ====================

def cmd_report(args):
    """生成报告"""
    from report_generator import (
        export_stats_report, export_paper_report, export_collection_report,
        export_recommendation_report
    )

    if args.type == "stats":
        path = export_stats_report(args.format)
    elif args.type == "paper":
        if not args.id:
            print("  [!] 需要 --id 参数")
            return
        path = export_paper_report(args.id, args.format)
    elif args.type == "collection":
        if not args.id:
            print("  [!] 需要 --id 参数（收藏夹ID）")
            return
        path = export_collection_report(int(args.id), args.format)
    elif args.type == "recommendations":
        from recommendation_engine import get_recommendations
        recs = get_recommendations("hybrid", top_n=15)
        if not recs:
            print("  [!] 无推荐数据")
            return
        path = export_recommendation_report(recs, args.format)
    else:
        path = export_stats_report(args.format)

    print(f"\n  [OK] 报告已生成: {path}")


# ==================== 推送命令 ====================

def cmd_push(args):
    """定时推送"""
    from scheduled_push import (
        list_subscriptions, execute_push, start_scheduler
    )

    if args.push_cmd == "list" or not args.push_cmd:
        subs = list_subscriptions()
        if not subs:
            print("\n  [!] 没有推送订阅")
            return
        print(f"\n  推送订阅 ({len(subs)}个):\n")
        for s in subs:
            status = "启用" if s['enabled'] else "禁用"
            print(f"  [{s['id']}] {s['name']} ({s['push_type']}) {status}")
            print(f"      推送次数: {s['push_count']}")
            if s.get('last_push_at'):
                print(f"      最后推送: {s['last_push_at'][:19]}")

    elif args.push_cmd == "test":
        result = execute_push(args.subscription_id, strategy="daily", top_n=5)
        status = result.get('status', 'unknown')
        if status == 'success':
            print(f"\n  [OK] 推送成功！{result.get('paper_count', 0)}篇论文")
        elif status == 'empty':
            print("\n  [!] 没有符合条件的论文")
        else:
            print(f"\n  [!] 推送失败: {result.get('message', '未知错误')}")

    elif args.push_cmd == "serve":
        print("\n  启动定时推送服务...")
        start_scheduler(args.interval)


# ==================== 原有命令 ====================

def cmd_search(args):
    init_db()
    papers = search_papers(
        query=args.query, limit=args.limit,
        year_from=args.year_from, year_to=args.year_to,
        min_citations=args.min_citations,
    )
    print_paper_list(papers, show_rating=False)
    if papers:
        print(f"  提示: 使用 'python cli.py view <id>' 查看详情")
        print(f"  提示: 使用 'python cli.py analyze <id>' 深度分析")
        print(f"  提示: 使用 'python cli.py combine <id>' 查找协同论文")


def cmd_view(args):
    init_db()
    paper = get_paper(args.paper_id)
    print_paper_detail(paper)


def cmd_analyze(args):
    init_db()
    paper = get_paper(args.paper_id)
    if not paper:
        print(f"\n  [!] 未找到论文: {args.paper_id}")
        return

    ratings = rate_paper(paper)
    insert_rating(paper["id"], ratings)
    tags = generate_tags(paper)
    comm = predict_commercialization(paper)

    print(f"\n{'='*60}")
    print(f"  深度分析: {paper.get('title', '无标题')[:50]}")
    print(f"{'='*60}")

    print(f"\n  五维评级:")
    print(f"  {'-'*40}")
    dimensions = [
        ("学术影响力", ratings["academic_impact"]),
        ("商业潜力  ", ratings["commercial_potential"]),
        ("创新指数  ", ratings["innovation_index"]),
        ("可复现性  ", ratings["reproducibility"]),
        ("组合价值  ", ratings["combo_value"]),
    ]
    for name, val in dimensions:
        print(f"  {name}: {bar(val)} {val}")

    print(f"\n  综合评分: {ratings['overall_score']} {color_level(ratings['rating_level'])}")

    print(f"\n  商业化预测:")
    print(f"  {'-'*40}")
    print(f"  TRL等级:     {comm['trl']}")
    print(f"  预计时间:    {comm['base_time']}")
    print(f"  置信度:      {comm['confidence']}")
    if comm["factors"]:
        print(f"  影响因素:")
        for f in comm["factors"]:
            print(f"    - {f}")

    print(f"\n  自动标签:")
    print(f"  {'-'*40}")
    for tag in tags:
        category_map = {"discipline": "学科", "technology": "技术",
                        "innovation_type": "类型", "trl": "成熟度"}
        cat = category_map.get(tag["category"], tag["category"])
        print(f"  [{cat}] {tag['name']} (置信度: {tag['confidence']})")

    print(f"\n{'='*60}")


def cmd_ratings(args):
    init_db()
    ratings = get_all_ratings(limit=args.limit, order_by=args.sort)
    print_ratings_summary(ratings)


def cmd_stats(args):
    init_db()
    stats = get_stats()
    print_stats(stats)


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(
        description="Paper Analysis Engine - 论文智能分析引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python cli.py search "LLM" -n 20
  python cli.py view <paper_id>
  python cli.py analyze <paper_id>
  python cli.py ratings --sort overall_score -n 20
  python cli.py stats

新增功能:
  python cli.py export --format csv -o papers.csv
  python cli.py export --format json -o papers.json --query "LLM"
  python cli.py export --format bibtex -o refs.bib
  python cli.py combine <paper_id> -n 10
  python cli.py trends --dimension year
  python cli.py trends --dimension journal --limit 20
  python cli.py trends --dimension field
  python cli.py trends --dimension rating
  python cli.py tags --limit 20
  python cli.py tags <paper_id>
  python cli.py compare <id1> <id2>
  python cli.py delete <paper_id> --force

导入论文:
  python import_papers.py topic "固态电池" -n 50
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # search
    p_search = subparsers.add_parser("search", help="搜索本地数据库中的论文")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("-n", "--limit", type=int, default=20, help="结果数量 (默认20)")
    p_search.add_argument("--year-from", type=int, help="起始年份")
    p_search.add_argument("--year-to", type=int, help="结束年份")
    p_search.add_argument("--min-citations", type=int, default=0, help="最低引用数")

    # view
    p_view = subparsers.add_parser("view", help="查看论文详情")
    p_view.add_argument("paper_id", help="论文ID")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="深度分析论文")
    p_analyze.add_argument("paper_id", help="论文ID")

    # ratings
    p_ratings = subparsers.add_parser("ratings", help="查看评级排行榜")
    p_ratings.add_argument("-n", "--limit", type=int, default=20, help="显示数量")
    p_ratings.add_argument("--sort", default="overall_score",
                           choices=["overall_score", "academic_impact", "commercial_potential",
                                    "innovation_index", "reproducibility", "combo_value"],
                           help="排序字段")

    # stats
    p_stats = subparsers.add_parser("stats", help="查看数据库统计")

    # === 新增: export ===
    p_export = subparsers.add_parser("export", help="导出论文数据")
    p_export.add_argument("--format", default="csv",
                          choices=["csv", "json", "bibtex"],
                          help="导出格式 (默认 csv)")
    p_export.add_argument("-o", "--output", default="papers_export.csv",
                          help="输出文件路径")
    p_export.add_argument("--query", help="只导出匹配关键词的论文")

    # === 新增: combine ===
    p_combine = subparsers.add_parser("combine", help="组合分析 - 找出协同论文")
    p_combine.add_argument("paper_id", help="论文ID")
    p_combine.add_argument("-n", "--limit", type=int, default=10, help="显示数量 (默认10)")

    # === 新增: trends ===
    p_trends = subparsers.add_parser("trends", help="趋势统计分析")
    p_trends.add_argument("--dimension", default="year",
                          choices=["year", "journal", "field", "rating"],
                          help="分析维度 (默认 year)")
    p_trends.add_argument("-n", "--limit", type=int, default=20, help="显示数量")

    # === 新增: tags ===
    p_tags = subparsers.add_parser("tags", help="标签统计")
    p_tags.add_argument("paper_id", nargs="?", help="论文ID (不指定则统计全部)")
    p_tags.add_argument("-n", "--limit", type=int, default=20, help="显示数量")

    # === 新增: compare ===
    p_compare = subparsers.add_parser("compare", help="对比两篇论文")
    p_compare.add_argument("id1", help="论文A的ID")
    p_compare.add_argument("id2", help="论文B的ID")

    # === 新增: delete ===
    p_delete = subparsers.add_parser("delete", help="删除论文")
    p_delete.add_argument("paper_id", help="论文ID")
    p_delete.add_argument("--force", action="store_true", help="跳过确认")

    # === 新增: ai ===
    p_ai = subparsers.add_parser("ai", help="AI 智能分析论文")
    p_ai.add_argument("paper_id", help="论文ID")
    p_ai.add_argument("action", choices=["summary", "translate", "plain", "value", "function", "all"],
                      default="all", nargs="?", help="分析类型 (默认 all)")

    # === 新增: ai-compare ===
    p_ai_cmp = subparsers.add_parser("ai-compare", help="AI 对比两篇论文")
    p_ai_cmp.add_argument("id1", help="论文A的ID")
    p_ai_cmp.add_argument("id2", help="论文B的ID")

    # === 新增: ai-switch ===
    p_ai_sw = subparsers.add_parser("ai-switch", help="切换 LLM 提供商")
    p_ai_sw.add_argument("provider", choices=["deepseek", "groq", "glm"], help="提供商")

    # 收藏夹
    p_fav = subparsers.add_parser("fav", help="收藏夹管理")
    p_fav_sub = p_fav.add_subparsers(dest="fav_cmd")
    p_fav_sub.add_parser("list", help="列出收藏夹")
    p_fav_add = p_fav_sub.add_parser("add", help="收藏论文")
    p_fav_add.add_argument("collection_id", type=int, help="收藏夹ID")
    p_fav_add.add_argument("paper_id", help="论文ID")
    p_fav_add.add_argument("--notes", default="", help="笔记")
    p_fav_rm = p_fav_sub.add_parser("remove", help="移除收藏")
    p_fav_rm.add_argument("collection_id", type=int, help="收藏夹ID")
    p_fav_rm.add_argument("paper_id", help="论文ID")
    p_fav_create = p_fav_sub.add_parser("create", help="创建收藏夹")
    p_fav_create.add_argument("name", help="收藏夹名称")
    p_fav_create.add_argument("--desc", default="", help="描述")

    # 推荐
    p_rec = subparsers.add_parser("rec", help="论文推荐")
    p_rec.add_argument("-s", "--strategy", choices=["hybrid", "content", "rating", "trending", "recent"],
                        default="hybrid", help="推荐策略")
    p_rec.add_argument("-n", "--top", type=int, default=10, help="推荐数量")

    # 报告
    p_report = subparsers.add_parser("report", help="生成报告")
    p_report.add_argument("-t", "--type", choices=["stats", "paper", "collection", "recommendations"],
                           default="stats", help="报告类型")
    p_report.add_argument("-f", "--format", choices=["md", "html"], default="md", help="格式")
    p_report.add_argument("--id", help="论文ID或收藏夹ID")

    # 推送
    p_push = subparsers.add_parser("push", help="定时推送")
    p_push_sub = p_push.add_subparsers(dest="push_cmd")
    p_push_sub.add_parser("list", help="列出订阅")
    p_push_test = p_push_sub.add_parser("test", help="测试推送")
    p_push_test.add_argument("subscription_id", type=int, help="订阅ID")
    p_push_serve = p_push_sub.add_parser("serve", help="启动定时服务")
    p_push_serve.add_argument("--interval", type=int, default=60, help="检查间隔(分钟)")

    args = parser.parse_args()

    commands = {
        "search": cmd_search,
        "view": cmd_view,
        "analyze": cmd_analyze,
        "ratings": cmd_ratings,
        "stats": cmd_stats,
        "export": cmd_export,
        "combine": cmd_combine,
        "trends": cmd_trends,
        "tags": cmd_tags,
        "compare": cmd_compare,
        "delete": cmd_delete,
        "ai": cmd_ai,
        "ai-compare": cmd_ai_compare,
        "ai-switch": cmd_ai_switch,
        "fav": cmd_fav,
        "rec": cmd_rec,
        "report": cmd_report,
        "push": cmd_push,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
