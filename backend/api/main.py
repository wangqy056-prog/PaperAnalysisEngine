"""FastAPI 后端 API - 论文分析引擎

包装现有后端函数，提供 RESTful API 供 Vue 前端调用。
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

# 加载 .env 文件中的环境变量（必须在导入 llm_analyzer 之前）
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"[OK] 已加载环境变量: {env_path}")
    else:
        print(f"[WARN] .env 文件不存在: {env_path}")
except ImportError:
    print("[WARN] python-dotenv 未安装，环境变量不会从 .env 文件读取")

# 确保能导入 backend 模块
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 导入后端模块
from db import (
    init_db, search_papers, get_paper, get_all_ratings, get_stats,
    insert_paper, insert_rating, get_connection
)
from paper_fetcher import PaperFetcher
from rating_engine import rate_paper, generate_tags, predict_commercialization
from linkresearcher_spider import fetch_latest_papers as fetch_lr_papers
from knowledge_graph import build_graph, get_graph_summary
from scorecard_generator import generate_scorecard

# ==================== Pydantic 模型 ====================

class PaperImport(BaseModel):
    title: str
    abstract: Optional[str] = ""
    authors: Optional[List[str]] = []
    journal: Optional[str] = ""
    year: Optional[int] = None
    citations: Optional[int] = 0
    doi: Optional[str] = ""
    url: Optional[str] = ""
    pdf_url: Optional[str] = ""
    fields: Optional[List[str]] = []
    source: Optional[str] = "manual"


class SearchQuery(BaseModel):
    query: str
    limit: int = 20
    sources: Optional[List[str]] = ["oa", "arxiv"]


class BatchImportTitles(BaseModel):
    titles: List[str]
    source: str = "oa"


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class FavoriteAdd(BaseModel):
    paper_id: str
    notes: Optional[str] = ""


class NotesUpdate(BaseModel):
    notes: str


class UserPreference(BaseModel):
    field: Optional[str] = None
    keywords: Optional[List[str]] = None
    value: str


class UserRating(BaseModel):
    paper_id: str
    rating: int  # 1-5
    comment: Optional[str] = ""


class PushSubscription(BaseModel):
    name: str
    method: str  # file/webhook/wechat/email
    config: Dict[str, Any]
    strategy: str = "trending"
    enabled: bool = True


class ReportRequest(BaseModel):
    report_type: str  # stats/paper/collection/search/recommendations
    format: str = "markdown"  # markdown/html
    paper_id: Optional[str] = None
    collection_id: Optional[int] = None
    query: Optional[str] = None


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="论文分析引擎 API",
    description="论文搜索、评级、AI 分析、知识图谱、推荐、收藏夹等",
    version="0.4.0",
)

# CORS 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000",
                   "http://127.0.0.1:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化
init_db()
fetcher = PaperFetcher()


# ==================== 0. 根路径 ====================

@app.get("/")
def root():
    """根路径：返回服务信息"""
    return {
        "service": "论文分析引擎 API",
        "version": "0.4.0",
        "docs": "/docs",
        "endpoints": {
            "stats": "/api/stats",
            "ratings": "/api/ratings",
            "search": "/api/papers/search",
            "paper_detail": "/api/papers/{paper_id}",
            "linkresearcher": "/api/linkresearcher",
            "knowledge_graph": "/api/knowledge-graph",
            "ai_provider": "/api/ai/provider",
        },
    }


# ==================== 1. 统计 / 仪表盘 ====================

@app.get("/api/stats")
def get_dashboard_stats():
    """获取仪表盘统计数据"""
    stats = get_stats()
    return stats


@app.get("/api/ratings")
def get_ratings(limit: int = Query(100, ge=1, le=9999)):
    """获取评级列表（按评分降序）"""
    ratings = get_all_ratings(limit=limit)
    return ratings


# ==================== 2. 论文搜索 ====================

@app.get("/api/papers/search")
def search_local_papers(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, ge=1, le=200),
    year_from: int = Query(1990, ge=1900, le=2026),
    min_citations: int = Query(0, ge=0),
):
    """本地数据库搜索论文"""
    results = search_papers(q, limit=limit, year_from=year_from, min_citations=min_citations)
    return results


@app.post("/api/papers/search-online")
def search_online_papers(req: SearchQuery):
    """在线搜索论文（OpenAlex + arXiv）"""
    results = fetcher.search(req.query, limit=req.limit, sources=req.sources)
    return results


@app.get("/api/papers/{paper_id}")
def get_paper_detail(paper_id: str):
    """获取论文详情（含商业化预测）"""
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    # 附加商业化预测（实时计算，不入库）
    try:
        from rating_engine import predict_commercialization
        pred = predict_commercialization(paper)
        trl = pred.get("trl", 0)
        # 字段映射：前端用 commercial_prediction（文本）+ commercial_score（0-1）
        paper["commercial_score"] = round(trl / 9.0, 2)  # TRL 1-9 归一化到 0-1
        factors_text = "；".join(pred.get("factors", [])) or "无明显加速因素"
        paper["commercial_prediction"] = (
            f"技术成熟度 TRL {trl}/9 级 | 预计商业化时间：{pred.get('base_time', '未知')} | "
            f"置信度：{pred.get('confidence', '中')} | {factors_text}"
        )
    except Exception as e:
        paper["commercial_score"] = 0
        paper["commercial_prediction"] = None

    return paper


@app.get("/api/papers/{paper_id}/scorecard")
def get_paper_scorecard(paper_id: str):
    """生成论文评分卡 PNG 图片（五维雷达图，可分享）

    返回 image/png 二进制数据，前端用 <img> 或下载链接访问
    """
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    rating = paper.get("rating")
    if not rating:
        raise HTTPException(status_code=404, detail="论文暂无评级数据，无法生成评分卡")

    try:
        img_bytes = generate_scorecard(paper, rating)
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分卡生成失败：{str(e)}")


@app.get("/api/papers/{paper_id}/patents")
def get_paper_patents(paper_id: str):
    """获取论文的专利引用列表"""
    from db import get_connection
    conn = get_connection()
    rows = conn.execute("""
        SELECT patent_id, assignee, publication_date, country_code, npl_text
        FROM patent_citations
        WHERE paper_id = ?
        ORDER BY publication_date DESC
    """, (paper_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/paper/by-doi/{doi:path}/rating")
def get_rating_by_doi(doi: str):
    """通过 DOI 查询论文评级（Zotero 插件用）

    Zotero 保存论文时自动调用此端点，返回评级信息用于标注彩色徽章
    如果论文不在数据库中，返回 404（提示用户先在 PAE 搜索导入）
    """
    doi = doi.strip().lower()
    if not doi:
        raise HTTPException(status_code=400, detail="DOI 不能为空")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # DOI 大小写不敏感查询
        cursor.execute(
            "SELECT id FROM papers WHERE LOWER(doi) = ?",
            (doi,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Paper not in database. Search for it first."
        )

    paper_id = row["id"]
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    rating = paper.get("rating")
    if not rating:
        raise HTTPException(status_code=404, detail="论文暂无评级数据")

    # 返回精简的评级信息（Zotero 插件用）
    return {
        "paper_id": paper_id,
        "title": paper.get("title"),
        "doi": paper.get("doi"),
        "year": paper.get("year"),
        "grade": rating.get("rating_level"),  # S/A/B/C/D
        "overall_score": rating.get("overall_score"),
        "academic_impact": rating.get("academic_impact"),
        "commercial_potential": rating.get("commercial_potential"),
        "innovation_index": rating.get("innovation_index"),
        "reproducibility": rating.get("reproducibility"),
        "combo_value": rating.get("combo_value"),
    }



@app.post("/api/papers/import")
def import_paper(paper: PaperImport):
    """导入单篇论文并自动评级"""
    paper_dict = paper.dict()
    # 生成 ID
    import hashlib
    if not paper_dict.get("id"):
        paper_dict["id"] = hashlib.md5(paper_dict["title"].encode()).hexdigest()[:16]

    success = insert_paper(paper_dict)
    if not success:
        return {"success": False, "message": "论文已存在或导入失败"}

    rating = rate_paper(paper_dict)
    insert_rating(paper_dict["id"], rating)

    # 生成标签
    tags = generate_tags(paper_dict)
    _save_tags(paper_dict["id"], tags)

    return {
        "success": True,
        "paper_id": paper_dict["id"],
        "rating": rating,
        "tags": tags,
    }


@app.post("/api/papers/batch-import-titles")
def batch_import_by_titles(req: BatchImportTitles):
    """通过标题列表批量导入"""
    imported = []
    failed = []
    for title in req.titles:
        try:
            results = fetcher.search(title, limit=1, sources=[req.source])
            if results:
                paper_data = results[0]
                if not paper_data.get("id"):
                    import hashlib
                    paper_data["id"] = hashlib.md5(paper_data["title"].encode()).hexdigest()[:16]
                success = insert_paper(paper_data)
                if success:
                    rating = rate_paper(paper_data)
                    insert_rating(paper_data["id"], rating)
                    tags = generate_tags(paper_data)
                    _save_tags(paper_data["id"], tags)
                    imported.append(paper_data["id"])
                else:
                    failed.append(title)
            else:
                failed.append(title)
        except Exception as e:
            failed.append(f"{title}: {str(e)}")

    return {"imported": imported, "failed": failed, "total": len(req.titles)}


@app.delete("/api/papers/{paper_id}")
def delete_paper(paper_id: str):
    """删除论文"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
    cursor.execute("DELETE FROM ratings WHERE paper_id = ?", (paper_id,))
    cursor.execute("DELETE FROM favorites WHERE paper_id = ?", (paper_id,))
    cursor.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ==================== 3. 领研网 ====================

@app.get("/api/linkresearcher")
def get_linkresearcher_papers(
    pages: int = Query(1, ge=1, le=5),
    refresh: bool = Query(False, description="强制清空缓存重新抓取"),
):
    """抓取领研网最新论文

    - pages: 抓取页数（每页 20 篇，最多 5 页 = 100 篇）
    - refresh=true: 清空缓存重新抓取（领研网有 30 分钟缓存避免频繁启动浏览器）
    """
    if refresh:
        from linkresearcher_spider import _clear_cache
        _clear_cache()
    papers = fetch_lr_papers(pages=pages)
    return papers


@app.post("/api/linkresearcher/import")
def import_from_linkresearcher(paper_title: str = Body(..., embed=True)):
    """通过标题从 OpenAlex 搜索并导入"""
    search_title = paper_title.split("｜")[0].split("|")[0].strip()
    results = fetcher.search(search_title, limit=3, sources=["oa"])
    if not results:
        return {"success": False, "message": "未找到匹配论文"}

    paper_data = results[0]
    import hashlib
    if not paper_data.get("id"):
        paper_data["id"] = hashlib.md5(paper_data["title"].encode()).hexdigest()[:16]

    success = insert_paper(paper_data)
    if success:
        rating = rate_paper(paper_data)
        insert_rating(paper_data["id"], rating)
        tags = generate_tags(paper_data)
        _save_tags(paper_data["id"], tags)
        return {"success": True, "paper_id": paper_data["id"], "rating": rating}
    return {"success": False, "message": "论文已存在"}


# ==================== 4. 多主题导入 ====================

@app.get("/api/batch-import/topics")
def get_topic_library():
    """获取主题库"""
    from batch_import_topics import TOPIC_LIBRARY
    return TOPIC_LIBRARY


@app.post("/api/batch-import/run")
def run_batch_import(
    categories: List[str] = Body(...),
    per_topic: int = Body(20, embed=True),
    sources: List[str] = Body(["oa"], embed=True),
):
    """执行多主题批量导入"""
    from batch_import_topics import batch_import
    result = batch_import(categories=categories, per_topic=per_topic, sources=sources)
    return result


# ==================== 5. 知识图谱 ====================

@app.get("/api/knowledge-graph/{graph_type}")
def get_knowledge_graph(
    graph_type: str,
    limit: int = Query(50, ge=1, le=300),
    threshold: int = Query(1, ge=1, le=20),
):
    """获取知识图谱数据

    graph_type: field/author/keyword/similarity/citation
    返回 {nodes: [...], edges: [...], summary: {...}}
    """
    type_map = {
        # 简短形式
        "field": "领域共现",
        "author": "作者合作",
        "keyword": "关键词共现",
        "similarity": "论文相似",
        "citation": "引用网络",
        # 兼容长形式（前端常用）
        "field_co_occurrence": "领域共现",
        "author_collaboration": "作者合作",
        "keyword_co_occurrence": "关键词共现",
        "paper_similarity": "论文相似",
        "citation_network": "引用网络",
        # 兼容中文
        "领域共现": "领域共现",
        "作者合作": "作者合作",
        "关键词共现": "关键词共现",
        "论文相似": "论文相似",
        "引用网络": "引用网络",
    }
    cn_type = type_map.get(graph_type)
    if not cn_type:
        raise HTTPException(status_code=400, detail=f"未知图谱类型: {graph_type}，支持: {list(type_map.keys())}")

    try:
        G, summary = build_graph(cn_type, top_n=limit, min_cooccurrence=threshold)
        # 转换 networkx 图为前端可用的格式
        nodes = []
        for node_id, data in G.nodes(data=True):
            nodes.append({
                "id": str(node_id),
                "label": data.get("label", str(node_id)),
                "size": data.get("size", data.get("weight", 1)),
                **{k: v for k, v in data.items() if k not in ("label", "size", "weight")},
            })
        edges = []
        for u, v, data in G.edges(data=True):
            edges.append({
                # 同时输出 source/target（语义清晰）和 from/to（vis-network 默认字段）
                "source": str(u),
                "target": str(v),
                "from": str(u),
                "to": str(v),
                "weight": data.get("weight", 1),
                **{k: v for k, v in data.items() if k not in ("source", "target", "from", "to")},
            })
        return {"nodes": nodes, "edges": edges, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/knowledge-graph")
def get_knowledge_graph_summary():
    """获取知识图谱概要"""
    return get_graph_summary()


# ==================== 6. AI 分析 ====================

@app.post("/api/ai/summary")
def ai_summary(paper_id: str = Body(..., embed=True)):
    """AI 生成论文摘要"""
    from llm_analyzer import summarize_paper
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = summarize_paper(paper)
    return {"result": result}


@app.post("/api/ai/translate")
def ai_translate(paper_id: str = Body(..., embed=True)):
    """AI 翻译摘要"""
    from llm_analyzer import translate_abstract
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = translate_abstract(paper)
    return {"result": result}


@app.post("/api/ai/plain-summary")
def ai_plain_summary(paper_id: str = Body(..., embed=True)):
    """AI 通俗解读"""
    from llm_analyzer import plain_language_summary
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = plain_language_summary(paper)
    return {"result": result}


@app.post("/api/ai/assess")
def ai_assess(paper_id: str = Body(..., embed=True)):
    """AI 价值评估"""
    from llm_analyzer import assess_value
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = assess_value(paper)
    return {"result": result}


@app.post("/api/ai/functional")
def ai_functional(paper_id: str = Body(..., embed=True)):
    """AI 功能说明"""
    from llm_analyzer import functional_description
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = functional_description(paper)
    return {"result": result}


@app.post("/api/ai/deep-analysis")
def ai_deep_analysis(paper_id: str = Body(..., embed=True)):
    """AI 综合深度分析"""
    from llm_analyzer import deep_analysis
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = deep_analysis(paper)
    return {"result": result}


@app.post("/api/ai/compare")
def ai_compare_papers(
    paper_id_1: str = Body(..., embed=True),
    paper_id_2: str = Body(..., embed=True),
):
    """AI 对比两篇论文"""
    from llm_analyzer import compare_papers_ai
    paper1 = get_paper(paper_id_1)
    paper2 = get_paper(paper_id_2)
    if not paper1 or not paper2:
        raise HTTPException(status_code=404, detail="论文不存在")
    result = compare_papers_ai(paper1, paper2)
    return {"result": result}


@app.post("/api/ai/switch-provider")
def ai_switch_provider(provider: str = Body(..., embed=True)):
    """切换 LLM 提供商"""
    from llm_analyzer import switch_provider
    if provider not in ["deepseek", "groq", "glm"]:
        raise HTTPException(status_code=400, detail="未知提供商")
    switch_provider(provider)
    return {"success": True, "provider": provider}


@app.get("/api/ai/provider")
def ai_get_provider():
    """获取当前 LLM 提供商"""
    from llm_analyzer import CURRENT_PROVIDER
    return {"provider": CURRENT_PROVIDER}


# ==================== 7. 推荐 ====================

@app.get("/api/recommendations")
def get_recommendations(
    strategy: str = Query("hybrid", description="content/rating/trending/recent/hybrid"),
    limit: int = Query(10, ge=1, le=50),
):
    """获取论文推荐"""
    from recommendation_engine import get_recommendations as get_recs
    recs = get_recs(strategy=strategy, top_n=limit)
    return recs


@app.post("/api/recommendations/view")
def record_viewing(paper_id: str = Body(..., embed=True)):
    """记录用户浏览历史"""
    from recommendation_engine import record_view
    record_view(paper_id)
    return {"success": True}


@app.post("/api/recommendations/rate")
def record_user_rating(req: UserRating):
    """记录用户评分"""
    from recommendation_engine import rate_paper_user
    success = rate_paper_user(req.paper_id, req.rating, req.comment)
    return {"success": success}


@app.get("/api/recommendations/profile")
def get_user_profile():
    """获取用户画像"""
    from recommendation_engine import get_user_profile as get_profile
    return get_profile()


# ==================== 8. 收藏夹 ====================

@app.get("/api/favorites/collections")
def list_collections():
    """列出所有收藏夹"""
    from favorites_manager import list_collections as lc
    return lc()


@app.post("/api/favorites/collections")
def create_collection(req: CollectionCreate):
    """创建收藏夹"""
    from favorites_manager import create_collection as cc
    col_id = cc(req.name, req.description)
    return {"id": col_id}


@app.delete("/api/favorites/collections/{collection_id}")
def delete_collection(collection_id: int):
    """删除收藏夹"""
    from favorites_manager import delete_collection as dc
    success = dc(collection_id)
    return {"success": success}


@app.get("/api/favorites/collections/{collection_id}/papers")
def list_papers_in_collection(
    collection_id: int,
    limit: int = Query(100, ge=1, le=9999),
    order: str = Query("added_at_desc"),
):
    """列出收藏夹中的论文"""
    from favorites_manager import list_papers_in_collection as lpc
    return lpc(collection_id, limit=limit, order=order)


@app.post("/api/favorites/collections/{collection_id}/papers")
def add_to_collection(collection_id: int, req: FavoriteAdd):
    """添加论文到收藏夹"""
    from favorites_manager import add_to_collection as atc
    success = atc(collection_id, req.paper_id, req.notes)
    return {"success": success}


@app.delete("/api/favorites/collections/{collection_id}/papers/{paper_id}")
def remove_from_collection(collection_id: int, paper_id: str):
    """从收藏夹移除论文"""
    from favorites_manager import remove_from_collection as rfc
    success = rfc(collection_id, paper_id)
    return {"success": success}


@app.put("/api/favorites/collections/{collection_id}/papers/{paper_id}/notes")
def update_notes(collection_id: int, paper_id: str, req: NotesUpdate):
    """更新笔记"""
    from favorites_manager import update_notes as un
    success = un(collection_id, paper_id, req.notes)
    return {"success": success}


@app.get("/api/favorites/search")
def search_in_favorites(q: str = Query(...), collection_id: int = Query(1, ge=1)):
    """在收藏夹中搜索"""
    from favorites_manager import search_in_collection as sic
    return sic(collection_id, q)


# ==================== 9. 报告 ====================

@app.post("/api/reports/generate")
def generate_report(req: ReportRequest):
    """生成报告"""
    from report_generator import (
        export_paper_report, export_collection_report,
        export_search_report, export_stats_report,
        export_recommendation_report,
    )
    fmt = "md" if req.format == "markdown" else "html"
    filepath = None
    if req.report_type == "stats":
        filepath = export_stats_report(fmt=fmt)
    elif req.report_type == "paper" and req.paper_id:
        filepath = export_paper_report(req.paper_id, fmt=fmt)
    elif req.report_type == "collection" and req.collection_id:
        filepath = export_collection_report(req.collection_id, fmt=fmt)
    elif req.report_type == "search" and req.query:
        papers = search_papers(req.query, limit=50)
        filepath = export_search_report(req.query, papers, fmt=fmt)
    elif req.report_type == "recommendations":
        from recommendation_engine import get_recommendations as get_recs
        recs = get_recs(strategy="hybrid", top_n=20)
        filepath = export_recommendation_report(recs, fmt=fmt)
    else:
        raise HTTPException(status_code=400, detail="无效的报告类型或缺少参数")
    return {"filepath": filepath, "format": req.format}


# ==================== 10. 推送 ====================

@app.get("/api/push/subscriptions")
def list_push_subscriptions():
    """列出推送订阅"""
    from scheduled_push import list_subscriptions
    return list_subscriptions()


@app.post("/api/push/subscriptions")
def create_push_subscription(req: PushSubscription):
    """创建推送订阅"""
    from scheduled_push import create_subscription
    sub_id = create_subscription(
        name=req.name,
        push_type=req.method,
        config=req.config,
        strategy=req.strategy,
    )
    return {"id": sub_id}


@app.delete("/api/push/subscriptions/{sub_id}")
def delete_push_subscription(sub_id: int):
    """删除推送订阅"""
    from scheduled_push import delete_subscription
    success = delete_subscription(sub_id)
    return {"success": success}


@app.get("/api/push/history")
def list_push_history(limit: int = Query(20, ge=1, le=100)):
    """获取推送历史"""
    from scheduled_push import list_push_history
    return list_push_history(limit=limit)


@app.post("/api/push/test/{sub_id}")
def test_push(sub_id: int):
    """测试推送"""
    from scheduled_push import execute_push
    result = execute_push(sub_id)
    return result


# ==================== 辅助函数 ====================

def _save_tags(paper_id: str, tags: list):
    """保存标签到数据库"""
    conn = get_connection()
    cursor = conn.cursor()
    for tag in tags:
        cursor.execute(
            "INSERT OR IGNORE INTO tags (name, category, description) VALUES (?, ?, ?)",
            (tag["name"], tag["category"], tag.get("description", ""))
        )
        cursor.execute("SELECT id FROM tags WHERE name = ? AND category = ?",
                       (tag["name"], tag["category"]))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id, confidence) VALUES (?, ?, ?)",
                (paper_id, row["id"], tag.get("confidence", 1.0))
            )
    conn.commit()
    conn.close()


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
