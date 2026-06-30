"""恢复导入 - 完成上次崩溃时未导入的主题"""
import sys
import time
import traceback

# Windows 控制台 UTF-8 编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from db import init_db, get_stats
from import_papers import import_topic

# 剩余待导入的主题（半导体后2个 + 机器人 + 生物医学 + 计算机系统 + 太空探索）
REMAINING_TOPICS = [
    ("半导体", "semiconductor lithography"),
    ("半导体", "wide bandgap semiconductor"),
    ("机器人", "humanoid robot"),
    ("机器人", "soft robotics"),
    ("机器人", "robot learning"),
    ("机器人", "autonomous driving"),
    ("生物医学", "Alzheimer disease biomarker"),
    ("生物医学", "cancer immunotherapy"),
    ("生物医学", "brain computer interface"),
    ("生物医学", "organoid"),
    ("计算机系统", "edge computing"),
    ("计算机系统", "federated learning"),
    ("计算机系统", "homomorphic encryption"),
    ("计算机系统", "zero knowledge proof"),
    ("太空探索", "space debris removal"),
    ("太空探索", "mars colonization"),
    ("太空探索", "reusable rocket"),
    ("太空探索", "satellite constellation"),
]


def resume(per_topic: int = 15, sources=None):
    if sources is None:
        sources = ["oa"]

    init_db()
    stats_before = get_stats()
    print(f"\n{'='*60}")
    print(f"  恢复导入 (剩余 {len(REMAINING_TOPICS)} 个主题)")
    print(f"  导入前: {stats_before['total_papers']} 篇")
    print(f"{'='*60}\n")

    total_stored = 0
    failed = []

    for i, (cat, topic) in enumerate(REMAINING_TOPICS, 1):
        print(f"\n  [{i}/{len(REMAINING_TOPICS)}] [{cat}] {topic}")
        try:
            stored = import_topic(topic, per_topic, sources, rate=True)
            total_stored += stored or 0
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            print(f"\n  [!] 主题失败: {err_msg}")
            traceback.print_exc()
            failed.append((cat, topic, err_msg))
            # 继续下一个主题，不让一个失败影响全部
        time.sleep(1)

    stats_after = get_stats()
    print(f"\n{'='*60}")
    print(f"  恢复导入完成!")
    print(f"  导入前:    {stats_before['total_papers']} 篇")
    print(f"  导入后:    {stats_after['total_papers']} 篇")
    print(f"  新增:      {stats_after['total_papers'] - stats_before['total_papers']} 篇")
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

    if failed:
        print(f"\n  失败主题 ({len(failed)} 个):")
        for cat, topic, err in failed:
            print(f"    [{cat}] {topic} - {err}")
    else:
        print(f"\n  全部主题导入成功!")

    print(f"{'='*60}")
    return total_stored


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="恢复导入剩余主题")
    parser.add_argument("-n", "--per-topic", type=int, default=15, help="每主题数量 (默认15)")
    parser.add_argument("-s", "--sources", nargs="+", choices=["ss", "oa", "arxiv"],
                        default=["oa"], help="数据源 (默认 oa)")
    args = parser.parse_args()
    resume(args.per_topic, args.sources)
