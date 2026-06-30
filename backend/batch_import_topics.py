"""多主题批量导入 - 一次性导入多个领域的论文"""

import sys
import time
from db import init_db, get_stats, get_connection
from import_papers import import_topic

# 预设主题库（覆盖主流研究领域）
TOPIC_LIBRARY = {
    "人工智能": [
        "large language models",
        "transformer architecture",
        "reinforcement learning",
        "multi-agent systems",
        "AI alignment",
    ],
    "量子计算": [
        "quantum computing",
        "quantum error correction",
        "quantum machine learning",
        "quantum cryptography",
    ],
    "生物技术": [
        "CRISPR gene editing",
        "protein folding",
        "mRNA vaccine",
        "synthetic biology",
    ],
    "材料科学": [
        "perovskite solar cell",
        "solid-state battery",
        "2D materials",
        "metamaterials",
    ],
    "新能源": [
        "hydrogen fuel cell",
        "lithium battery",
        "photovoltaic efficiency",
        "carbon capture",
    ],
    "半导体": [
        "chiplet architecture",
        "advanced packaging",
        "semiconductor lithography",
        "wide bandgap semiconductor",
    ],
    "机器人": [
        "humanoid robot",
        "soft robotics",
        "robot learning",
        "autonomous driving",
    ],
    "生物医学": [
        "Alzheimer disease biomarker",
        "cancer immunotherapy",
        "brain computer interface",
        "organoid",
    ],
    "计算机系统": [
        "edge computing",
        "federated learning",
        "homomorphic encryption",
        "zero knowledge proof",
    ],
    "太空探索": [
        "space debris removal",
        "mars colonization",
        "reusable rocket",
        "satellite constellation",
    ],
}


def batch_import(categories: list = None, per_topic: int = 20, sources: list = None):
    """
    批量导入多个主题的论文

    Args:
        categories: 要导入的分类列表，None表示全部
        per_topic: 每个主题导入数量
        sources: 数据源 ['oa', 'arxiv']
    """
    if sources is None:
        sources = ["oa"]

    if categories:
        topics_to_import = {k: v for k, v in TOPIC_LIBRARY.items() if k in categories}
    else:
        topics_to_import = TOPIC_LIBRARY

    total_topics = sum(len(v) for v in topics_to_import.values())
    total_categories = len(topics_to_import)

    print(f"\n{'='*60}")
    print(f"  多主题批量导入")
    print(f"  分类数: {total_categories}")
    print(f"  主题数: {total_topics}")
    print(f"  每主题: {per_topic} 篇")
    print(f"  预计总量: {total_topics * per_topic} 篇")
    print(f"  数据源: {sources}")
    print(f"{'='*60}\n")

    init_db()

    # 导入前的数据库状态
    stats_before = get_stats()
    print(f"  导入前: {stats_before['total_papers']} 篇论文\n")

    total_stored = 0
    total_topics_done = 0

    for cat_name, topics in topics_to_import.items():
        print(f"\n{'─'*60}")
        print(f"  分类: {cat_name} ({len(topics)} 个主题)")
        print(f"{'─'*60}")

        for topic in topics:
            total_topics_done += 1
            print(f"\n  [{total_topics_done}/{total_topics}] {topic}")

            stored = import_topic(topic, per_topic, sources, rate=True)
            total_stored += stored

            # 避免请求过快
            time.sleep(1)

    # 最终统计
    stats_after = get_stats()
    new_papers = stats_after["total_papers"] - stats_before["total_papers"]

    print(f"\n{'='*60}")
    print(f"  批量导入完成!")
    print(f"{'='*60}")
    print(f"  导入前:    {stats_before['total_papers']} 篇")
    print(f"  导入后:    {stats_after['total_papers']} 篇")
    print(f"  新增:      {new_papers} 篇")
    print(f"  评级总数:  {stats_after['total_ratings']} 条")
    print(f"  平均评分:  {stats_after['avg_score']:.1f}")
    print(f"  最高评分:  {stats_after['max_score']:.1f}")

    if stats_after.get("level_distribution"):
        print(f"\n  评级分布:")
        for level in ["S", "A", "B", "C", "D"]:
            count = stats_after["level_distribution"].get(level, 0)
            if count:
                bar = "#" * min(count, 30)
                print(f"    {level}: {bar} {count}")

    # 各分类统计
    print(f"\n  各分类论文数:")
    conn = get_connection()
    cursor = conn.cursor()
    for cat_name in topics_to_import.keys():
        topics = topics_to_import[cat_name]
        count = 0
        for topic in topics:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM papers WHERE title LIKE ? OR abstract LIKE ?",
                (f"%{topic.split()[0]}%", f"%{topic.split()[0]}%"),
            )
            count += cursor.fetchone()["cnt"]
        print(f"    {cat_name}: {count} 篇")
    conn.close()

    print(f"{'='*60}")
    return total_stored


def list_topics():
    """列出所有可用主题"""
    print(f"\n{'='*60}")
    print(f"  可用主题库 ({len(TOPIC_LIBRARY)} 个分类)")
    print(f"{'='*60}\n")

    for cat, topics in TOPIC_LIBRARY.items():
        print(f"  【{cat}】({len(topics)} 个主题)")
        for t in topics:
            print(f"    - {t}")
        print()

    total = sum(len(v) for v in TOPIC_LIBRARY.values())
    print(f"  共 {total} 个主题")
    print(f"\n  用法:")
    print(f"    python batch_import_topics.py --all -n 20")
    print(f"    python batch_import_topics.py --categories 人工智能 量子计算 -n 15")
    print(f"    python batch_import_topics.py --list")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="多主题批量导入论文")
    parser.add_argument("--all", action="store_true", help="导入所有分类")
    parser.add_argument("--categories", nargs="+", help="指定分类名称")
    parser.add_argument("-n", "--per-topic", type=int, default=20, help="每主题数量 (默认20)")
    parser.add_argument("-s", "--sources", nargs="+", choices=["ss", "oa", "arxiv"],
                        default=["oa"], help="数据源 (默认 oa)")
    parser.add_argument("--list", action="store_true", help="列出所有主题")
    parser.add_argument("--add", nargs=2, metavar=("CATEGORY", "TOPIC"), action="append",
                        help="添加自定义主题 (可多次使用)")

    args = parser.parse_args()

    if args.list:
        list_topics()
    elif args.add:
        # 动态添加主题
        for cat, topic in args.add:
            if cat not in TOPIC_LIBRARY:
                TOPIC_LIBRARY[cat] = []
            if topic not in TOPIC_LIBRARY[cat]:
                TOPIC_LIBRARY[cat].append(topic)
            print(f"  已添加: [{cat}] {topic}")
        print(f"\n  当前共 {sum(len(v) for v in TOPIC_LIBRARY.values())} 个主题")
    elif args.all or args.categories:
        batch_import(args.categories, args.per_topic, args.sources)
    else:
        parser.print_help()
