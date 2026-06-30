"""知识图谱构建模块 - 论文关系网络可视化

支持4种网络视图:
1. 领域共现网络 - 论文通过共同研究领域连接
2. 作者合作网络 - 共同作者关系
3. 关键词共现网络 - 标题关键词共现
4. 引用网络 - 论文引用关系（需补充抓取数据）
"""

import json
import re
import sqlite3
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional

import networkx as nx
from db import get_connection


# ==================== 通用工具 ====================

def _load_papers() -> List[dict]:
    """加载所有论文（解析JSON字段）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM papers")
    rows = cursor.fetchall()
    conn.close()

    papers = []
    for row in rows:
        p = dict(row)
        # 解析JSON字段
        try:
            p["authors"] = json.loads(p.get("authors") or "[]")
        except (json.JSONDecodeError, TypeError):
            p["authors"] = []
        try:
            p["fields"] = json.loads(p.get("fields") or "[]")
        except (json.JSONDecodeError, TypeError):
            p["fields"] = []
        try:
            p["ref_ids"] = json.loads(p.get("ref_ids") or "[]")
        except (json.JSONDecodeError, TypeError):
            p["ref_ids"] = []
        papers.append(p)
    return papers


def _load_ratings() -> Dict[str, dict]:
    """加载所有评级，返回 paper_id -> rating 映射"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ratings")
    rows = cursor.fetchall()
    conn.close()
    return {row["paper_id"]: dict(row) for row in rows}


def _compute_layout(G: nx.Graph, layout_type: str = "spring") -> Dict[str, Tuple[float, float]]:
    """计算节点布局位置"""
    if len(G.nodes) == 0:
        return {}
    try:
        if layout_type == "spring":
            pos = nx.spring_layout(G, k=1.5/len(G.nodes)**0.5, iterations=80, seed=42)
        elif layout_type == "circular":
            pos = nx.circular_layout(G)
        elif layout_type == "kamada":
            pos = nx.kamada_kawai_layout(G)
        else:
            pos = nx.spring_layout(G, seed=42)
    except Exception:
        pos = nx.random_layout(G, seed=42)
    return {n: (float(p[0]), float(p[1])) for n, p in pos.items()}


# 颜色方案
COLOR_SCALES = {
    "领域共现": "Viridis",
    "作者合作": "Plasma",
    "关键词共现": "Inferno",
    "引用网络": "Turbo",
    "论文相似": "Cividis",
}


# ==================== 1. 领域共现网络 ====================

def build_field_network(top_n: int = 40, min_cooccurrence: int = 2) -> Tuple[nx.Graph, dict]:
    """
    构建领域共现网络

    - 节点 = 研究领域
    - 节点大小 = 出现在多少篇论文中
    - 边 = 两个领域在同一篇论文中共现的次数
    """
    papers = _load_papers()

    # 统计每个领域的论文数
    field_paper_count = Counter()
    # 统计领域共现
    field_pairs = Counter()

    for p in papers:
        fields = p.get("fields") or []
        if not isinstance(fields, list):
            continue
        for f in fields:
            field_paper_count[f] += 1
        # 共现对
        unique_fields = sorted(set(fields))
        for i in range(len(unique_fields)):
            for j in range(i + 1, len(unique_fields)):
                field_pairs[(unique_fields[i], unique_fields[j])] += 1

    # 取Top领域
    top_fields = [f for f, _ in field_paper_count.most_common(top_n)]
    top_set = set(top_fields)

    # 构建图
    G = nx.Graph()
    for f in top_fields:
        G.add_node(f, size=field_paper_count[f])

    for (f1, f2), count in field_pairs.items():
        if f1 in top_set and f2 in top_set and count >= min_cooccurrence:
            G.add_edge(f1, f2, weight=count)

    stats = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "top_fields": field_paper_count.most_common(10),
        "top_pairs": [(list(pair), cnt) for pair, cnt in field_pairs.most_common(10)],
        "total_fields": len(field_paper_count),
    }
    return G, stats


# ==================== 2. 作者合作网络 ====================

def build_author_network(min_papers: int = 2, min_cooperation: int = 2, top_n: int = 60) -> Tuple[nx.Graph, dict]:
    """
    构建作者合作网络

    - 节点 = 作者
    - 节点大小 = 发表论文数
    - 边 = 两位作者合作次数
    """
    papers = _load_papers()

    # 统计每位作者的论文数
    author_papers = Counter()
    # 统计合作对
    author_pairs = Counter()

    for p in papers:
        authors = p.get("authors") or []
        if not isinstance(authors, list) or len(authors) == 0:
            continue
        for a in authors:
            author_papers[a] += 1
        # 合作对
        unique_authors = sorted(set(authors))
        for i in range(len(unique_authors)):
            for j in range(i + 1, len(unique_authors)):
                author_pairs[(unique_authors[i], unique_authors[j])] += 1

    # 筛选: 至少发表 min_papers 篇，取Top
    top_authors = [a for a, c in author_papers.most_common(top_n) if c >= min_papers]
    top_set = set(top_authors)

    G = nx.Graph()
    for a in top_authors:
        G.add_node(a, size=author_papers[a])

    for (a1, a2), count in author_pairs.items():
        if a1 in top_set and a2 in top_set and count >= min_cooperation:
            G.add_edge(a1, a2, weight=count)

    # 移除孤立节点（没有连接的）
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    G.remove_nodes_from(isolated)

    stats = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "removed_isolated": len(isolated),
        "top_authors": author_papers.most_common(10),
        "top_collaborations": [(list(pair), cnt) for pair, cnt in author_pairs.most_common(10)],
        "total_authors": len(author_papers),
    }
    return G, stats


# ==================== 3. 关键词共现网络 ====================

STOPWORDS = {
    "the", "a", "an", "of", "and", "in", "to", "for", "on", "with", "by",
    "is", "are", "was", "were", "be", "been", "from", "as", "at", "it",
    "this", "that", "these", "those", "or", "if", "not", "but", "via",
    "using", "through", "into", "its", "their", "we", "our", "can",
    "will", "may", "might", "should", "would", "could", "also", "than",
    "more", "most", "such", "some", "any", "all", "both", "each", "other",
    "new", "one", "two", "three", "first", "second", "based", "approach",
    "method", "methods", "study", "studies", "paper", "research", "analysis",
    "system", "systems", "model", "models", "results", "show", "shown",
}

# 偏长或具领域意义的词组（提升权重）
IMPORTANT_TERMS = {
    "learning", "neural", "network", "quantum", "cell", "battery", "solar",
    "robot", "chip", "satellite", "crispr", "protein", "materials", "energy",
}


def _extract_keywords(title: str, max_len: int = 20) -> List[str]:
    """从标题提取关键词"""
    if not title:
        return []
    words = re.findall(r"[a-zA-Z][a-zA-Z-]+", title.lower())
    keywords = []
    for w in words:
        if len(w) < 3 or w in STOPWORDS:
            continue
        keywords.append(w)
    return keywords


def build_keyword_network(top_n: int = 50, min_cooccurrence: int = 3) -> Tuple[nx.Graph, dict]:
    """
    构建关键词共现网络

    - 节点 = 关键词
    - 节点大小 = 出现次数
    - 边 = 两个关键词在同一标题中共现次数
    """
    papers = _load_papers()

    word_count = Counter()
    word_pairs = Counter()

    for p in papers:
        title = p.get("title") or ""
        keywords = _extract_keywords(title)
        for w in keywords:
            word_count[w] += 1
        # 共现对
        unique = sorted(set(keywords))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                word_pairs[(unique[i], unique[j])] += 1

    top_words = [w for w, _ in word_count.most_common(top_n)]
    top_set = set(top_words)

    G = nx.Graph()
    for w in top_words:
        G.add_node(w, size=word_count[w])

    for (w1, w2), count in word_pairs.items():
        if w1 in top_set and w2 in top_set and count >= min_cooccurrence:
            G.add_edge(w1, w2, weight=count)

    # 移除孤立节点
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    G.remove_nodes_from(isolated)

    stats = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "removed_isolated": len(isolated),
        "top_keywords": word_count.most_common(15),
        "top_pairs": [(list(pair), cnt) for pair, cnt in word_pairs.most_common(10)],
        "total_words": len(word_count),
    }
    return G, stats


# ==================== 4. 引用网络 ====================

def build_citation_network() -> Tuple[nx.DiGraph, dict]:
    """
    构建论文引用网络（有向图）

    - 节点 = 论文
    - 边 = 论文A 引用了 论文B（A->B）
    - 只包含数据库内存在的论文之间的引用
    """
    papers = _load_papers()
    paper_ids = {p["id"] for p in papers}

    G = nx.DiGraph()
    internal_links = 0
    papers_with_internal_refs = 0

    for p in papers:
        pid = p["id"]
        refs = p.get("ref_ids") or []
        if not isinstance(refs, list):
            continue
        internal_refs = [r for r in refs if r in paper_ids and r != pid]
        if internal_refs:
            papers_with_internal_refs += 1
            G.add_node(pid, title=p.get("title", ""), year=p.get("year"),
                       citations=p.get("citations", 0))
            for ref_id in internal_refs:
                G.add_edge(pid, ref_id, type="cites")
                internal_links += 1

    # 补充被引用的论文节点信息
    cited_ids = {v for u, v in G.edges()}
    for p in papers:
        if p["id"] in cited_ids and p["id"] not in G:
            G.add_node(p["id"], title=p.get("title", ""), year=p.get("year"),
                       citations=p.get("citations", 0))

    stats = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "internal_links": internal_links,
        "papers_with_internal_refs": papers_with_internal_refs,
        "has_citation_data": internal_links > 0,
        "message": ("引用网络数据完整" if internal_links > 0
                    else "数据库中论文的引用关系(ref_ids)为空，无法构建引用网络。"
                         "建议运行 fetch_references.py 补充抓取引用关系。"),
    }
    return G, stats


# ==================== 5. 论文相似性网络 ====================

def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """计算Jaccard相似度"""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def build_similarity_network(top_n: int = 80, min_similarity: float = 0.2,
                              knn: int = 5) -> Tuple[nx.Graph, dict]:
    """
    构建论文相似性网络（基于领域+标题+摘要关键词的Jaccard相似度）

    - 节点 = 论文（Top评分的）
    - 边 = 相似度 >= min_similarity，或属于每篇论文最相似的 knn 篇
    - 边权重 = 相似度
    """
    papers = _load_papers()
    ratings = _load_ratings()

    # 按评分排序取Top论文
    scored = []
    for p in papers:
        r = ratings.get(p["id"])
        score = r["overall_score"] if r else 0
        scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    top_papers = [p for _, p in scored[:top_n]]

    # 为每篇论文构建特征集（领域+标题关键词+摘要关键词+作者）
    features = {}
    for p in top_papers:
        feats = set(p.get("fields") or [])
        feats.update(_extract_keywords(p.get("title") or ""))
        # 摘要关键词（取前15个）
        abstract = p.get("abstract") or ""
        abs_keywords = _extract_keywords(abstract)[:15]
        feats.update(abs_keywords)
        # 作者
        feats.update((p.get("authors") or [])[:3])
        features[p["id"]] = feats

    G = nx.Graph()
    for p in top_papers:
        r = ratings.get(p["id"], {})
        G.add_node(p["id"],
                   title=(p.get("title") or "")[:50],
                   score=r.get("overall_score", 0),
                   level=r.get("rating_level", "?"),
                   year=p.get("year"))

    # 计算所有对的相似度
    edges_added = 0
    # 记录每篇论文最相似的 knn 篇
    knn_map = defaultdict(list)

    for i in range(len(top_papers)):
        for j in range(i + 1, len(top_papers)):
            p1, p2 = top_papers[i], top_papers[j]
            sim = _jaccard_similarity(features[p1["id"]], features[p2["id"]])
            if sim >= min_similarity:
                G.add_edge(p1["id"], p2["id"], weight=round(sim, 3))
                edges_added += 1
            # 记录kNN候选
            knn_map[p1["id"]].append((sim, p2["id"]))
            knn_map[p2["id"]].append((sim, p1["id"]))

    # 对孤立节点，连接其最相似的 knn 篇（保证网络连通性）
    for node_id in list(G.nodes):
        if G.degree(node_id) > 0:
            continue
        neighbors = sorted(knn_map.get(node_id, []), reverse=True)[:knn]
        for sim, neighbor_id in neighbors:
            if sim > 0:
                G.add_edge(node_id, neighbor_id, weight=round(sim, 3))
                edges_added += 1
                break

    # 移除仍然孤立的节点
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    G.remove_nodes_from(isolated)

    stats = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "removed_isolated": len(isolated),
        "min_similarity": min_similarity,
        "analyzed_papers": len(top_papers),
        "avg_degree": round(2 * G.number_of_edges() / G.number_of_nodes(), 2) if G.number_of_nodes() else 0,
        "message": f"基于领域+标题+摘要关键词的Jaccard相似度（阈值 {min_similarity}），分析Top {len(top_papers)} 篇论文",
    }
    return G, stats


# ==================== 统一入口 ====================

GRAPH_BUILDERS = {
    "领域共现": build_field_network,
    "作者合作": build_author_network,
    "关键词共现": build_keyword_network,
    "论文相似": build_similarity_network,
    "引用网络": lambda: build_citation_network(),
}


def build_graph(graph_type: str, **kwargs) -> Tuple[nx.Graph, dict]:
    """统一构建入口"""
    builder = GRAPH_BUILDERS.get(graph_type)
    if builder is None:
        raise ValueError(f"未知图谱类型: {graph_type}，可选: {list(GRAPH_BUILDERS.keys())}")

    # 不同类型有不同参数
    if graph_type == "领域共现":
        return build_field_network(top_n=kwargs.get("top_n", 40),
                                   min_cooccurrence=kwargs.get("min_cooccurrence", 2))
    elif graph_type == "作者合作":
        return build_author_network(min_papers=kwargs.get("min_papers", 2),
                                     min_cooperation=kwargs.get("min_cooperation", 2),
                                     top_n=kwargs.get("top_n", 60))
    elif graph_type == "关键词共现":
        return build_keyword_network(top_n=kwargs.get("top_n", 50),
                                      min_cooccurrence=kwargs.get("min_cooccurrence", 3))
    elif graph_type == "论文相似":
        return build_similarity_network(top_n=kwargs.get("top_n", 80),
                                         min_similarity=kwargs.get("min_similarity", 0.2),
                                         knn=kwargs.get("knn", 5))
    elif graph_type == "引用网络":
        return build_citation_network()
    return builder()


def get_graph_summary() -> dict:
    """获取所有图谱类型的概要信息"""
    papers = _load_papers()
    ratings = _load_ratings()

    # 统计有引用关系的论文
    papers_with_refs = sum(1 for p in papers if p.get("ref_ids"))

    return {
        "total_papers": len(papers),
        "total_ratings": len(ratings),
        "papers_with_references": papers_with_refs,
        "graph_types": list(GRAPH_BUILDERS.keys()),
    }


if __name__ == "__main__":
    # 测试
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    print("=" * 60)
    print("  知识图谱构建测试")
    print("=" * 60)

    summary = get_graph_summary()
    print(f"\n  论文总数: {summary['total_papers']}")
    print(f"  评级总数: {summary['total_ratings']}")
    print(f"  有引用关系的论文: {summary['papers_with_references']}")

    for gtype in ["领域共现", "作者合作", "关键词共现", "论文相似", "引用网络"]:
        print(f"\n--- {gtype} ---")
        try:
            G, stats = build_graph(gtype)
            print(f"  节点数: {stats.get('node_count', 0)}")
            print(f"  边数:   {stats.get('edge_count', 0)}")
            if stats.get("message"):
                print(f"  说明:   {stats['message']}")
            if stats.get("top_fields"):
                print(f"  Top领域:")
                for f, c in stats["top_fields"][:5]:
                    print(f"    {f}: {c}")
            if stats.get("top_authors"):
                print(f"  Top作者:")
                for a, c in stats["top_authors"][:5]:
                    print(f"    {a}: {c}篇")
            if stats.get("top_keywords"):
                print(f"  Top关键词:")
                for w, c in stats["top_keywords"][:5]:
                    print(f"    {w}: {c}")
        except Exception as e:
            print(f"  错误: {e}")
