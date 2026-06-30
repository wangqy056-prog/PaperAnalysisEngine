"""论文推荐引擎

基于多种策略推荐论文:
1. 基于内容相似度 - 与用户收藏/浏览过的论文相似
2. 基于领域偏好 - 用户偏好的研究领域
3. 基于评分 - 高评分论文推荐
4. 基于热度 - 高引用、高评分
5. 基于时间 - 最新高质量论文
6. 协同推荐 - 收藏夹中的论文作者其他作品
"""

import json
import sqlite3
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Set
from datetime import datetime
from db import get_connection


# ==================== 用户行为追踪 ====================

def record_view(paper_id: str):
    """记录论文浏览"""
    conn = get_connection()
    cursor = conn.cursor()
    # 如果已存在则增加计数
    cursor.execute(
        """INSERT INTO viewing_history (paper_id, viewed_at, view_count)
           VALUES (?, ?, 1)
           ON CONFLICT(paper_id) DO UPDATE SET
               view_count = view_count + 1,
               viewed_at = excluded.viewed_at""",
        (paper_id, datetime.now().isoformat())
    )
    # SQLite 老版本不支持 ON CONFLICT，备选方案
    if cursor.rowcount == 0:
        cursor.execute("SELECT id FROM viewing_history WHERE paper_id = ?", (paper_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE viewing_history SET view_count = view_count + 1, viewed_at = ? WHERE paper_id = ?",
                (datetime.now().isoformat(), paper_id)
            )
        else:
            cursor.execute(
                "INSERT INTO viewing_history (paper_id, viewed_at, view_count) VALUES (?, ?, 1)",
                (paper_id, datetime.now().isoformat())
            )
    conn.commit()
    conn.close()


def rate_paper_user(paper_id: str, rating: int, comment: str = "") -> bool:
    """用户对论文打分（1-5星）"""
    if not 1 <= rating <= 5:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO user_ratings (paper_id, rating, comment, rated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(paper_id) DO UPDATE SET
                   rating = excluded.rating,
                   comment = excluded.comment,
                   rated_at = excluded.rated_at""",
            (paper_id, rating, comment, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        # 老版本 SQLite 兼容
        try:
            cursor.execute("DELETE FROM user_ratings WHERE paper_id = ?", (paper_id,))
            cursor.execute(
                "INSERT INTO user_ratings (paper_id, rating, comment, rated_at) VALUES (?, ?, ?, ?)",
                (paper_id, rating, comment, datetime.now().isoformat())
            )
            conn.commit()
            return True
        except Exception as e2:
            print(f"[ERROR] 用户评分失败: {e2}")
            return False
    finally:
        conn.close()


def set_preference(key: str, value: str):
    """设置用户偏好（如偏好领域、关键词）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO user_preferences (pref_key, pref_value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(pref_key) DO UPDATE SET
               pref_value = excluded.pref_value,
               updated_at = excluded.updated_at""",
        (key, value, datetime.now().isoformat())
    )
    if cursor.rowcount == 0:
        cursor.execute("DELETE FROM user_preferences WHERE pref_key = ?", (key,))
        cursor.execute(
            "INSERT INTO user_preferences (pref_key, pref_value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat())
        )
    conn.commit()
    conn.close()


def get_preference(key: str, default: str = "") -> str:
    """获取用户偏好"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pref_value FROM user_preferences WHERE pref_key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["pref_value"] if row else default


def get_all_preferences() -> Dict[str, str]:
    """获取所有用户偏好"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pref_key, pref_value FROM user_preferences")
    rows = cursor.fetchall()
    conn.close()
    return {r["pref_key"]: r["pref_value"] for r in rows}


# ==================== 用户画像分析 ====================

def get_user_profile() -> Dict:
    """分析用户画像（基于浏览历史、收藏、评分）"""
    conn = get_connection()
    cursor = conn.cursor()

    profile = {
        "viewed_papers": 0,
        "favorited_papers": 0,
        "rated_papers": 0,
        "avg_user_rating": 0,
        "top_fields": [],
        "top_keywords": [],
        "top_authors": [],
        "preferred_years": [],
    }

    # 浏览历史
    cursor.execute("SELECT COUNT(DISTINCT paper_id) as cnt FROM viewing_history")
    profile["viewed_papers"] = cursor.fetchone()["cnt"]

    # 收藏夹
    cursor.execute("SELECT COUNT(DISTINCT paper_id) as cnt FROM favorites")
    profile["favorited_papers"] = cursor.fetchone()["cnt"]

    # 用户评分
    cursor.execute("SELECT COUNT(*) as cnt, AVG(rating) as avg FROM user_ratings")
    row = cursor.fetchone()
    profile["rated_papers"] = row["cnt"]
    profile["avg_user_rating"] = round(row["avg"], 2) if row["avg"] else 0

    # 基于浏览+收藏的论文提取特征
    cursor.execute("""
        SELECT DISTINCT p.id, p.title, p.fields, p.authors, p.year
        FROM papers p
        LEFT JOIN viewing_history v ON p.id = v.paper_id
        LEFT JOIN favorites f ON p.id = f.paper_id
        LEFT JOIN user_ratings u ON p.id = u.paper_id
        WHERE v.paper_id IS NOT NULL OR f.paper_id IS NOT NULL OR u.paper_id IS NOT NULL
    """)
    papers = cursor.fetchall()

    field_counter = Counter()
    author_counter = Counter()
    year_counter = Counter()
    keyword_counter = Counter()

    import re
    stopwords = {"the", "a", "an", "of", "and", "in", "to", "for", "on", "with",
                 "is", "are", "was", "were", "by", "from", "as", "at", "this",
                 "that", "using", "based", "study", "method", "research"}

    for p in papers:
        try:
            fields = json.loads(p["fields"]) if p["fields"] else []
            for f in fields:
                field_counter[f] += 1
        except:
            pass
        try:
            authors = json.loads(p["authors"]) if p["authors"] else []
            for a in authors:
                author_counter[a] += 1
        except:
            pass
        if p["year"]:
            year_counter[p["year"]] += 1
        title = p["title"] or ""
        words = re.findall(r"[a-zA-Z]+", title.lower())
        for w in words:
            if len(w) > 3 and w not in stopwords:
                keyword_counter[w] += 1

    profile["top_fields"] = field_counter.most_common(10)
    profile["top_authors"] = author_counter.most_common(10)
    profile["preferred_years"] = year_counter.most_common(5)
    profile["top_keywords"] = keyword_counter.most_common(20)

    conn.close()
    return profile


# ==================== 推荐算法 ====================

def _get_viewed_favorited_ids() -> Set[str]:
    """获取用户已浏览/已收藏的论文ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT paper_id FROM viewing_history
        UNION
        SELECT paper_id FROM favorites
    """)
    ids = {row["paper_id"] for row in cursor.fetchall()}
    conn.close()
    return ids


def recommend_by_content(top_n: int = 20) -> List[Dict]:
    """基于内容相似度推荐

    策略: 用户已浏览/收藏的论文的领域+关键词 → 推荐相似论文
    """
    profile = get_user_profile()
    if profile["viewed_papers"] + profile["favorited_papers"] == 0:
        return []

    # 用户偏好的领域和关键词
    user_fields = {f for f, _ in profile["top_fields"]}
    user_keywords = {k for k, _ in profile["top_keywords"]}

    if not user_fields and not user_keywords:
        return []

    excluded_ids = _get_viewed_favorited_ids()

    conn = get_connection()
    cursor = conn.cursor()

    # 加载未浏览过的论文
    placeholders = ",".join(["?"] * len(excluded_ids)) if excluded_ids else "''"
    query = f"""
        SELECT p.id, p.title, p.fields, p.year, p.citations, p.journal,
               r.overall_score, r.rating_level
        FROM papers p
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE p.id NOT IN ({placeholders})
        LIMIT 500
    """
    cursor.execute(query, list(excluded_ids) if excluded_ids else [""])
    candidates = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 计算每篇论文与用户兴趣的匹配度
    scored = []
    for p in candidates:
        try:
            fields = set(json.loads(p["fields"]) if p["fields"] else [])
        except:
            fields = set()

        # 领域匹配（权重高）
        field_match = len(fields & user_fields)
        # 关键词匹配
        import re
        title_words = set(re.findall(r"[a-zA-Z]+", (p["title"] or "").lower()))
        keyword_match = len(title_words & user_keywords)

        # 综合得分
        score = field_match * 3 + keyword_match * 1
        # 加上评级分（归一化）
        rating_score = (p.get("overall_score") or 0) / 100 * 2

        total = score + rating_score
        if total > 0:
            scored.append({
                **p,
                "recommend_score": round(total, 2),
                "match_reason": f"领域匹配{field_match}个 + 关键词匹配{keyword_match}个",
            })

    scored.sort(key=lambda x: -x["recommend_score"])
    return scored[:top_n]


def recommend_by_rating(top_n: int = 20, min_score: float = 50) -> List[Dict]:
    """基于评分推荐 - 高评分论文"""
    excluded_ids = _get_viewed_favorited_ids()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               r.overall_score, r.rating_level
        FROM papers p
        JOIN ratings r ON p.id = r.paper_id
        WHERE r.overall_score >= ?
    """
    params = [min_score]
    if excluded_ids:
        placeholders = ",".join(["?"] * len(excluded_ids))
        query += f" AND p.id NOT IN ({placeholders})"
        params.extend(excluded_ids)
    query += " ORDER BY r.overall_score DESC LIMIT ?"
    params.append(top_n)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["recommend_score"] = r.get("overall_score", 0)
        r["match_reason"] = f"高评分 [{r.get('rating_level', '?')}]"
    return rows


def recommend_by_trending(top_n: int = 20) -> List[Dict]:
    """基于热度推荐 - 高引用+高评分"""
    excluded_ids = _get_viewed_favorited_ids()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               r.overall_score, r.rating_level
        FROM papers p
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE p.citations > 0
    """
    params = []
    if excluded_ids:
        placeholders = ",".join(["?"] * len(excluded_ids))
        query += f" AND p.id NOT IN ({placeholders})"
        params.extend(excluded_ids)
    query += " ORDER BY p.citations DESC LIMIT ?"
    params.append(top_n * 3)  # 多取一些再筛选

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 计算热度得分 = log(引用+1) + 评分/10
    import math
    for r in rows:
        citations = r.get("citations", 0) or 0
        score = r.get("overall_score") or 0
        trending = math.log10(citations + 1) * 10 + score / 10
        r["recommend_score"] = round(trending, 2)
        r["match_reason"] = f"高引用({citations})+评分({score:.1f})"

    rows.sort(key=lambda x: -x["recommend_score"])
    return rows[:top_n]


def recommend_by_recent(top_n: int = 20, days: int = 365) -> List[Dict]:
    """基于时间推荐 - 最近添加的高质量论文"""
    excluded_ids = _get_viewed_favorited_ids()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               p.created_at, r.overall_score, r.rating_level
        FROM papers p
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE p.created_at >= datetime('now', ?)
    """
    params = [f"-{days} days"]
    if excluded_ids:
        placeholders = ",".join(["?"] * len(excluded_ids))
        query += f" AND p.id NOT IN ({placeholders})"
        params.extend(excluded_ids)
    query += " ORDER BY p.created_at DESC, r.overall_score DESC LIMIT ?"
    params.append(top_n)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["recommend_score"] = r.get("overall_score") or 0
        r["match_reason"] = "最新导入"
    return rows


def recommend_by_field(field: str, top_n: int = 20) -> List[Dict]:
    """基于指定领域推荐"""
    excluded_ids = _get_viewed_favorited_ids()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               r.overall_score, r.rating_level
        FROM papers p
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE p.fields LIKE ?
    """
    params = [f'%"{field}"%']
    if excluded_ids:
        placeholders = ",".join(["?"] * len(excluded_ids))
        query += f" AND p.id NOT IN ({placeholders})"
        params.extend(excluded_ids)
    query += " ORDER BY r.overall_score DESC LIMIT ?"
    params.append(top_n)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["recommend_score"] = r.get("overall_score") or 0
        r["match_reason"] = f"领域: {field}"
    return rows


def recommend_hybrid(top_n: int = 20) -> List[Dict]:
    """混合推荐 - 综合多种策略"""
    # 获取各策略推荐
    by_content = recommend_by_content(top_n=top_n)
    by_rating = recommend_by_rating(top_n=top_n)
    by_trending = recommend_by_trending(top_n=top_n)
    by_recent = recommend_by_recent(top_n=top_n // 2)

    # 合并去重，取最高分
    paper_map = {}
    for recs, weight in [
        (by_content, 1.5),    # 内容匹配权重最高
        (by_rating, 1.0),
        (by_trending, 0.8),
        (by_recent, 0.6),
    ]:
        for r in recs:
            pid = r["id"]
            if pid not in paper_map:
                paper_map[pid] = {**r, "sources": []}
            paper_map[pid]["sources"].append({
                "score": r["recommend_score"],
                "reason": r["match_reason"],
                "weight": weight,
            })

    # 综合得分 = 各来源得分加权平均
    for p in paper_map.values():
        if p["sources"]:
            total_weight = sum(s["weight"] for s in p["sources"])
            weighted_score = sum(s["score"] * s["weight"] for s in p["sources"]) / total_weight
            p["recommend_score"] = round(weighted_score, 2)
            p["match_reason"] = " | ".join(s["reason"] for s in p["sources"])
        else:
            p["recommend_score"] = 0
            p["match_reason"] = ""

    sorted_papers = sorted(paper_map.values(), key=lambda x: -x["recommend_score"])
    return sorted_papers[:top_n]


def _normalize_paper(p: Dict) -> Dict:
    """把从数据库读出的 JSON 字符串字段解析为数组，避免前端误用字符串的 slice/join"""
    for key in ("authors", "fields", "ref_ids", "tags"):
        v = p.get(key)
        if isinstance(v, str):
            try:
                p[key] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                p[key] = []
        elif v is None:
            p[key] = []
        if not isinstance(p[key], list):
            p[key] = []
    return p


def get_recommendations(strategy: str = "hybrid", top_n: int = 20, **kwargs) -> List[Dict]:
    """统一推荐入口"""
    if strategy == "content":
        recs = recommend_by_content(top_n)
    elif strategy == "rating":
        recs = recommend_by_rating(top_n, kwargs.get("min_score", 50))
    elif strategy == "trending":
        recs = recommend_by_trending(top_n)
    elif strategy == "recent":
        recs = recommend_by_recent(top_n, kwargs.get("days", 365))
    elif strategy == "field":
        recs = recommend_by_field(kwargs.get("field", ""), top_n)
    elif strategy == "hybrid":
        recs = recommend_hybrid(top_n)
    else:
        recs = recommend_hybrid(top_n)
    # 统一规范化所有论文的 JSON 字段
    return [_normalize_paper(p) for p in recs]


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    print("=" * 60)
    print("  推荐引擎测试")
    print("=" * 60)

    profile = get_user_profile()
    print(f"\n用户画像:")
    print(f"  浏览论文: {profile['viewed_papers']}")
    print(f"  收藏论文: {profile['favorited_papers']}")
    print(f"  评分论文: {profile['rated_papers']}")
    print(f"  Top领域: {profile['top_fields'][:3]}")

    print(f"\n混合推荐 Top 5:")
    recs = get_recommendations("hybrid", top_n=5)
    for i, r in enumerate(recs, 1):
        print(f"  {i}. [{r.get('rating_level', '?')}] {r['title'][:50]}")
        print(f"     得分: {r['recommend_score']} | {r['match_reason']}")
