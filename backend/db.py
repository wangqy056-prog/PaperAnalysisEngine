"""SQLite 数据库初始化与操作"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime

# 数据库路径：优先从环境变量读取，否则使用默认路径
DB_PATH = Path(os.environ.get("DATABASE_PATH", Path(__file__).parent / "papers.db"))


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    # 论文表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS papers (
        id TEXT PRIMARY KEY,
        doi TEXT UNIQUE,
        title TEXT NOT NULL,
        abstract TEXT,
        authors JSON,
        journal TEXT,
        year INTEGER,
        citations INTEGER DEFAULT 0,
        ref_ids JSON,
        url TEXT,
        pdf_url TEXT,
        fields JSON,
        source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 评级表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id TEXT NOT NULL,
        academic_impact REAL DEFAULT 0,
        commercial_potential REAL DEFAULT 0,
        innovation_index REAL DEFAULT 0,
        reproducibility REAL DEFAULT 0,
        combo_value REAL DEFAULT 50,
        overall_score REAL DEFAULT 0,
        rating_level TEXT DEFAULT 'C',
        analysis_date TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers (id)
    )
    """)

    # 标签表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT
    )
    """)

    # 论文-标签关联表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paper_tags (
        paper_id TEXT NOT NULL,
        tag_id INTEGER NOT NULL,
        confidence REAL DEFAULT 1.0,
        PRIMARY KEY (paper_id, tag_id),
        FOREIGN KEY (paper_id) REFERENCES papers (id),
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )
    """)

    # 查询历史表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        results_count INTEGER DEFAULT 0,
        searched_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 收藏夹分组表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        color TEXT DEFAULT '#4e79a7',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 收藏夹-论文关联表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER NOT NULL,
        paper_id TEXT NOT NULL,
        notes TEXT,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(collection_id, paper_id),
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
    )
    """)

    # 用户偏好表（推荐引擎使用）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pref_key TEXT NOT NULL UNIQUE,
        pref_value TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 浏览历史表（推荐引擎使用）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viewing_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id TEXT NOT NULL UNIQUE,
        viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        view_count INTEGER DEFAULT 1,
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
    )
    """)

    # 用户评分表（对论文打分，推荐引擎使用）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id TEXT NOT NULL UNIQUE,
        rating INTEGER CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        rated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
    )
    """)

    # 推送订阅表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        push_type TEXT NOT NULL,
        config JSON,
        enabled INTEGER DEFAULT 1,
        last_push_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 推送历史表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS push_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        paper_count INTEGER DEFAULT 0,
        paper_ids JSON,
        status TEXT DEFAULT 'success',
        pushed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subscription_id) REFERENCES push_subscriptions(id) ON DELETE CASCADE
    )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_citations ON papers(citations DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_paper ON ratings(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_paper_tags_paper ON paper_tags(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_collection ON favorites(collection_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_paper ON favorites(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_viewing_history_paper ON viewing_history(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_ratings_paper ON user_ratings(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_history_sub ON push_history(subscription_id)")

    conn.commit()
    conn.close()
    print(f"[OK] 数据库已初始化: {DB_PATH}")


# ==================== CRUD 操作 ====================

def insert_paper(paper: dict) -> bool:
    """插入或更新论文，返回是否成功

    查重逻辑：
    1. 先按 id 查（INSERT OR REPLACE 自动处理同 ID 更新）
    2. 再按标题查（避免不同数据源同篇论文重复导入）
       - 标题归一化：去空格 + 转小写后比较
       - 已存在则跳过，返回 False
    """
    conn = get_connection()
    cursor = conn.cursor()

    title = (paper.get("title") or "").strip()
    if not title:
        return False

    # 标题查重：避免不同数据源（OpenAlex/arXiv/领研网）重复导入同一篇论文
    norm_title = title.lower()
    cursor.execute(
        "SELECT id FROM papers WHERE LOWER(TRIM(title)) = ? AND id != ?",
        (norm_title, paper.get("id"))
    )
    if cursor.fetchone():
        # 标题已存在（且不是同一 ID），跳过
        conn.close()
        return False

    try:
        cursor.execute("""
        INSERT OR REPLACE INTO papers
        (id, doi, title, abstract, authors, journal, year, citations, ref_ids, url, pdf_url, fields, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper.get("id"),
            paper.get("doi"),
            paper.get("title"),
            paper.get("abstract"),
            json.dumps(paper.get("authors", []), ensure_ascii=False),
            paper.get("journal"),
            paper.get("year"),
            paper.get("citations", 0),
            json.dumps(paper.get("references", []), ensure_ascii=False),
            paper.get("url"),
            paper.get("pdf_url"),
            json.dumps(paper.get("fields", []), ensure_ascii=False),
            paper.get("source"),
        ))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[ERROR] 插入论文失败: {e}")
        return False
    finally:
        conn.close()


def insert_rating(paper_id: str, ratings: dict):
    """插入评级数据"""
    conn = get_connection()
    cursor = conn.cursor()

    # 计算综合评分
    overall = (
        ratings.get("academic_impact", 0) * 0.30 +
        ratings.get("commercial_potential", 0) * 0.25 +
        ratings.get("innovation_index", 0) * 0.20 +
        ratings.get("reproducibility", 0) * 0.15 +
        ratings.get("combo_value", 50) * 0.10
    )

    # 确定评级等级
    if overall >= 90:
        level = "S"
    elif overall >= 75:
        level = "A"
    elif overall >= 60:
        level = "B"
    elif overall >= 40:
        level = "C"
    else:
        level = "D"

    try:
        # 先删除该论文的旧评级（避免重复累积；ratings 表 paper_id 无 UNIQUE 约束）
        cursor.execute("DELETE FROM ratings WHERE paper_id = ?", (paper_id,))
        cursor.execute("""
        INSERT INTO ratings
        (paper_id, academic_impact, commercial_potential, innovation_index,
         reproducibility, combo_value, overall_score, rating_level, analysis_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            ratings.get("academic_impact", 0),
            ratings.get("commercial_potential", 0),
            ratings.get("innovation_index", 0),
            ratings.get("reproducibility", 0),
            ratings.get("combo_value", 50),
            overall,
            level,
            datetime.now().isoformat(),
        ))
        conn.commit()
        return overall
    except sqlite3.Error as e:
        print(f"[ERROR] 插入评级失败: {e}")
        return 0
    finally:
        conn.close()


def search_papers(query: str, limit: int = 20, year_from: int = None, year_to: int = None, min_citations: int = 0) -> list:
    """搜索论文"""
    conn = get_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM papers WHERE title LIKE ?"
    params = [f"%{query}%"]

    if year_from:
        sql += " AND year >= ?"
        params.append(year_from)
    if year_to:
        sql += " AND year <= ?"
        params.append(year_to)
    if min_citations:
        sql += " AND citations >= ?"
        params.append(min_citations)

    sql += " ORDER BY citations DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    papers = []
    for row in rows:
        p = dict(row)
        # 解析 JSON 字段为列表，避免前端误把字符串当数组用
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
        papers.append(p)
    return papers


def get_paper(paper_id: str) -> dict:
    """获取单篇论文详情（含评级）"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    paper = cursor.fetchone()

    if paper:
        paper = dict(paper)
        cursor.execute("SELECT * FROM ratings WHERE paper_id = ?", (paper_id,))
        rating = cursor.fetchone()
        paper["rating"] = dict(rating) if rating else None

        # 解析JSON字段
        paper["authors"] = json.loads(paper.get("authors", "[]"))
        paper["fields"] = json.loads(paper.get("fields", "[]"))

    conn.close()
    return paper


def get_all_ratings(limit: int = 100, order_by: str = "overall_score") -> list:
    """获取所有评级数据"""
    conn = get_connection()
    cursor = conn.cursor()

    valid_columns = {"overall_score", "academic_impact", "commercial_potential", 
                      "innovation_index", "reproducibility", "combo_value", "analysis_date"}
    order_col = order_by if order_by in valid_columns else "overall_score"

    cursor.execute(f"""
    SELECT p.id, p.title, p.year, p.citations, p.journal,
           MAX(r.overall_score) AS overall_score,
           MAX(r.rating_level) AS rating_level,
           MAX(r.rating_level) AS grade,
           MAX(r.academic_impact) AS academic_impact,
           MAX(r.commercial_potential) AS commercial_potential,
           MAX(r.innovation_index) AS innovation_index,
           MAX(r.reproducibility) AS reproducibility,
           MAX(r.combo_value) AS combo_value
    FROM papers p
    JOIN ratings r ON p.id = r.paper_id
    GROUP BY p.id
    ORDER BY {order_col} DESC
    LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    """获取数据库统计信息"""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}
    cursor.execute("SELECT COUNT(*) as count FROM papers")
    stats["total_papers"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM ratings")
    stats["total_ratings"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM tags")
    stats["total_tags"] = cursor.fetchone()["count"]

    cursor.execute("""
    SELECT 
        AVG(r.overall_score) as avg_score,
        MAX(r.overall_score) as max_score,
        MIN(r.overall_score) as min_score
    FROM ratings r
    """)
    row = cursor.fetchone()
    stats["avg_score"] = round(row["avg_score"], 1) if row["avg_score"] else 0
    stats["max_score"] = round(row["max_score"], 1) if row["max_score"] else 0
    stats["min_score"] = round(row["min_score"], 1) if row["min_score"] else 0

    cursor.execute("""
    SELECT rating_level, COUNT(*) as count 
    FROM ratings 
    GROUP BY rating_level 
    ORDER BY rating_level
    """)
    stats["level_distribution"] = {row["rating_level"]: row["count"] for row in cursor.fetchall()}

    conn.close()
    return stats


if __name__ == "__main__":
    init_db()
    stats = get_stats()
    print(f"\n数据库统计:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
