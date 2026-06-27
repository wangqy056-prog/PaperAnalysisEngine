"""Paper Analysis Engine - SQLite Database Layer

设计原则：
1. MVP 阶段用 SQLite，零配置、单文件、可随时迁移到 PostgreSQL
2. 图谱关系先不引入 Neo4j，用 SQL 自引用+JSON 字段实现轻量图谱
3. 所有时间字段用 ISO 8601 字符串（SQLite 无原生 DATE 类型）
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

from engine.config import config


class PaperDB:
    """论文数据库管理（SQLite）"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init_db(self):
        """初始化表结构"""
        cursor = self.conn.cursor()

        # === 论文表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            doi TEXT UNIQUE,
            title TEXT NOT NULL,
            abstract TEXT,
            authors JSON,              -- [{"name":"...","affiliation":"..."}]
            journal TEXT,
            year INTEGER,
            citations INTEGER DEFAULT 0,
            reference_count INTEGER DEFAULT 0,
            url TEXT,
            pdf_url TEXT,
            field TEXT,                 -- 主领域
            subfield TEXT,              -- 子领域
            source TEXT,                -- 数据来源: semantic_scholar/openalex/arxiv
            source_id TEXT,             -- 来源ID
            fetched_at TEXT,            -- 数据抓取时间
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # === 作者表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            affiliation TEXT,
            h_index INTEGER,
            total_citations INTEGER,
            research_interests JSON
        )
        """)

        # === 论文-作者关联表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_authors (
            paper_id TEXT NOT NULL,
            author_id TEXT NOT NULL,
            author_order INTEGER,       -- 第几作者
            PRIMARY KEY (paper_id, author_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id),
            FOREIGN KEY (author_id) REFERENCES authors(id)
        )
        """)

        # === 引用关系表（轻量图谱边） ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            citing_paper_id TEXT NOT NULL,    -- 引用的论文
            cited_paper_id TEXT NOT NULL,     -- 被引用的论文
            relationship TEXT DEFAULT 'cites',
            PRIMARY KEY (citing_paper_id, cited_paper_id),
            FOREIGN KEY (citing_paper_id) REFERENCES papers(id),
            FOREIGN KEY (cited_paper_id) REFERENCES papers(id)
        )
        """)

        # === 评级表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL UNIQUE,
            academic_impact REAL NOT NULL DEFAULT 0,
            commercial_potential REAL NOT NULL DEFAULT 0,
            innovation_index REAL NOT NULL DEFAULT 0,
            reproducibility REAL NOT NULL DEFAULT 0,
            combo_value REAL NOT NULL DEFAULT 0,
            overall_score REAL NOT NULL DEFAULT 0,
            grade TEXT NOT NULL DEFAULT 'D',
            -- 各维度细分（JSON，便于调试）
            dimension_details JSON,
            -- 时间衰减调整值
            decay_adjustment REAL DEFAULT 0,
            -- 评级快照
            rated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
        """)

        # === 标签表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT,
            weight REAL DEFAULT 1.0,
            description TEXT
        )
        """)

        # === 论文-标签关联表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_tags (
            paper_id TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,    -- AI标签置信度
            source TEXT DEFAULT 'ai',        -- ai/manual/api
            PRIMARY KEY (paper_id, tag_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        )
        """)

        # === 组合分析表 ===
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS combos (
            id TEXT PRIMARY KEY,
            paper_ids JSON NOT NULL,
            synergy_score REAL DEFAULT 0,
            combo_value REAL DEFAULT 0,
            description TEXT,
            use_case TEXT,
            commercial_timeline TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        self.conn.commit()

    # ==================== CRUD 操作 ====================

    def insert_paper(self, paper: Dict[str, Any]) -> str:
        """插入或更新论文"""
        paper_id = paper.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
        INSERT OR REPLACE INTO papers
            (id, doi, title, abstract, authors, journal, year, citations,
             reference_count, url, pdf_url, field, subfield, source, source_id,
             fetched_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            paper.get("doi"),
            paper.get("title", "Untitled"),
            paper.get("abstract", ""),
            json.dumps(paper.get("authors", [])),
            paper.get("journal"),
            paper.get("year"),
            paper.get("citations", 0),
            paper.get("reference_count", 0),
            paper.get("url"),
            paper.get("pdf_url"),
            paper.get("field"),
            paper.get("subfield"),
            paper.get("source", "unknown"),
            paper.get("source_id"),
            now,
            now,
        ))
        self.conn.commit()
        return paper_id

    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """获取论文详情"""
        row = self.conn.execute(
            "SELECT * FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["authors"] = json.loads(data["authors"])
        return data

    def search_papers(self, query: str, limit: int = 20) -> List[Dict]:
        """全文搜索"""
        rows = self.conn.execute(
            """SELECT * FROM papers
               WHERE title LIKE ? OR abstract LIKE ?
               ORDER BY citations DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        ).fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["authors"] = json.loads(data["authors"])
            results.append(data)
        return results

    def get_papers_by_field(self, field: str, limit: int = 50) -> List[Dict]:
        """按领域查询"""
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE field = ? ORDER BY citations DESC LIMIT ?",
            (field, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ==================== 评级相关 ====================

    def save_rating(self, rating: Dict[str, Any]):
        """保存评级结果"""
        rating_id = rating.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
        INSERT OR REPLACE INTO ratings
            (id, paper_id, academic_impact, commercial_potential,
             innovation_index, reproducibility, combo_value,
             overall_score, grade, dimension_details, decay_adjustment, rated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rating_id, rating["paper_id"],
            rating["academic_impact"], rating["commercial_potential"],
            rating["innovation_index"], rating["reproducibility"],
            rating["combo_value"], rating["overall_score"],
            rating["grade"],
            json.dumps(rating.get("dimension_details", {})),
            rating.get("decay_adjustment", 0),
            now,
        ))
        self.conn.commit()

    def get_paper_rating(self, paper_id: str) -> Optional[Dict]:
        """获取论文评级"""
        row = self.conn.execute(
            "SELECT * FROM ratings WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["dimension_details"] = json.loads(data.get("dimension_details", "{}"))
        return data

    def get_top_papers(self, limit: int = 20) -> List[Dict]:
        """获取评分最高的论文"""
        rows = self.conn.execute("""
        SELECT p.title, p.year, p.citations, r.*
        FROM ratings r JOIN papers p ON r.paper_id = p.id
        ORDER BY r.overall_score DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()


# 单例
db = PaperDB()
