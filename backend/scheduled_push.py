"""定时推送模块

支持多种推送方式:
1. 本地文件推送 - 生成待阅读清单文件
2. Webhook推送 - 通用HTTP回调（可对接企业微信、钉钉、飞书）
3. 邮件推送 - SMTP发送
4. 微信公众号 - 通过Server酱/PushPlus等中转

推送策略:
- 每日推送 - 最新高质量论文
- 每周推送 - 本周Top论文
- 关注领域推送 - 指定领域新论文
- 收藏夹更新 - 收藏夹相关论文推荐
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from db import get_connection, DB_PATH


PUSH_DIR = DB_PATH.parent / "push_queue"
PUSH_DIR.mkdir(exist_ok=True)


# ==================== 推送订阅管理 ====================

def create_subscription(name: str, push_type: str, config: Dict,
                          enabled: bool = True) -> int:
    """创建推送订阅

    Args:
        name: 订阅名称
        push_type: 推送类型 'file'/'webhook'/'email'/'wechat'
        config: 配置字典
            - file: {'directory': '/path/to/dir'}
            - webhook: {'url': 'https://...', 'method': 'POST'}
            - email: {'smtp_host', 'smtp_port', 'username', 'password', 'to'}
            - wechat: {'token': 'pushplus_token'} 或 {'key': 'serverchan_key'}
        enabled: 是否启用
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO push_subscriptions (name, push_type, config, enabled) VALUES (?, ?, ?, ?)",
            (name, push_type, json.dumps(config, ensure_ascii=False), 1 if enabled else 0)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"[ERROR] 创建订阅失败: {e}")
        return -1
    finally:
        conn.close()


def delete_subscription(subscription_id: int) -> bool:
    """删除推送订阅"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM push_history WHERE subscription_id = ?", (subscription_id,))
        cursor.execute("DELETE FROM push_subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_subscriptions() -> List[Dict]:
    """列出所有推送订阅"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, COUNT(h.id) as push_count,
               s.last_push_at
        FROM push_subscriptions s
        LEFT JOIN push_history h ON s.id = h.subscription_id
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["config"] = json.loads(r.get("config") or "{}")
        r["enabled"] = bool(r.get("enabled"))
    return rows


def toggle_subscription(subscription_id: int, enabled: bool) -> bool:
    """启用/禁用订阅"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE push_subscriptions SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, subscription_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def list_push_history(subscription_id: int = None, limit: int = 20) -> List[Dict]:
    """查看推送历史"""
    conn = get_connection()
    cursor = conn.cursor()
    if subscription_id:
        cursor.execute("""
            SELECT h.*, s.name as subscription_name
            FROM push_history h
            JOIN push_subscriptions s ON h.subscription_id = s.id
            WHERE h.subscription_id = ?
            ORDER BY h.pushed_at DESC
            LIMIT ?
        """, (subscription_id, limit))
    else:
        cursor.execute("""
            SELECT h.*, s.name as subscription_name
            FROM push_history h
            JOIN push_subscriptions s ON h.subscription_id = s.id
            ORDER BY h.pushed_at DESC
            LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["paper_ids"] = json.loads(r.get("paper_ids") or "[]")
    return rows


# ==================== 论文筛选 ====================

def get_papers_for_push(strategy: str = "daily", top_n: int = 10,
                         field: str = None, days: int = 1) -> List[Dict]:
    """根据推送策略筛选论文

    Args:
        strategy: 'daily'/'weekly'/'field'/'top_rated'
        top_n: 推送数量
        field: 领域（strategy='field'时使用）
        days: 时间范围（天数）
    """
    conn = get_connection()
    cursor = conn.cursor()

    if strategy == "daily":
        # 当天导入的高质量论文
        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
                   p.abstract, p.fields, p.url, p.created_at,
                   r.overall_score, r.rating_level
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            WHERE p.created_at >= datetime('now', ?)
            ORDER BY r.overall_score DESC, p.citations DESC
            LIMIT ?
        """, (f'-{days} days', top_n))

    elif strategy == "weekly":
        # 一周内的高质量论文
        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
                   p.abstract, p.fields, p.url, p.created_at,
                   r.overall_score, r.rating_level
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            WHERE p.created_at >= datetime('now', ?)
            ORDER BY r.overall_score DESC, p.citations DESC
            LIMIT ?
        """, (f'-{days * 7} days', top_n))

    elif strategy == "field" and field:
        # 指定领域的高质量论文
        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
                   p.abstract, p.fields, p.url, p.created_at,
                   r.overall_score, r.rating_level
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            WHERE p.fields LIKE ?
            ORDER BY r.overall_score DESC, p.citations DESC
            LIMIT ?
        """, (f'%"{field}"%', top_n))

    elif strategy == "top_rated":
        # 全库Top评分
        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
                   p.abstract, p.fields, p.url, p.created_at,
                   r.overall_score, r.rating_level
            FROM papers p
            JOIN ratings r ON p.id = r.paper_id
            ORDER BY r.overall_score DESC
            LIMIT ?
        """, (top_n,))

    else:
        # 默认：最新高质量
        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.journal, p.year, p.citations,
                   p.abstract, p.fields, p.url, p.created_at,
                   r.overall_score, r.rating_level
            FROM papers p
            LEFT JOIN ratings r ON p.id = r.paper_id
            ORDER BY p.created_at DESC, r.overall_score DESC
            LIMIT ?
        """, (top_n,))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 解析JSON字段
    for r in rows:
        try:
            r["authors"] = json.loads(r.get("authors") or "[]")
        except:
            r["authors"] = []
        try:
            r["fields"] = json.loads(r.get("fields") or "[]")
        except:
            r["fields"] = []

    return rows


# ==================== 推送执行 ====================

def _format_push_content(papers: List[Dict], strategy: str) -> str:
    """格式化推送内容"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    strategy_names = {
        "daily": "每日推荐",
        "weekly": "本周精选",
        "field": "领域更新",
        "top_rated": "Top评分",
    }
    title = f"📚 论文{strategy_names.get(strategy, '推荐')} - {now}"

    lines = [title, "=" * 40, ""]

    for i, p in enumerate(papers, 1):
        level = p.get('rating_level') or '?'
        score = p.get('overall_score') or 0
        title = (p.get('title') or '')[:60]
        journal = (p.get('journal') or '')[:30]
        year = p.get('year') or ''
        citations = p.get('citations', 0)

        lines.append(f"{i}. [{level}] {title}")
        lines.append(f"   评分:{score:.1f} | {journal} ({year}) | 引用:{citations}")
        if p.get('abstract'):
            abstract = p['abstract'][:100].replace('\n', ' ')
            lines.append(f"   摘要: {abstract}...")
        lines.append("")

    lines.append(f"\n共 {len(papers)} 篇论文")
    lines.append(f"来自 Paper Analysis Engine")
    return "\n".join(lines)


def _push_file(papers: List[Dict], config: Dict, strategy: str) -> Dict:
    """本地文件推送"""
    directory = config.get("directory", str(PUSH_DIR))
    os.makedirs(directory, exist_ok=True)

    now = datetime.now()
    filename = f"push_{strategy}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(directory, filename)

    content = _format_push_content(papers, strategy)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return {"status": "success", "filepath": filepath, "filename": filename}


def _push_webhook(papers: List[Dict], config: Dict, strategy: str) -> Dict:
    """Webhook推送（企业微信/钉钉/飞书/自定义）"""
    url = config.get("url")
    if not url:
        return {"status": "error", "message": "webhook url未配置"}

    content = _format_push_content(papers, strategy)

    # 自动适配不同平台
    headers = {"Content-Type": "application/json"}
    payload = {}

    if "qyapi.weixin.qq.com" in url:
        # 企业微信
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
    elif "oapi.dingtalk.com" in url:
        # 钉钉
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": f"论文推荐 {datetime.now().strftime('%m-%d')}", "text": content}
        }
    elif "open.feishu.cn" in url:
        # 飞书
        payload = {
            "msg_type": "text",
            "content": {"text": content}
        }
    else:
        # 通用
        payload = {
            "text": content,
            "papers": [{"id": p["id"], "title": p.get("title")} for p in papers],
            "strategy": strategy,
            "pushed_at": datetime.now().isoformat(),
        }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            return {"status": "success", "response": resp.text[:200]}
        else:
            return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _push_wechat(papers: List[Dict], config: Dict, strategy: str) -> Dict:
    """微信推送（通过Server酱/PushPlus）"""
    content = _format_push_content(papers, strategy)
    title = f"论文推荐 {datetime.now().strftime('%m-%d %H:%M')}"

    # PushPlus
    token = config.get("token")
    if token:
        try:
            resp = requests.post(
                "http://www.pushplus.plus/send",
                json={
                    "token": token,
                    "title": title,
                    "content": content,
                    "template": "markdown"
                },
                timeout=15
            )
            data = resp.json()
            if data.get("code") == 200:
                return {"status": "success", "response": data}
            else:
                return {"status": "error", "message": data.get("msg", "未知错误")}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # Server酱
    key = config.get("key")
    if key:
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": content},
                timeout=15
            )
            data = resp.json()
            if data.get("code") == 0:
                return {"status": "success", "response": data}
            else:
                return {"status": "error", "message": data.get("message", "未知错误")}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "未配置token或key"}


def _push_email(papers: List[Dict], config: Dict, strategy: str) -> Dict:
    """邮件推送"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = config.get("smtp_host")
    smtp_port = config.get("smtp_port", 465)
    username = config.get("username")
    password = config.get("password")
    to_email = config.get("to")

    if not all([smtp_host, username, password, to_email]):
        return {"status": "error", "message": "邮件配置不完整"}

    content = _format_push_content(papers, strategy)
    title = f"论文推荐 - {datetime.now().strftime('%Y-%m-%d')}"

    msg = MIMEMultipart()
    msg["From"] = username
    msg["To"] = to_email
    msg["Subject"] = title
    msg.attach(MIMEText(content, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            server.login(username, password)
            server.sendmail(username, [to_email], msg.as_string())
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_push(subscription_id: int, strategy: str = "daily",
                  top_n: int = 10, field: str = None) -> Dict:
    """执行一次推送"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM push_subscriptions WHERE id = ?", (subscription_id,))
    sub = cursor.fetchone()
    if not sub:
        conn.close()
        return {"status": "error", "message": "订阅不存在"}

    sub = dict(sub)
    sub["config"] = json.loads(sub.get("config") or "{}")
    if not sub.get("enabled"):
        conn.close()
        return {"status": "skipped", "message": "订阅已禁用"}

    conn.close()

    # 筛选论文
    papers = get_papers_for_push(strategy=strategy, top_n=top_n, field=field, days=1)
    if not papers:
        return {"status": "empty", "message": "没有符合条件的论文"}

    # 执行推送
    push_type = sub["push_type"]
    config = sub["config"]

    if push_type == "file":
        result = _push_file(papers, config, strategy)
    elif push_type == "webhook":
        result = _push_webhook(papers, config, strategy)
    elif push_type == "wechat":
        result = _push_wechat(papers, config, strategy)
    elif push_type == "email":
        result = _push_email(papers, config, strategy)
    else:
        result = {"status": "error", "message": f"未知推送类型: {push_type}"}

    # 记录推送历史
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO push_history (subscription_id, paper_count, paper_ids, status, pushed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (subscription_id, len(papers),
         json.dumps([p["id"] for p in papers], ensure_ascii=False),
         result.get("status", "unknown"),
         datetime.now().isoformat())
    )
    # 更新最后推送时间
    cursor.execute(
        "UPDATE push_subscriptions SET last_push_at = ? WHERE id = ?",
        (datetime.now().isoformat(), subscription_id)
    )
    conn.commit()
    conn.close()

    result["paper_count"] = len(papers)
    result["subscription_name"] = sub["name"]
    return result


def execute_all_due() -> List[Dict]:
    """执行所有到期的推送（用于定时任务）"""
    subs = list_subscriptions()
    results = []
    for sub in subs:
        if not sub["enabled"]:
            continue
        # 简化：每个订阅都执行一次
        config = sub["config"]
        strategy = config.get("strategy", "daily")
        top_n = config.get("top_n", 10)
        field = config.get("field")
        result = execute_push(sub["id"], strategy=strategy, top_n=top_n, field=field)
        result["subscription_id"] = sub["id"]
        results.append(result)
    return results


# ==================== 定时任务入口 ====================

def run_scheduler_once():
    """执行一次定时任务（用于cron/计划任务调用）"""
    print(f"[{datetime.now()}] 执行定时推送...")
    results = execute_all_due()
    success = sum(1 for r in results if r.get("status") == "success")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    empty = sum(1 for r in results if r.get("status") == "empty")
    failed = len(results) - success - skipped - empty
    print(f"  完成: 成功{success} 跳过{skipped} 空数据{empty} 失败{failed}")
    return results


def start_scheduler(interval_minutes: int = 60):
    """启动定时器（阻塞执行，用于常驻进程）

    Args:
        interval_minutes: 检查间隔（分钟）
    """
    print(f"定时推送服务已启动，每 {interval_minutes} 分钟检查一次")
    print(f"按 Ctrl+C 停止")

    while True:
        try:
            run_scheduler_once()
        except Exception as e:
            print(f"[ERROR] 定时任务异常: {e}")

        # 等待下次
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    import sys
    import argparse

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="定时推送模块")
    parser.add_argument("--test", action="store_true", help="测试一次推送")
    parser.add_argument("--serve", action="store_true", help="启动定时服务")
    parser.add_argument("--interval", type=int, default=60, help="检查间隔（分钟）")
    parser.add_argument("--list", action="store_true", help="列出订阅")
    parser.add_argument("--create-file-sub", action="store_true", help="创建本地文件订阅")
    args = parser.parse_args()

    if args.list:
        print("推送订阅列表:")
        for s in list_subscriptions():
            print(f"  [{s['id']}] {s['name']} ({s['push_type']}) 启用={s['enabled']} 推送次数={s['push_count']}")
    elif args.create_file_sub:
        sid = create_subscription("每日文件推送", "file",
                                    {"directory": str(PUSH_DIR), "strategy": "daily", "top_n": 10})
        print(f"已创建订阅 ID={sid}")
    elif args.test:
        # 创建测试订阅并推送
        subs = list_subscriptions()
        if subs:
            result = execute_push(subs[0]["id"], strategy="daily", top_n=5)
            print(f"推送结果: {result}")
        else:
            sid = create_subscription("测试推送", "file", {})
            result = execute_push(sid, strategy="daily", top_n=5)
            print(f"推送结果: {result}")
    elif args.serve:
        start_scheduler(args.interval)
    else:
        parser.print_help()
