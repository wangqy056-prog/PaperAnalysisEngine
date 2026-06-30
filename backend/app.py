"""Paper Analysis Engine - Streamlit Web UI

功能页面:
1. 仪表盘 - 数据概览、统计图表
2. 搜索论文 - 关键词搜索、筛选、导入
3. 论文详情 - 评级、标签、商业化预测
4. 排行榜 - 评分排名、维度对比
5. 领研网 - 最新论文抓取、一键导入
6. 批量导入 - 粘贴标题列表批量导入
"""

import sys
import os
import time
import json
import sqlite3
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import (
    init_db, search_papers, get_paper, get_all_ratings,
    get_stats, insert_paper, insert_rating, get_connection
)
from paper_fetcher import PaperFetcher
from rating_engine import rate_paper, generate_tags, predict_commercialization
from linkresearcher_spider import fetch_latest_papers as fetch_lr_papers

# ==================== 页面配置 ====================

st.set_page_config(
    page_title="论文分析引擎",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化数据库
init_db()

# 初始化 session state
if "fetcher" not in st.session_state:
    st.session_state.fetcher = PaperFetcher()


# ==================== 侧边栏 ====================

st.sidebar.title("📊 论文分析引擎")
st.sidebar.divider()

page = st.sidebar.radio(
    "功能导航",
    ["📋 仪表盘", "🔍 搜索论文", "📊 排行榜", "📰 领研网", "📥 批量导入", "🚀 多主题导入", "🕸 知识图谱", "🤖 AI 分析",
     "💡 论文推荐", "⭐ 收藏夹", "📄 导出报告", "🔔 定时推送"],
    index=0
)

st.sidebar.divider()
st.sidebar.markdown("### 数据源")
st.sidebar.markdown("- ✅ OpenAlex (2.5亿+)")
st.sidebar.markdown("- ✅ arXiv (预印本)")
st.sidebar.markdown("- ✅ 领研网 (中文)")
st.sidebar.markdown("- ⚠️ Semantic Scholar (待配置)")
st.sidebar.divider()
st.sidebar.markdown(f"**版本**: v0.3.0（推荐/收藏/报告/推送）")
st.sidebar.markdown(f"**更新**: 2026-06-28")


# ==================== 辅助函数 ====================

def _import_paper(paper_data):
    """导入单篇论文并评级，返回 (paper_id, rating) 或 (None, None)"""
    # 确保 paper_data 有 id
    if not paper_data.get("id"):
        import hashlib
        paper_data["id"] = hashlib.md5(paper_data["title"].encode()).hexdigest()[:16]

    success = insert_paper(paper_data)
    if not success:
        return None, None

    rating = rate_paper(paper_data)
    insert_rating(paper_data["id"], rating)
    return paper_data["id"], rating


def _get_rating_for_paper(paper_id):
    """获取论文的评级数据"""
    from db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ratings WHERE paper_id = ?", (paper_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_tags_for_paper(paper_id):
    """获取论文的标签"""
    from db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.name, t.category FROM tags t
        JOIN paper_tags pt ON t.id = pt.tag_id
        WHERE pt.paper_id = ?
    """, (paper_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _save_tags(paper_id, tags):
    """保存标签到数据库"""
    from db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    for tag in tags:
        # 插入标签（如果不存在）
        cursor.execute(
            "INSERT OR IGNORE INTO tags (name, category, description) VALUES (?, ?, ?)",
            (tag["name"], tag["category"], tag.get("description", ""))
        )
        # 获取标签ID
        cursor.execute("SELECT id FROM tags WHERE name = ? AND category = ?",
                       (tag["name"], tag["category"]))
        row = cursor.fetchone()
        if row:
            tag_id = row["id"]
            cursor.execute(
                "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id, confidence) VALUES (?, ?, ?)",
                (paper_id, tag_id, tag.get("confidence", 1.0))
            )
    conn.commit()
    conn.close()


# ==================== 1. 仪表盘 ====================

def show_dashboard():
    st.title("📋 仪表盘")

    stats = get_stats()

    if not stats or stats.get("total_papers", 0) == 0:
        st.warning("数据库为空，请先导入论文。")
        st.info("💡 去「搜索论文」或「领研网」页面导入论文。")
        return

    # 指标卡
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("论文总数", stats.get("total_papers", 0))
    col2.metric("平均评分", f"{stats.get('avg_score', 0):.1f}")
    col3.metric("最高评分", f"{stats.get('max_score', 0):.1f}")
    col4.metric("评级数", stats.get("total_ratings", 0))

    st.divider()

    # 评级分布
    st.subheader("评级分布")
    level_dist = stats.get("level_distribution", {})
    if level_dist:
        grade_df = pd.DataFrame([
            {"等级": k, "数量": v} for k, v in sorted(level_dist.items())
        ])
        fig_grade = px.bar(grade_df, x="等级", y="数量", color="等级",
                           color_discrete_map={"S": "#ff4444", "A": "#ff8800", "B": "#ffcc00",
                                               "C": "#88cc00", "D": "#88aaff", "E": "#aaaaaa"},
                           title="评级分布")
        st.plotly_chart(fig_grade, use_container_width=True)
    else:
        st.info("暂无评级数据。")

    # 评分详情
    ratings = get_all_ratings(limit=9999)
    if ratings:
        df = pd.DataFrame(ratings)

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("五维评分雷达")
            avg_data = {
                "学术影响力": df["academic_impact"].mean(),
                "商业潜力": df["commercial_potential"].mean(),
                "创新指数": df["innovation_index"].mean(),
                "可复现性": df["reproducibility"].mean(),
                "组合价值": df["combo_value"].mean(),
            }
            fig_radar = go.Figure(data=go.Scatterpolar(
                r=list(avg_data.values()) + [list(avg_data.values())[0]],
                theta=list(avg_data.keys()) + [list(avg_data.keys())[0]],
                fill='toself',
                fillcolor='rgba(0, 128, 255, 0.2)',
                line=dict(color='blue', width=2),
            ))
            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                                   title="平均五维评分")
            st.plotly_chart(fig_radar, use_container_width=True)

        with col_right:
            st.subheader("年份分布")
            if "year" in df.columns:
                year_counts = df["year"].value_counts().reset_index()
                year_counts.columns = ["年份", "数量"]
                year_counts = year_counts.sort_values("年份")
                fig_year = px.bar(year_counts, x="年份", y="数量", title="论文年份分布")
                st.plotly_chart(fig_year, use_container_width=True)


# ==================== 2. 搜索论文 ====================

def show_search():
    st.title("🔍 搜索论文")

    # 搜索框
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        query = st.text_input("关键词", placeholder="输入关键词，如 LLM、量子计算、石墨烯...")
    with col2:
        limit = st.number_input("数量", min_value=5, max_value=100, value=20)
    with col3:
        st.write("")
        st.write("")
        search_local = st.button("搜索本地", type="primary")

    # 筛选
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        year_from = st.number_input("年份(起)", min_value=1990, max_value=2026, value=2020)
    with col_f2:
        min_citations = st.number_input("最低引用", min_value=0, max_value=10000, value=0)
    with col_f3:
        st.write("")
        st.write("")
        search_online = st.button("在线搜索并导入")

    # 本地搜索
    if search_local and query:
        results = search_papers(query, limit=limit, year_from=year_from, min_citations=min_citations)
        if results:
            st.success(f"找到 {len(results)} 篇论文")
            for paper in results:
                _show_paper_card(paper)
        else:
            st.warning("本地数据库未找到匹配论文，试试在线搜索。")

    # 在线搜索
    if search_online and query:
        with st.spinner(f"正在从 OpenAlex + arXiv 搜索 '{query}'..."):
            results = st.session_state.fetcher.search(query, limit=limit, sources=["oa", "arxiv"])
        if results:
            st.success(f"找到 {len(results)} 篇论文，正在导入...")
            imported = 0
            for paper_data in results:
                pid, rating = _import_paper(paper_data)
                if pid:
                    tags = generate_tags(paper_data)
                    _save_tags(pid, tags)
                    imported += 1
            st.success(f"成功导入 {imported} 篇论文，已自动评级！")
            # 显示本地搜索结果
            local_results = search_papers(query, limit=limit)
            for paper in local_results:
                _show_paper_card(paper)
        else:
            st.error("未找到论文，请尝试其他关键词。")


def _show_paper_card(paper):
    """显示论文卡片"""
    with st.container():
        col1, col2 = st.columns([4, 1])
        with col1:
            title = paper.get("title", "无标题")
            st.markdown(f"**{title}**")
            authors = paper.get("authors", "")
            if authors and isinstance(authors, str):
                try:
                    authors = json.loads(authors)
                    authors = ", ".join(authors[:5])
                except:
                    pass
            if authors:
                st.caption(f"作者: {str(authors)[:80]}")
            journal = paper.get("journal", "")
            year = paper.get("year", "")
            citations = paper.get("citations", 0)
            st.caption(f"期刊: {journal} | 年份: {year} | 引用: {citations}")
        with col2:
            rating = _get_rating_for_paper(paper["id"])
            if rating:
                grade = rating.get("rating_level", "?")
                score = rating.get("overall_score", 0)
                color = {"S": "🔴", "A": "🟠", "B": "🟡", "C": "🟢", "D": "🔵", "E": "⚪"}.get(grade, "⚪")
                st.metric(f"{color} 等级", grade)
                st.caption(f"评分: {score:.1f}")
            else:
                st.caption("未评级")

        # 详情按钮
        if st.button("查看详情", key=f"detail_{paper['id']}"):
            st.session_state.selected_paper = paper["id"]
            st.rerun()

        st.divider()


def _show_paper_detail(paper_id):
    """显示论文详情"""
    paper = get_paper(paper_id)
    if not paper:
        st.error("论文不存在")
        return

    st.button("← 返回", on_click=lambda: st.session_state.pop("selected_paper", None))

    st.title(paper.get("title", "无标题"))

    # 基本信息
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("年份", paper.get("year", "N/A"))
    col2.metric("引用量", paper.get("citations", 0))
    col3.metric("期刊", paper.get("journal", "N/A") or "N/A")
    col4.metric("来源", paper.get("source", "N/A"))

    # 作者
    authors = paper.get("authors", "")
    if authors and isinstance(authors, str):
        try:
            authors = json.loads(authors)
            authors = ", ".join(authors)
        except:
            pass
    if authors:
        st.markdown(f"**作者**: {authors}")

    # 摘要
    abstract = paper.get("abstract", "")
    if abstract:
        with st.expander("摘要", expanded=True):
            st.write(abstract)

    # 评级
    rating = paper.get("rating") or _get_rating_for_paper(paper_id)
    if rating:
        st.divider()
        st.subheader("📊 五维评级")

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("学术影响力", f"{rating.get('academic_impact', 0):.1f}")
        col2.metric("商业潜力", f"{rating.get('commercial_potential', 0):.1f}")
        col3.metric("创新指数", f"{rating.get('innovation_index', 0):.1f}")
        col4.metric("可复现性", f"{rating.get('reproducibility', 0):.1f}")
        col5.metric("组合价值", f"{rating.get('combo_value', 0):.1f}")

        # 雷达图
        categories = ["学术影响力", "商业潜力", "创新指数", "可复现性", "组合价值"]
        values = [
            rating.get("academic_impact", 0),
            rating.get("commercial_potential", 0),
            rating.get("innovation_index", 0),
            rating.get("reproducibility", 0),
            rating.get("combo_value", 0),
        ]

        fig = go.Figure(data=go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill='toself',
            fillcolor='rgba(0, 128, 255, 0.2)',
            line=dict(color='blue', width=2),
        ))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
        st.plotly_chart(fig, use_container_width=True)

        # 综合评分
        st.markdown(f"### 综合评分: {rating.get('overall_score', 0):.1f} [{rating.get('rating_level', '?')}]")

        # 商业化预测
        trl = rating.get("combo_value", 0)  # 暂用combo_value占位
        st.divider()
        st.subheader("🔮 商业化预测")
        pred = predict_commercialization(paper)
        col1, col2, col3 = st.columns(3)
        col1.metric("TRL 等级", f"TRL {pred.get('trl', '?')}")
        col2.metric("预计时间", pred.get("base_time", "未知"))
        col3.metric("置信度", pred.get("confidence", "未知"))

        if pred.get("factors"):
            st.markdown("**影响因素**:")
            for f in pred["factors"]:
                st.markdown(f"- {f}")

    # 标签
    tags = _get_tags_for_paper(paper_id)
    if tags:
        st.divider()
        st.subheader("🏷 标签")
        tag_str = " ".join([f"`{t['name']}`" for t in tags])
        st.markdown(tag_str)

    # 链接
    st.divider()
    if paper.get("url"):
        st.markdown(f"[原文链接]({paper['url']})")
    if paper.get("pdf_url"):
        st.markdown(f"[PDF下载]({paper['pdf_url']})")


# ==================== 3. 排行榜 ====================

def show_leaderboard():
    st.title("📊 排行榜")

    col1, col2 = st.columns([1, 3])
    with col1:
        sort_options = {
            "综合评分": "overall_score",
            "学术影响力": "academic_impact",
            "商业潜力": "commercial_potential",
            "创新指数": "innovation_index",
        }
        sort_label = st.selectbox("排序方式", list(sort_options.keys()))
        limit = st.selectbox("显示数量", [10, 20, 50, 100], index=1)

    sort_col = sort_options[sort_label]
    ratings = get_all_ratings(limit=limit, order_by=sort_col)

    if not ratings:
        st.warning("数据库为空，请先导入论文。")
        return

    # 表格
    df = pd.DataFrame(ratings)
    display_cols = ["rating_level", "overall_score", "title", "year", "citations", "journal"]
    display_cols = [c for c in display_cols if c in df.columns]
    df_display = df[display_cols].copy()
    col_names = {"rating_level": "等级", "overall_score": "评分", "title": "标题",
                 "year": "年份", "citations": "引用", "journal": "期刊"}
    df_display = df_display.rename(columns=col_names)

    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # 条形图
    st.subheader(f"Top {limit} 评分对比")
    fig = px.bar(
        df.head(limit),
        x="overall_score",
        y="title",
        orientation='h',
        color="rating_level",
        color_discrete_map={"S": "#ff4444", "A": "#ff8800", "B": "#ffcc00",
                             "C": "#88cc00", "D": "#88aaff", "E": "#aaaaaa"},
        title=f"Top {limit} 论文评分排行",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(400, limit * 30))
    st.plotly_chart(fig, use_container_width=True)


# ==================== 4. 领研网 ====================

def show_linkresearcher():
    st.title("📰 领研网最新论文")

    st.markdown("从领研网抓取最新论文列表，点击可一键从 OpenAlex 搜索并导入。")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 刷新列表", type="primary"):
            st.session_state.lr_papers = None

    # 抓取
    if "lr_papers" not in st.session_state or st.session_state.lr_papers is None:
        with st.spinner("正在抓取领研网最新论文..."):
            st.session_state.lr_papers = fetch_lr_papers(pages=1)

    papers = st.session_state.lr_papers

    if not papers:
        st.warning("未抓取到论文，请稍后重试。")
        return

    st.success(f"抓取到 {len(papers)} 篇最新论文")

    # 显示论文列表
    for i, paper in enumerate(papers):
        with st.container():
            col1, col2, col3 = st.columns([5, 2, 1])
            with col1:
                st.markdown(f"**{i+1}. {paper['title']}**")
                journal = paper.get("journal", "")
                date = paper.get("date", "")
                authors = paper.get("authors", "")
                st.caption(f"期刊: {journal} | 日期: {date}")
                if authors:
                    st.caption(f"作者: {authors[:60]}")
            with col2:
                tags = paper.get("tags", [])
                if tags:
                    st.caption(" ".join([f"`{t}`" for t in tags[:3]]))
            with col3:
                if st.button("导入", key=f"lr_import_{i}"):
                    _import_from_linkresearcher(paper)

            st.divider()


def _import_from_linkresearcher(lr_paper):
    """从领研网论文信息，通过 OpenAlex 搜索并导入"""
    title = lr_paper.get("title", "")
    # 去掉中文标题中的特殊字符
    search_title = title.split("｜")[0].split("|")[0].strip()

    with st.spinner(f"正在搜索 '{search_title[:30]}...'"):
        results = st.session_state.fetcher.search(search_title, limit=3, sources=["oa"])

    if results:
        paper_data = results[0]
        pid, rating = _import_paper(paper_data)
        if pid:
            tags = generate_tags(paper_data)
            _save_tags(pid, tags)
            st.success(f"导入成功！评级: {rating.get('rating_level', '?')} ({rating.get('overall_score', 0):.1f})")
        else:
            st.info("该论文已在数据库中。")
    else:
        with st.spinner("OpenAlex 未找到，尝试 arXiv..."):
            results = st.session_state.fetcher.search(search_title, limit=3, sources=["arxiv"])
        if results:
            paper_data = results[0]
            pid, rating = _import_paper(paper_data)
            if pid:
                tags = generate_tags(paper_data)
                _save_tags(pid, tags)
                st.success(f"从 arXiv 导入成功！评级: {rating.get('rating_level', '?')} ({rating.get('overall_score', 0):.1f})")
        else:
            st.error("未找到匹配论文，可手动导入。")


# ==================== 5. 批量导入 ====================

def show_batch_import():
    st.title("📥 批量导入")

    st.markdown("粘贴论文标题列表（每行一个），自动从 OpenAlex 搜索并导入。")

    # 输入框
    titles_text = st.text_area(
        "论文标题列表",
        placeholder="每行输入一个论文标题，例如：\nLarge language models encode clinical knowledge\nA Survey on Evaluation of Large Language Models\n...",
        height=200,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("开始导入", type="primary"):
            titles = [t.strip() for t in titles_text.split("\n") if t.strip()]
            if not titles:
                st.warning("请输入至少一个标题。")
                return

            st.info(f"共 {len(titles)} 个标题，开始搜索导入...")
            progress = st.progress(0)
            success_count = 0
            fail_count = 0

            for i, title in enumerate(titles):
                progress.progress((i + 1) / len(titles), f"正在处理: {title[:40]}...")
                try:
                    results = st.session_state.fetcher.search(title, limit=1, sources=["oa"])
                    if not results:
                        results = st.session_state.fetcher.search(title, limit=1, sources=["arxiv"])

                    if results:
                        paper_data = results[0]
                        pid, rating = _import_paper(paper_data)
                        if pid:
                            tags = generate_tags(paper_data)
                            _save_tags(pid, tags)
                            success_count += 1
                    else:
                        fail_count += 1
                        st.warning(f"未找到: {title[:50]}")
                except Exception as e:
                    fail_count += 1
                    st.error(f"导入失败: {title[:40]} - {e}")

                time.sleep(0.5)  # 礼貌等待

            progress.empty()
            st.success(f"完成！成功导入 {success_count} 篇，失败 {fail_count} 篇。")

    with col2:
        st.markdown("### 使用说明")
        st.markdown("""
        1. 每行输入一个论文标题
        2. 支持中英文标题
        3. 先从 OpenAlex 搜索，找不到再从 arXiv 搜索
        4. 导入后自动评级和生成标签
        5. 可以从领研网复制论文标题粘贴到这里
        """)


# ==================== 多主题批量导入页面 ====================

def show_batch_topics():
    """多主题批量导入页面"""
    st.header("🚀 多主题批量导入")
    st.markdown("从预设主题库批量导入多个领域的论文")

    from batch_import_topics import TOPIC_LIBRARY

    # 显示主题库
    st.subheader("可用主题库")
    cols = st.columns(5)
    for i, (cat, topics) in enumerate(TOPIC_LIBRARY.items()):
        with cols[i % 5]:
            st.markdown(f"**{cat}**")
            for t in topics:
                st.markdown(f"- {t}")

    st.divider()

    # 选择分类
    all_cats = list(TOPIC_LIBRARY.keys())
    selected_cats = st.multiselect("选择分类（不选=全部）", all_cats)

    per_topic = st.slider("每主题导入数量", 5, 50, 20)
    sources = st.multiselect("数据源", ["OpenAlex", "arXiv"], default=["OpenAlex"])

    if not sources:
        st.warning("请至少选择一个数据源")
        return

    src_map = {"OpenAlex": "oa", "arXiv": "arxiv"}
    src_list = [src_map[s] for s in sources]

    # 计算预计总量
    if selected_cats:
        total_topics = sum(len(TOPIC_LIBRARY[c]) for c in selected_cats)
    else:
        total_topics = sum(len(v) for v in TOPIC_LIBRARY.values())

    st.info(f"预计导入: {total_topics} 个主题 × {per_topic} 篇 = 约 {total_topics * per_topic} 篇")

    # 自定义主题
    with st.expander("添加自定义主题"):
        col_c, col_t = st.columns(2)
        with col_c:
            custom_cat = st.text_input("分类名称", placeholder="如：区块链")
        with col_t:
            custom_topic = st.text_input("主题关键词", placeholder="如：blockchain consensus")
        if st.button("添加"):
            if custom_cat and custom_topic:
                if custom_cat not in TOPIC_LIBRARY:
                    TOPIC_LIBRARY[custom_cat] = []
                TOPIC_LIBRARY[custom_cat].append(custom_topic)
                st.success(f"已添加: [{custom_cat}] {custom_topic}")
                st.rerun()

    st.divider()

    # 导入按钮
    if st.button("🚀 开始批量导入", type="primary"):
        from import_papers import import_topic
        from db import get_stats

        cats = selected_cats if selected_cats else all_cats
        topics_to_import = {k: TOPIC_LIBRARY[k] for k in cats if k in TOPIC_LIBRARY}

        stats_before = get_stats()
        total_stored = 0
        total_topics_done = 0
        total_topics_count = sum(len(v) for v in topics_to_import.values())

        progress = st.progress(0)
        status = st.empty()

        for cat_name, topics in topics_to_import.items():
            for topic in topics:
                total_topics_done += 1
                progress.progress(total_topics_done / total_topics_count)
                status.write(f"[{total_topics_done}/{total_topics_count}] 导入: {topic}")

                stored = import_topic(topic, per_topic, src_list, rate=True)
                total_stored += stored

                time.sleep(0.5)

        progress.progress(1.0)
        status.empty()

        stats_after = get_stats()
        new_papers = stats_after["total_papers"] - stats_before["total_papers"]

        st.success(f"导入完成! 新增 {new_papers} 篇，总计 {stats_after['total_papers']} 篇")

        if stats_after.get("level_distribution"):
            st.write("评级分布:")
            dist_data = []
            for level in ["S", "A", "B", "C", "D"]:
                count = stats_after["level_distribution"].get(level, 0)
                dist_data.append({"等级": level, "数量": count})
            st.bar_chart(pd.DataFrame(dist_data).set_index("等级"))


# ==================== AI 分析页面 ====================

def show_ai_analysis():
    """AI 智能分析页面"""
    st.header("🤖 AI 智能分析")
    st.markdown("使用 DeepSeek V4 Flash / GLM-4-Flash 进行深度分析")

    # 检查 LLM 是否可用
    try:
        from llm_analyzer import (
            summarize_paper, translate_abstract, plain_language_summary,
            assess_value, functional_description, deep_analysis,
            compare_papers_ai, switch_provider, CURRENT_PROVIDER
        )
    except ImportError:
        st.error("LLM 模块未安装，请确保 llm_analyzer.py 存在")
        return

    # 模型切换
    col1, col2 = st.columns([3, 1])
    with col2:
        provider_list = ["deepseek", "groq", "glm"]
        provider_labels = {
            "deepseek": "DeepSeek V4 Flash",
            "groq": "Groq Llama 3.3 70B (免费极速)",
            "glm": "GLM-4-Flash (免费)",
        }
        provider = st.selectbox(
            "当前模型",
            provider_list,
            index=provider_list.index(CURRENT_PROVIDER) if CURRENT_PROVIDER in provider_list else 0,
            format_func=lambda x: provider_labels.get(x, x)
        )
        if st.button("切换模型"):
            switch_provider(provider)
            st.rerun()

    st.divider()

    mode = st.radio("分析模式", ["单篇分析", "双篇对比"], horizontal=True)

    if mode == "单篇分析":
        paper_id = st.text_input("输入论文ID", placeholder="例如: arxiv_2606.27372v1")

        # 快速选择
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, year FROM papers ORDER BY citations DESC LIMIT 20")
        recent = cursor.fetchall()
        conn.close()

        if recent:
            options = {f"{r['title'][:40]}... ({r['year']})": r["id"] for r in recent}
            selected = st.selectbox("或从最近导入中选择", [""] + list(options.keys()))
            if selected:
                paper_id = options[selected]

        if not paper_id:
            st.info("请输入论文ID或从列表中选择")
            return

        paper = get_paper(paper_id)
        if not paper:
            st.error(f"未找到论文: {paper_id}")
            return

        st.success(f"已选择: {paper.get('title', 'N/A')[:60]}")

        analysis_type = st.selectbox(
            "选择分析类型",
            ["全部分析 (5项)", "1. AI 摘要", "2. 摘要翻译", "3. 通俗解读",
             "4. 价值评估", "5. 功能说明"]
        )

        if st.button("🚀 开始分析", type="primary"):
            action_map = {
                "全部分析 (5项)": "all",
                "1. AI 摘要": "summary",
                "2. 摘要翻译": "translate",
                "3. 通俗解读": "plain",
                "4. 价值评估": "value",
                "5. 功能说明": "function",
            }
            action = action_map[analysis_type]

            if action == "all":
                with st.spinner("正在执行深度分析（5项）..."):
                    progress = st.progress(0)
                    results = {}

                    steps = [
                        ("AI 摘要", summarize_paper, "summary"),
                        ("摘要翻译", translate_abstract, "translation"),
                        ("通俗解读", plain_language_summary, "plain_summary"),
                        ("价值评估", assess_value, "value_assessment"),
                        ("功能说明", functional_description, "functional_desc"),
                    ]

                    for i, (name, func, key) in enumerate(steps):
                        st.write(f"  [{i+1}/5] {name}...")
                        results[key] = func(paper)
                        progress.progress((i + 1) / 5)

                    st.success("分析完成!")

                    for name, _, key in steps:
                        st.divider()
                        st.subheader(name)
                        st.markdown(results.get(key, "生成失败"))

            else:
                func_map = {
                    "summary": summarize_paper,
                    "translate": translate_abstract,
                    "plain": plain_language_summary,
                    "value": assess_value,
                    "function": functional_description,
                }
                func = func_map[action]
                with st.spinner(f"正在生成{analysis_type}..."):
                    result = func(paper)
                    st.divider()
                    st.subheader(analysis_type)
                    st.markdown(result)

    else:  # 双篇对比
        col_a, col_b = st.columns(2)

        with col_a:
            id1 = st.text_input("论文A ID", key="cmp_id1")

        with col_b:
            id2 = st.text_input("论文B ID", key="cmp_id2")

        if st.button("🚖 AI 对比分析", type="primary"):
            if not id1 or not id2:
                st.warning("请输入两个论文ID")
                return

            p1 = get_paper(id1)
            p2 = get_paper(id2)

            if not p1:
                st.error(f"未找到论文A: {id1}")
                return
            if not p2:
                st.error(f"未找到论文B: {id2}")
                return

            st.info(f"论文A: {p1.get('title', 'N/A')[:40]}")
            st.info(f"论文B: {p2.get('title', 'N/A')[:40]}")

            with st.spinner("AI 正在对比分析..."):
                result = compare_papers_ai(p1, p2)
                st.divider()
                st.subheader("对比结果")
                st.markdown(result)


# ==================== 知识图谱页面 ====================

def _render_network_graph(G, stats, graph_type):
    """使用 plotly 渲染网络图"""
    import networkx as nx

    if G.number_of_nodes() == 0:
        st.warning("图谱为空，无节点可显示。")
        if stats.get("message"):
            st.info(stats["message"])
        return

    # 计算布局
    is_directed = G.is_directed()
    if is_directed:
        G_undirected = G.to_undirected()
    else:
        G_undirected = G

    try:
        pos = nx.spring_layout(G_undirected, k=1.8/max(1, len(G_undirected.nodes)**0.5),
                                iterations=80, seed=42)
    except Exception:
        pos = nx.random_layout(G_undirected, seed=42)

    # 节点度数（用于大小）
    degrees = dict(G_undirected.degree())
    max_degree = max(degrees.values()) if degrees else 1

    # 构建节点 trace
    node_x, node_y, node_text, node_size, node_color = [], [], [], [], []
    for node in G_undirected.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        # 节点大小：基于度数或size属性
        size_attr = G_undirected.nodes[node].get("size", 1)
        deg = degrees.get(node, 1)
        node_size.append(8 + 25 * (deg / max_degree) + min(size_attr * 0.5, 15))

        # 节点颜色：基于度数
        node_color.append(deg)

        # 悬停文本
        title = G_undirected.nodes[node].get("title", "")
        if title:
            node_text.append(f"{node}<br>标题: {title[:60]}<br>度数: {deg}")
        else:
            node_text.append(f"{node}<br>度数: {deg}<br>权重: {size_attr}")

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[str(n)[:20] for n in G_undirected.nodes()],
        textposition="top center",
        hovertext=node_text,
        hoverinfo='text',
        marker=dict(
            size=node_size,
            color=node_color,
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="度数", thickness=10),
            line=dict(width=1, color='#444'),
        ),
        line=dict(width=0),
    )

    # 构建边 trace
    edge_x, edge_y = [], []
    for edge in G_undirected.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode='lines',
        line=dict(width=0.8, color='#888'),
        hoverinfo='none',
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        title=f"{graph_type} ({G.number_of_nodes()} 节点 / {G.number_of_edges()} 边)",
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20, l=5, r=5, t=50),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='white',
        height=600,
    )
    st.plotly_chart(fig, use_container_width=True)


def show_knowledge_graph():
    st.title("🕸 知识图谱")

    from knowledge_graph import (
        build_graph, get_graph_summary,
        build_field_network, build_author_network,
        build_keyword_network, build_similarity_network, build_citation_network,
    )

    summary = get_graph_summary()

    # 概览
    col1, col2, col3 = st.columns(3)
    col1.metric("论文总数", summary["total_papers"])
    col2.metric("评级总数", summary["total_ratings"])
    col3.metric("有引用关系", summary["papers_with_references"])

    st.divider()

    # 图谱类型选择
    graph_type = st.selectbox(
        "选择图谱类型",
        ["领域共现", "作者合作", "关键词共现", "论文相似", "引用网络"],
        help="不同图谱展示论文间的不同关系维度"
    )

    # 参数调整
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        if graph_type == "领域共现":
            top_n = st.slider("显示领域数", 20, 80, 40, key="field_top")
            min_co = st.slider("最小共现次数", 1, 10, 2, key="field_min")
        elif graph_type == "作者合作":
            min_papers = st.slider("最小论文数", 1, 5, 2, key="author_papers")
            min_coop = st.slider("最小合作次数", 1, 5, 2, key="author_coop")
        elif graph_type == "关键词共现":
            top_n = st.slider("显示关键词数", 20, 100, 50, key="kw_top")
            min_co = st.slider("最小共现次数", 2, 15, 3, key="kw_min")
        elif graph_type == "论文相似":
            sim_top = st.slider("分析论文数", 30, 150, 80, key="sim_top")
            min_sim = st.slider("最小相似度", 0.1, 0.5, 0.2, 0.05, key="sim_min")
    with col_p2:
        st.markdown("**图谱说明**")
        descriptions = {
            "领域共现": "节点=研究领域，边=两领域在同一论文中共现。节点越大=涉及论文越多。",
            "作者合作": "节点=作者，边=两人合作过。只显示合作≥2次的作者。",
            "关键词共现": "节点=标题关键词，边=两词在同一标题出现。反映研究热点关联。",
            "论文相似": "节点=高评分论文，边=内容相似（领域+标题+摘要）。分析Top论文间关系。",
            "引用网络": "节点=论文，箭头=引用关系。需先补充抓取引用数据（见下方按钮）。",
        }
        st.caption(descriptions.get(graph_type, ""))

    st.divider()

    # 构建图谱
    with st.spinner(f"正在构建 {graph_type} 图谱..."):
        if graph_type == "领域共现":
            G, stats = build_field_network(top_n=top_n, min_cooccurrence=min_co)
        elif graph_type == "作者合作":
            G, stats = build_author_network(min_papers=min_papers,
                                             min_cooperation=min_coop)
        elif graph_type == "关键词共现":
            G, stats = build_keyword_network(top_n=top_n, min_cooccurrence=min_co)
        elif graph_type == "论文相似":
            G, stats = build_similarity_network(top_n=sim_top, min_similarity=min_sim)
        elif graph_type == "引用网络":
            G, stats = build_citation_network()

    # 统计信息
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("节点数", stats.get("node_count", 0))
    col_s2.metric("边数", stats.get("edge_count", 0))
    if stats.get("avg_degree"):
        col_s3.metric("平均度数", stats["avg_degree"])
    else:
        col_s3.metric("移除孤立", stats.get("removed_isolated", 0))
    col_s4.metric("分析论文", stats.get("analyzed_papers", summary["total_papers"]))

    if stats.get("message"):
        st.info(stats["message"])

    # 渲染网络图
    _render_network_graph(G, stats, graph_type)

    # Top列表
    st.divider()
    if graph_type == "领域共现" and stats.get("top_fields"):
        st.subheader("Top 领域")
        df = pd.DataFrame(stats["top_fields"], columns=["领域", "论文数"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    elif graph_type == "作者合作" and stats.get("top_authors"):
        st.subheader("Top 多产作者")
        df = pd.DataFrame(stats["top_authors"], columns=["作者", "论文数"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    elif graph_type == "关键词共现" and stats.get("top_keywords"):
        st.subheader("Top 关键词")
        df = pd.DataFrame(stats["top_keywords"], columns=["关键词", "出现次数"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # 引用网络特殊提示
    if graph_type == "引用网络" and not stats.get("has_citation_data"):
        st.divider()
        st.subheader("📋 补充抓取引用关系")
        st.warning("数据库中论文的引用关系(ref_ids)为空，无法构建引用网络。")
        st.markdown("""
        **如何补充引用数据：**

        在终端运行以下命令，通过 OpenAlex API 抓取每篇论文的参考文献列表：

        ```bash
        # 抓取所有论文的引用关系（约需10-15分钟）
        python fetch_references.py

        # 或只抓取前100篇测试
        python fetch_references.py --limit 100

        # 先测试不写入
        python fetch_references.py --limit 5 --dry-run
        ```

        抓取完成后，重新访问此页面即可查看完整的引用网络图。
        """)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚀 开始抓取引用关系 (前50篇)", type="primary"):
                st.session_state.start_fetch_refs = True
                st.info("请在终端运行: `python fetch_references.py --limit 50`")
        with col_btn2:
            if st.button("📖 查看抓取脚本"):
                st.code("""
# fetch_references.py 使用方法
python fetch_references.py --limit 50      # 抓取50篇
python fetch_references.py --limit 100     # 抓取100篇
python fetch_references.py                 # 抓取全部(571篇)
                """, language="bash")


# ==================== 论文推荐页面 ====================

def show_recommendations():
    st.title("💡 论文推荐")

    from recommendation_engine import (
        get_user_profile, get_recommendations, record_view,
        rate_paper_user, set_preference, get_all_preferences
    )

    # 用户画像
    profile = get_user_profile()
    with st.expander("👤 用户画像", expanded=False):
        col1, col2, col3 = st.columns(3)
        col1.metric("浏览论文", profile["viewed_papers"])
        col2.metric("收藏论文", profile["favorited_papers"])
        col3.metric("评分论文", profile["rated_papers"])

        if profile["top_fields"]:
            st.markdown("**偏好领域**:")
            cols = st.columns(min(len(profile["top_fields"]), 5))
            for i, (field, count) in enumerate(profile["top_fields"][:5]):
                cols[i].metric(field[:15], f"{count}次")

        if profile["top_keywords"]:
            st.markdown("**偏好关键词**:")
            kw_str = " ".join([f"`{k}`" for k, _ in profile["top_keywords"][:15]])
            st.markdown(kw_str)

    st.divider()

    # 推荐策略选择
    col1, col2 = st.columns([2, 1])
    with col1:
        strategy = st.selectbox(
            "推荐策略",
            ["hybrid", "content", "rating", "trending", "recent"],
            format_func=lambda x: {
                "hybrid": "🤝 混合推荐（综合策略）",
                "content": "🎯 内容匹配（基于偏好）",
                "rating": "🏆 高评分推荐",
                "trending": "🔥 热门论文",
                "recent": "🆕 最新论文",
            }.get(x, x)
        )
    with col2:
        top_n = st.slider("推荐数量", 5, 50, 15)

    # 领域筛选（用于content策略）
    field_filter = None
    if strategy == "content":
        from db import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT json_each.value as f FROM papers, json_each(papers.fields) ORDER BY f LIMIT 100")
        all_fields = [r["f"] for r in cursor.fetchall() if r["f"]]
        conn.close()
        if all_fields:
            field_filter = st.selectbox("指定领域", ["全部"] + all_fields)
            if field_filter == "全部":
                field_filter = None

    # 生成推荐
    if st.button("🚀 生成推荐", type="primary"):
        with st.spinner("正在生成推荐..."):
            kwargs = {}
            if strategy == "content" and field_filter:
                kwargs["field"] = field_filter
            recs = get_recommendations(strategy, top_n=top_n, **kwargs)

        if not recs:
            st.warning("暂无推荐，请先浏览/收藏一些论文以建立用户画像。")
            return

        st.success(f"为您推荐 {len(recs)} 篇论文")

        for i, r in enumerate(recs, 1):
            with st.container():
                col1, col2, col3 = st.columns([5, 2, 1])
                with col1:
                    title = r.get("title", "无标题")
                    st.markdown(f"**{i}. {title}**")
                    journal = r.get("journal", "")
                    year = r.get("year", "")
                    citations = r.get("citations", 0)
                    st.caption(f"📅 {year} | 📖 {journal[:30] if journal else 'N/A'} | 🔗 引用{citations}")
                    if r.get("match_reason"):
                        st.caption(f"💡 {r['match_reason']}")
                with col2:
                    level = r.get("rating_level", "?")
                    score = r.get("overall_score", 0)
                    rec_score = r.get("recommend_score", 0)
                    color = {"S": "🔴", "A": "🟠", "B": "🟡", "C": "🟢", "D": "🔵"}.get(level, "⚪")
                    st.metric(f"{color} 等级", level)
                    st.caption(f"评分: {score:.1f} | 推荐: {rec_score:.2f}")
                with col3:
                    if st.button("查看", key=f"rec_{r['id']}"):
                        st.session_state.selected_paper = r["id"]
                        st.rerun()

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("⭐ 收藏", key=f"fav_{r['id']}"):
                        st.session_state.fav_paper = r["id"]
                        st.rerun()
                with col_b:
                    rating = st.selectbox("我的评分", [1, 2, 3, 4, 5], key=f"ur_{r['id']}", label_visibility="collapsed")
                with col_c:
                    if st.button("提交评分", key=f"sr_{r['id']}"):
                        rate_paper_user(r["id"], rating)
                        st.success(f"已评分 {rating}星")
                        record_view(r["id"])
                        st.rerun()

                st.divider()


# ==================== 收藏夹页面 ====================

def show_favorites():
    st.title("⭐ 收藏夹")

    from favorites_manager import (
        ensure_default_collections, list_collections, create_collection,
        delete_collection, list_papers_in_collection, add_to_collection,
        remove_from_collection, update_notes, get_collection
    )

    ensure_default_collections()

    # 创建新收藏夹
    with st.expander("➕ 创建收藏夹", expanded=False):
        with st.form("new_collection"):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                name = st.text_input("名称", placeholder="如：经典必读")
            with col2:
                desc = st.text_input("描述", placeholder="收藏夹描述")
            with col3:
                color = st.color_picker("颜色", "#4e79a7")
            if st.form_submit_button("创建"):
                if name:
                    cid = create_collection(name, desc, color)
                    if cid > 0:
                        st.success(f"收藏夹 '{name}' 创建成功！")
                        st.rerun()

    st.divider()

    # 收藏夹列表
    collections = list_collections()
    if not collections:
        st.info("还没有收藏夹，点击上方创建")
        return

    # 选择收藏夹
    col_names = [f"{c['name']} ({c['paper_count']}篇)" for c in collections]
    selected_idx = st.selectbox("选择收藏夹", range(len(col_names)),
                                  format_func=lambda i: col_names[i])
    selected_col = collections[selected_idx]

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"### {selected_col['name']}")
        if selected_col.get("description"):
            st.caption(selected_col["description"])
    with col2:
        st.metric("论文数", selected_col["paper_count"])
    with col3:
        if st.button("🗑 删除收藏夹"):
            if delete_collection(selected_col["id"]):
                st.success("已删除")
                st.rerun()

    st.divider()

    # 收藏夹内论文
    papers = list_papers_in_collection(selected_col["id"], limit=100)
    if not papers:
        st.info("收藏夹为空，去搜索论文并收藏吧！")
    else:
        # 搜索框
        search_q = st.text_input("🔍 在收藏夹内搜索", "")
        if search_q:
            from favorites_manager import search_in_collection
            papers = search_in_collection(selected_col["id"], search_q)

        for idx, p in enumerate(papers):
            with st.container():
                col1, col2, col3 = st.columns([5, 2, 1])
                with col1:
                    title = p.get("title", "无标题")
                    st.markdown(f"**{title}**")
                    authors = p.get("authors", [])
                    if isinstance(authors, str):
                        try:
                            authors = json.loads(authors)
                        except:
                            pass
                    author_str = ", ".join(authors[:3]) if authors else "N/A"
                    st.caption(f"📝 {author_str} | 📅 {p.get('year', 'N/A')} | 📖 {(p.get('journal') or 'N/A')[:30]}")
                    if p.get("notes"):
                        st.info(f"📝 {p['notes']}")
                with col2:
                    level = p.get("rating_level", "?")
                    score = p.get("overall_score", 0)
                    st.metric("评级", f"{level} ({score:.1f})")
                with col3:
                    if st.button("查看", key=f"fv_{idx}_{p['id']}"):
                        st.session_state.selected_paper = p["id"]
                        st.rerun()
                    if st.button("移除", key=f"rm_{idx}_{p['id']}"):
                        remove_from_collection(selected_col["id"], p["id"])
                        st.rerun()

                # 笔记编辑
                with st.expander("编辑笔记", expanded=False):
                    new_note = st.text_area("笔记", value=p.get("notes", ""),
                                              key=f"note_{idx}_{p['id']}")
                    if st.button("保存笔记", key=f"sn_{idx}_{p['id']}"):
                        update_notes(selected_col["id"], p["id"], new_note)
                        st.success("已保存")
                        st.rerun()

                st.divider()


# ==================== 导出报告页面 ====================

def show_reports():
    st.title("📄 导出报告")

    from report_generator import (
        export_stats_report, export_paper_report, export_collection_report,
        export_search_report, export_recommendation_report, list_reports,
        REPORT_DIR
    )
    from favorites_manager import list_collections
    from db import search_papers
    from recommendation_engine import get_recommendations

    # 报告类型选择
    report_type = st.selectbox(
        "选择报告类型",
        ["📊 数据库统计报告", "📄 单篇论文报告", "📁 收藏夹报告",
         "🔍 检索结果报告", "💡 推荐清单报告"]
    )

    fmt = st.radio("导出格式", ["Markdown (.md)", "HTML (.html)"], horizontal=True)
    fmt_code = "md" if "Markdown" in fmt else "html"

    st.divider()

    # 根据类型显示不同选项
    if report_type == "📊 数据库统计报告":
        st.info("生成包含论文数、评级分布、统计图表的报告")
        if st.button("生成报告", type="primary"):
            path = export_stats_report(fmt_code)
            st.success(f"报告已生成: {path}")
            with open(path, "r", encoding="utf-8") as f:
                st.text_area("报告内容", f.read(), height=400)

    elif report_type == "📄 单篇论文报告":
        paper_id = st.text_input("输入论文ID或搜索")
        if st.button("生成报告", type="primary") and paper_id:
            path = export_paper_report(paper_id, fmt_code)
            if os.path.exists(path):
                st.success(f"报告已生成: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    st.text_area("报告内容", f.read(), height=400)
            else:
                st.error("论文不存在")

    elif report_type == "📁 收藏夹报告":
        collections = list_collections()
        if collections:
            col_names = [f"{c['name']} ({c['paper_count']}篇)" for c in collections]
            selected_idx = st.selectbox("选择收藏夹", range(len(col_names)),
                                          format_func=lambda i: col_names[i])
            if st.button("生成报告", type="primary"):
                path = export_collection_report(collections[selected_idx]["id"], fmt_code)
                st.success(f"报告已生成: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    st.text_area("报告内容", f.read(), height=400)
        else:
            st.warning("还没有收藏夹")

    elif report_type == "🔍 检索结果报告":
        query = st.text_input("搜索关键词")
        limit = st.slider("论文数量", 10, 100, 30)
        if st.button("生成报告", type="primary") and query:
            papers = search_papers(query, limit=limit)
            if papers:
                path = export_search_report(query, papers, fmt_code)
                st.success(f"报告已生成: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    st.text_area("报告内容", f.read(), height=400)
            else:
                st.warning("未找到论文")

    elif report_type == "💡 推荐清单报告":
        top_n = st.slider("推荐数量", 5, 50, 15)
        if st.button("生成报告", type="primary"):
            recs = get_recommendations("hybrid", top_n=top_n)
            if recs:
                path = export_recommendation_report(recs, fmt_code)
                st.success(f"报告已生成: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    st.text_area("报告内容", f.read(), height=400)
            else:
                st.warning("无推荐数据")

    st.divider()

    # 已生成的报告列表
    st.subheader("📁 已生成报告")
    reports = list_reports()
    if reports:
        df = pd.DataFrame(reports)
        df["大小"] = df["size"].apply(lambda x: f"{x/1024:.1f} KB")
        df["创建时间"] = df["created_at"].apply(lambda x: x[:19].replace("T", " "))
        st.dataframe(df[["filename", "大小", "创建时间"]], use_container_width=True, hide_index=True)

        if st.button("🗑 清空所有报告"):
            for r in reports:
                try:
                    os.remove(r["path"])
                except:
                    pass
            st.success("已清空")
            st.rerun()
    else:
        st.info("还没有生成任何报告")


# ==================== 定时推送页面 ====================

def show_push():
    st.title("🔔 定时推送")

    from scheduled_push import (
        create_subscription, delete_subscription, list_subscriptions,
        execute_push, list_push_history, toggle_subscription, PUSH_DIR
    )

    # 创建订阅
    with st.expander("➕ 创建推送订阅", expanded=False):
        with st.form("new_sub"):
            col1, col2 = st.columns(2)
            with col1:
                sub_name = st.text_input("订阅名称", placeholder="如：每日推荐")
                push_type = st.selectbox("推送方式", [
                    "file (本地文件)", "webhook (Webhook)",
                    "wechat (微信-PushPlus/Server酱)", "email (邮件)"
                ])
                push_type_code = push_type.split(" ")[0]
            with col2:
                strategy = st.selectbox("推送策略", [
                    "daily (每日)", "weekly (每周)", "field (按领域)", "top_rated (Top评分)"
                ])
                strategy_code = strategy.split(" ")[0]
                top_n = st.slider("每次推送数量", 3, 20, 5)

            st.markdown("**推送配置**")
            config = {}
            if push_type_code == "file":
                config["directory"] = st.text_input("输出目录", str(PUSH_DIR))
            elif push_type_code == "webhook":
                config["url"] = st.text_input("Webhook URL", placeholder="企业微信/钉钉/飞书/自定义")
            elif push_type_code == "wechat":
                push_service = st.radio("推送服务", ["PushPlus", "Server酱"])
                if push_service == "PushPlus":
                    config["token"] = st.text_input("PushPlus Token", type="password")
                else:
                    config["key"] = st.text_input("Server酱 Key", type="password")
            elif push_type_code == "email":
                config["smtp_host"] = st.text_input("SMTP服务器", "smtp.qq.com")
                config["smtp_port"] = st.number_input("端口", 465, 587, 465)
                config["username"] = st.text_input("发件邮箱")
                config["password"] = st.text_input("授权码", type="password")
                config["to"] = st.text_input("收件邮箱")
            config["strategy"] = strategy_code
            config["top_n"] = top_n

            if st.form_submit_button("创建订阅"):
                if sub_name:
                    sid = create_subscription(sub_name, push_type_code, config)
                    if sid > 0:
                        st.success(f"订阅 '{sub_name}' 创建成功！")
                        st.rerun()

    st.divider()

    # 订阅列表
    subs = list_subscriptions()
    if not subs:
        st.info("还没有推送订阅，点击上方创建")
        return

    st.subheader(f"📋 订阅列表 ({len(subs)}个)")

    for s in subs:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            with col1:
                status = "🟢" if s["enabled"] else "🔴"
                st.markdown(f"{status} **{s['name']}**")
                st.caption(f"类型: {s['push_type']} | 策略: {s['config'].get('strategy', 'N/A')}")
                if s.get("last_push_at"):
                    st.caption(f"最后推送: {s['last_push_at'][:19]}")
            with col2:
                st.metric("推送次数", s["push_count"])
            with col3:
                if st.button("测试推送", key=f"tp_{s['id']}"):
                    with st.spinner("推送中..."):
                        result = execute_push(s["id"], strategy=s["config"].get("strategy", "daily"),
                                              top_n=s["config"].get("top_n", 5))
                    if result.get("status") == "success":
                        st.success(f"推送成功！{result.get('paper_count', 0)}篇论文")
                    elif result.get("status") == "empty":
                        st.warning("没有符合条件的论文")
                    else:
                        st.error(f"推送失败: {result.get('message', '未知错误')}")
            with col4:
                if st.button("启用/禁用", key=f"tg_{s['id']}"):
                    toggle_subscription(s["id"], not s["enabled"])
                    st.rerun()
                if st.button("删除", key=f"dl_{s['id']}"):
                    delete_subscription(s["id"])
                    st.rerun()

            st.divider()

    # 推送历史
    st.subheader("📜 推送历史")
    history = list_push_history(limit=20)
    if history:
        df = pd.DataFrame(history)
        df["时间"] = df["pushed_at"].apply(lambda x: x[:19].replace("T", " "))
        df["状态"] = df["status"].apply(lambda s: "✅" if s == "success" else "❌")
        st.dataframe(df[["时间", "subscription_name", "paper_count", "状态"]],
                     use_container_width=True, hide_index=True)
    else:
        st.info("还没有推送历史")


# ==================== 主逻辑 ====================

# 检测页面切换：清理上次页面的临时状态，避免内容残留
page_changed = ("current_page" in st.session_state
                and st.session_state.current_page != page)
if page_changed:
    # 页面切换，清理所有页面特有的临时状态
    for key in ["selected_paper", "fav_paper", "lr_papers",
                "batch_results", "search_results", "rec_results"]:
        st.session_state.pop(key, None)
st.session_state.current_page = page

# 仅在页面切换时注入滚动到顶部的JS（用img onload触发，避免iframe干扰DOM）
if page_changed:
    st.markdown(
        '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" '
        'onload="setTimeout(function(){'
        'var m=document.querySelector(\'section.main\');'
        'if(m){m.scrollTo(0,0);m.scrollTop=0;}'
        '},50)" style="display:none;width:0;height:0;border:0;">',
        unsafe_allow_html=True
    )

# 论文详情页独立处理：只有从列表点击进入时才显示
if "selected_paper" in st.session_state:
    _show_paper_detail(st.session_state.selected_paper)
else:
    if page == "📋 仪表盘":
        show_dashboard()
    elif page == "🔍 搜索论文":
        show_search()
    elif page == "📊 排行榜":
        show_leaderboard()
    elif page == "📰 领研网":
        show_linkresearcher()
    elif page == "📥 批量导入":
        show_batch_import()
    elif page == "🚀 多主题导入":
        show_batch_topics()
    elif page == "🕸 知识图谱":
        show_knowledge_graph()
    elif page == "🤖 AI 分析":
        show_ai_analysis()
    elif page == "💡 论文推荐":
        show_recommendations()
    elif page == "⭐ 收藏夹":
        show_favorites()
    elif page == "📄 导出报告":
        show_reports()
    elif page == "🔔 定时推送":
        show_push()
