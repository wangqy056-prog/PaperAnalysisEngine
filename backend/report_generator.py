"""导出报告生成模块

支持生成多种格式报告:
1. 单篇论文详细报告 (Markdown/HTML)
2. 收藏夹总结报告
3. 检索结果报告
4. 统计分析报告
5. 推荐清单报告
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from db import get_connection, DB_PATH


REPORT_DIR = DB_PATH.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ==================== 工具函数 ====================

def _parse_json_field(value, default=None):
    if default is None:
        default = []
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _format_authors(authors: list, max_n: int = 5) -> str:
    if not authors:
        return "N/A"
    if len(authors) > max_n:
        return f"{', '.join(authors[:max_n])} 等{len(authors)}人"
    return ", ".join(authors)


def _get_paper_full(paper_id: str) -> Optional[Dict]:
    """获取论文完整信息（含评级、标签）"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    paper = dict(row)

    # 解析JSON字段
    paper["authors"] = _parse_json_field(paper.get("authors"))
    paper["fields"] = _parse_json_field(paper.get("fields"))
    paper["ref_ids"] = _parse_json_field(paper.get("ref_ids"))

    # 评级
    cursor.execute("SELECT * FROM ratings WHERE paper_id = ?", (paper_id,))
    rating = cursor.fetchone()
    paper["rating"] = dict(rating) if rating else None

    # 标签
    cursor.execute("""
        SELECT t.name, t.category FROM tags t
        JOIN paper_tags pt ON t.id = pt.tag_id
        WHERE pt.paper_id = ?
    """, (paper_id,))
    paper["tags"] = [dict(r) for r in cursor.fetchall()]

    # 收藏夹
    cursor.execute("""
        SELECT c.name, c.color FROM collections c
        JOIN favorites f ON c.id = f.collection_id
        WHERE f.paper_id = ?
    """, (paper_id,))
    paper["collections"] = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return paper


# ==================== Markdown 报告 ====================

def generate_paper_report_md(paper_id: str) -> str:
    """生成单篇论文的Markdown详细报告"""
    paper = _get_paper_full(paper_id)
    if not paper:
        return f"# 错误\n\n未找到论文: {paper_id}"

    rating = paper.get("rating", {}) or {}
    tags = paper.get("tags", [])
    refs = paper.get("ref_ids", [])

    md = f"""# {paper.get('title', '无标题')}

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 基本信息

| 字段 | 内容 |
|------|------|
| **论文ID** | `{paper.get('id')}` |
| **DOI** | {paper.get('doi') or 'N/A'} |
| **期刊** | {paper.get('journal') or 'N/A'} |
| **年份** | {paper.get('year') or 'N/A'} |
| **引用量** | {paper.get('citations', 0)} |
| **作者** | {_format_authors(paper.get('authors', []))} |
| **来源** | {paper.get('source', 'N/A')} |
| **原文链接** | {paper.get('url') or 'N/A'} |
| **PDF下载** | {paper.get('pdf_url') or 'N/A'} |

## 研究领域

{os.linesep.join(f'- {f}' for f in (paper.get('fields') or [])) or '无'}

## 摘要

{paper.get('abstract') or '无摘要'}

## 五维评级

| 维度 | 得分 | 等级 |
|------|------|------|
| 学术影响力 | {rating.get('academic_impact', 0):.1f} | - |
| 商业潜力 | {rating.get('commercial_potential', 0):.1f} | - |
| 创新指数 | {rating.get('innovation_index', 0):.1f} | - |
| 可复现性 | {rating.get('reproducibility', 0):.1f} | - |
| 组合价值 | {rating.get('combo_value', 0):.1f} | - |
| **综合评分** | **{rating.get('overall_score', 0):.1f}** | **{rating.get('rating_level', '?')}** |

## 标签

{os.linesep.join(f'- [{t["category"]}] {t["name"]}' for t in tags) or '无标签'}

## 引用关系

- 引用文献数：{len(refs)}
- 收藏于：{', '.join(c['name'] for c in paper.get('collections', [])) or '未收藏'}

---

*报告由 Paper Analysis Engine 生成*
"""
    return md


def generate_collection_report_md(collection_id: int) -> str:
    """生成收藏夹报告"""
    from favorites_manager import get_collection, list_papers_in_collection

    collection = get_collection(collection_id)
    if not collection:
        return f"# 错误\n\n未找到收藏夹: {collection_id}"

    papers = list_papers_in_collection(collection_id, limit=9999)

    md = f"""# 收藏夹报告：{collection['name']}

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 论文数量：{len(papers)} 篇

## 收藏夹信息

- **名称**：{collection['name']}
- **描述**：{collection.get('description') or '无'}
- **创建时间**：{collection.get('created_at', 'N/A')}

## 论文清单

| # | 标题 | 年份 | 期刊 | 引用 | 等级 | 评分 |
|---|------|------|------|------|------|------|
"""
    for i, p in enumerate(papers, 1):
        title = (p.get('title') or '')[:50]
        level = p.get('rating_level') or '-'
        score = p.get('overall_score') or 0
        md += f"| {i} | {title} | {p.get('year', '')} | {(p.get('journal') or '')[:20]} | {p.get('citations', 0)} | {level} | {score:.1f} |\n"

    # 统计信息
    if papers:
        avg_score = sum(p.get('overall_score') or 0 for p in papers) / len(papers)
        level_dist = {}
        for p in papers:
            level = p.get('rating_level') or '?'
            level_dist[level] = level_dist.get(level, 0) + 1

        md += f"""
## 统计

- **平均评分**：{avg_score:.1f}
- **评级分布**：{', '.join(f'{k}={v}' for k, v in sorted(level_dist.items()))}
- **总引用量**：{sum(p.get('citations', 0) for p in papers)}

---

*报告由 Paper Analysis Engine 生成*
"""
    return md


def generate_search_report_md(query: str, papers: List[Dict]) -> str:
    """生成检索结果报告"""
    md = f"""# 检索报告

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 检索关键词：{query}
> 结果数量：{len(papers)} 篇

## 检索结果

| # | 标题 | 年份 | 期刊 | 引用 | 等级 | 评分 |
|---|------|------|------|------|------|------|
"""
    for i, p in enumerate(papers, 1):
        title = (p.get('title') or '')[:50]
        level = p.get('rating_level') or '-'
        score = p.get('overall_score') or 0
        md += f"| {i} | {title} | {p.get('year', '')} | {(p.get('journal') or '')[:20]} | {p.get('citations', 0)} | {level} | {score:.1f} |\n"

    md += f"""
---

*报告由 Paper Analysis Engine 生成*
"""
    return md


def generate_stats_report_md() -> str:
    """生成统计分析报告"""
    from db import get_stats
    stats = get_stats()

    md = f"""# 数据库统计报告

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 概览

| 指标 | 数值 |
|------|------|
| 论文总数 | {stats.get('total_papers', 0)} |
| 评级总数 | {stats.get('total_ratings', 0)} |
| 标签总数 | {stats.get('total_tags', 0)} |
| 平均评分 | {stats.get('avg_score', 0)} |
| 最高评分 | {stats.get('max_score', 0)} |
| 最低评分 | {stats.get('min_score', 0)} |

## 评级分布

| 等级 | 数量 | 占比 |
|------|------|------|
"""
    dist = stats.get("level_distribution", {})
    total = sum(dist.values()) or 1
    for level in ["S", "A", "B", "C", "D"]:
        count = dist.get(level, 0)
        pct = count / total * 100
        md += f"| {level} | {count} | {pct:.1f}% |\n"

    md += f"""
---

*报告由 Paper Analysis Engine 生成*
"""
    return md


def generate_recommendation_report_md(recommendations: List[Dict]) -> str:
    """生成推荐清单报告"""
    md = f"""# 论文推荐清单

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 推荐数量：{len(recommendations)} 篇

## 推荐列表

| # | 标题 | 评分 | 推荐分 | 推荐理由 |
|---|------|------|--------|---------|
"""
    for i, r in enumerate(recommendations, 1):
        title = (r.get('title') or '')[:50]
        score = r.get('overall_score') or 0
        rec_score = r.get('recommend_score', 0)
        reason = r.get('match_reason', '')
        md += f"| {i} | {title} | {score:.1f} | {rec_score:.2f} | {reason} |\n"

    md += f"""
---

*报告由 Paper Analysis Engine 生成*
"""
    return md


# ==================== HTML 报告 ====================

def _md_to_html_basic(md: str, title: str = "报告") -> str:
    """简易Markdown转HTML（不依赖外部库）"""
    import re
    lines = md.split('\n')
    html_lines = []
    in_table = False
    in_code = False

    for line in lines:
        if line.startswith('```'):
            if in_code:
                html_lines.append('</code></pre>')
                in_code = False
            else:
                html_lines.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue

        # 标题
        if line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('> '):
            html_lines.append(f'<blockquote>{line[2:]}</blockquote>')
        elif line.startswith('---'):
            html_lines.append('<hr>')
        elif line.startswith('| '):
            # 表格
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if all(set(c) <= set('-: ') for c in cells):
                continue  # 分隔行
            if not in_table:
                html_lines.append('<table>')
                in_table = True
                html_lines.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
            else:
                html_lines.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        elif in_table:
            html_lines.append('</table>')
            in_table = False
            if line.strip():
                html_lines.append(f'<p>{line}</p>')
        elif line.strip():
            html_lines.append(f'<p>{line}</p>')

    if in_table:
        html_lines.append('</table>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', sans-serif; max-width: 900px;
       margin: 40px auto; padding: 20px; color: #333; line-height: 1.6; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #34495e; margin-top: 30px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
th {{ background: #f5f5f5; font-weight: bold; }}
tr:nth-child(even) {{ background: #fafafa; }}
blockquote {{ background: #fff3cd; padding: 10px 20px; border-left: 4px solid #ffc107; margin: 10px 0; }}
hr {{ border: none; border-top: 1px solid #eee; margin: 30px 0; }}
code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
pre {{ background: #f5f5f5; padding: 15px; border-radius: 5px; overflow-x: auto; }}
</style>
</head>
<body>
{chr(10).join(html_lines)}
</body>
</html>"""


# ==================== 统一导出入口 ====================

def save_report(content: str, filename: str, fmt: str = "md") -> str:
    """保存报告到文件"""
    ext = {"md": "md", "html": "html", "json": "json"}.get(fmt, "md")
    filepath = REPORT_DIR / f"{filename}.{ext}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return str(filepath)


def export_paper_report(paper_id: str, fmt: str = "md") -> str:
    """导出单篇论文报告"""
    if fmt == "html":
        md = generate_paper_report_md(paper_id)
        title = _get_paper_full(paper_id).get("title", "report")[:30]
        return save_report(_md_to_html_basic(md, title), f"paper_{paper_id}", "html")
    else:
        md = generate_paper_report_md(paper_id)
        return save_report(md, f"paper_{paper_id}", "md")


def export_collection_report(collection_id: int, fmt: str = "md") -> str:
    """导出收藏夹报告"""
    from favorites_manager import get_collection
    collection = get_collection(collection_id)
    name = collection["name"] if collection else f"collection_{collection_id}"

    if fmt == "html":
        md = generate_collection_report_md(collection_id)
        return save_report(_md_to_html_basic(md, name), f"collection_{collection_id}", "html")
    else:
        md = generate_collection_report_md(collection_id)
        return save_report(md, f"collection_{collection_id}", "md")


def export_search_report(query: str, papers: List[Dict], fmt: str = "md") -> str:
    """导出检索报告"""
    safe_query = "".join(c if c.isalnum() else "_" for c in query)[:30]
    if fmt == "html":
        md = generate_search_report_md(query, papers)
        return save_report(_md_to_html_basic(md, f"搜索: {query}"), f"search_{safe_query}", "html")
    else:
        md = generate_search_report_md(query, papers)
        return save_report(md, f"search_{safe_query}", "md")


def export_stats_report(fmt: str = "md") -> str:
    """导出统计报告"""
    if fmt == "html":
        md = generate_stats_report_md()
        return save_report(_md_to_html_basic(md, "数据库统计"), "stats", "html")
    else:
        md = generate_stats_report_md()
        return save_report(md, "stats", "md")


def export_recommendation_report(recommendations: List[Dict], fmt: str = "md") -> str:
    """导出推荐清单报告"""
    if fmt == "html":
        md = generate_recommendation_report_md(recommendations)
        return save_report(_md_to_html_basic(md, "论文推荐"), "recommendations", "html")
    else:
        md = generate_recommendation_report_md(recommendations)
        return save_report(md, "recommendations", "md")


def list_reports() -> List[Dict]:
    """列出已生成的报告"""
    reports = []
    for f in REPORT_DIR.glob("*"):
        if f.is_file() and f.suffix in (".md", ".html", ".json"):
            reports.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    reports.sort(key=lambda x: x["created_at"], reverse=True)
    return reports


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    # 生成统计报告
    path = export_stats_report("md")
    print(f"统计报告已生成: {path}")

    # 生成推荐报告
    from recommendation_engine import get_recommendations
    recs = get_recommendations("hybrid", top_n=10)
    if recs:
        path = export_recommendation_report(recs, "md")
        print(f"推荐报告已生成: {path}")

    print(f"\n报告目录: {REPORT_DIR}")
