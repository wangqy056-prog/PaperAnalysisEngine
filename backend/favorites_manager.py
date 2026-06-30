"""收藏夹管理模块

功能:
1. 创建/删除收藏夹分组
2. 收藏/取消收藏论文
3. 收藏夹列表查看
4. 收藏夹内论文搜索
5. 笔记管理
6. 收藏夹导入导出
"""

import json
from datetime import datetime
from typing import List, Dict, Optional
from db import get_connection


# ==================== 收藏夹分组 ====================

def create_collection(name: str, description: str = "", color: str = "#4e79a7") -> int:
    """创建收藏夹分组，返回分组ID"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO collections (name, description, color) VALUES (?, ?, ?)",
            (name, description, color)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"[ERROR] 创建收藏夹失败: {e}")
        return -1
    finally:
        conn.close()


def delete_collection(collection_id: int) -> bool:
    """删除收藏夹分组（连同内部收藏）"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM favorites WHERE collection_id = ?", (collection_id,))
        cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] 删除收藏夹失败: {e}")
        return False
    finally:
        conn.close()


def list_collections() -> List[Dict]:
    """列出所有收藏夹分组（含论文数）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.description, c.color, c.created_at,
               COUNT(f.paper_id) as paper_count
        FROM collections c
        LEFT JOIN favorites f ON c.id = f.collection_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_collection(collection_id: int) -> Optional[Dict]:
    """获取收藏夹分组详情"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_collection(collection_id: int, name: str = None, description: str = None,
                       color: str = None) -> bool:
    """更新收藏夹分组信息"""
    conn = get_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if color is not None:
        updates.append("color = ?")
        params.append(color)
    if not updates:
        return False
    params.append(collection_id)
    try:
        cursor.execute(f"UPDATE collections SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] 更新收藏夹失败: {e}")
        return False
    finally:
        conn.close()


# ==================== 收藏/取消收藏 ====================

def add_to_collection(collection_id: int, paper_id: str, notes: str = "") -> bool:
    """收藏论文到分组"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO favorites (collection_id, paper_id, notes) VALUES (?, ?, ?)",
            (collection_id, paper_id, notes)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] 收藏失败: {e}")
        return False
    finally:
        conn.close()


def remove_from_collection(collection_id: int, paper_id: str) -> bool:
    """从分组移除论文"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM favorites WHERE collection_id = ? AND paper_id = ?",
            (collection_id, paper_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] 移除失败: {e}")
        return False
    finally:
        conn.close()


def is_favorited(paper_id: str, collection_id: int = None) -> bool:
    """检查论文是否已收藏"""
    conn = get_connection()
    cursor = conn.cursor()
    if collection_id:
        cursor.execute(
            "SELECT 1 FROM favorites WHERE paper_id = ? AND collection_id = ?",
            (paper_id, collection_id)
        )
    else:
        cursor.execute("SELECT 1 FROM favorites WHERE paper_id = ?", (paper_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_paper_collections(paper_id: str) -> List[Dict]:
    """获取论文所在的收藏夹列表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.color, f.added_at, f.notes
        FROM collections c
        JOIN favorites f ON c.id = f.collection_id
        WHERE f.paper_id = ?
        ORDER BY f.added_at DESC
    """, (paper_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ==================== 收藏夹内容查询 ====================

def list_papers_in_collection(collection_id: int, limit: int = 100,
                                order_by: str = "added_at") -> List[Dict]:
    """列出收藏夹中的论文"""
    valid_orders = {"added_at": "f.added_at DESC", "title": "p.title",
                     "year": "p.year DESC", "citations": "p.citations DESC",
                     "score": "r.overall_score DESC"}
    order_clause = valid_orders.get(order_by, "f.added_at DESC")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               p.abstract, p.fields, p.url, p.pdf_url,
               f.added_at, f.notes,
               r.overall_score, r.rating_level
        FROM papers p
        JOIN favorites f ON p.id = f.paper_id
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE f.collection_id = ?
        GROUP BY p.id
        ORDER BY {order_clause}
        LIMIT ?
    """, (collection_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 解析JSON字段
    for r in rows:
        try:
            r["authors"] = json.loads(r.get("authors") or "[]")
        except (json.JSONDecodeError, TypeError):
            r["authors"] = []
        try:
            r["fields"] = json.loads(r.get("fields") or "[]")
        except (json.JSONDecodeError, TypeError):
            r["fields"] = []

    return rows


def search_in_collection(collection_id: int, query: str, limit: int = 50) -> List[Dict]:
    """在收藏夹内搜索论文"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
               f.added_at, f.notes,
               r.overall_score, r.rating_level
        FROM papers p
        JOIN favorites f ON p.id = f.paper_id
        LEFT JOIN ratings r ON p.id = r.paper_id
        WHERE f.collection_id = ? AND (p.title LIKE ? OR p.abstract LIKE ?)
        ORDER BY f.added_at DESC
        LIMIT ?
    """, (collection_id, f"%{query}%", f"%{query}%", limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def update_notes(collection_id: int, paper_id: str, notes: str) -> bool:
    """更新收藏论文的笔记"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE favorites SET notes = ? WHERE collection_id = ? AND paper_id = ?",
            (notes, collection_id, paper_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] 更新笔记失败: {e}")
        return False
    finally:
        conn.close()


# ==================== 导入导出 ====================

def export_collection(collection_id: int) -> Dict:
    """导出收藏夹为JSON"""
    collection = get_collection(collection_id)
    if not collection:
        return None

    papers = list_papers_in_collection(collection_id, limit=9999)

    return {
        "collection": collection,
        "paper_count": len(papers),
        "papers": [{
            "id": p["id"],
            "title": p["title"],
            "year": p.get("year"),
            "journal": p.get("journal"),
            "doi": p.get("doi"),
            "url": p.get("url"),
            "notes": p.get("notes", ""),
            "rating_level": p.get("rating_level"),
            "overall_score": p.get("overall_score"),
        } for p in papers],
        "exported_at": datetime.now().isoformat(),
    }


# ==================== 默认收藏夹初始化 ====================

def ensure_default_collections():
    """确保默认收藏夹存在"""
    defaults = [
        ("⭐ 收藏", "默认收藏夹", "#ffaa00"),
        ("📖 待读", "待读论文列表", "#4e79a7"),
        ("💡 灵感", "有启发的论文", "#59a14f"),
        ("📚 参考", "参考文献", "#e15759"),
    ]
    existing = {c["name"] for c in list_collections()}
    for name, desc, color in defaults:
        if name not in existing:
            create_collection(name, desc, color)


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    ensure_default_collections()
    print("收藏夹列表:")
    for c in list_collections():
        print(f"  [{c['id']}] {c['name']} - {c['paper_count']}篇")
