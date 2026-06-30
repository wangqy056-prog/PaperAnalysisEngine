"""论文导入脚本 - 从多个数据源导入论文并自动评级"""

import sys
import argparse

# Windows 控制台 UTF-8 编码修复（处理论文标题中的特殊字符）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from db import init_db, insert_paper, insert_rating, get_stats
from paper_fetcher import PaperFetcher
from rating_engine import rate_paper, generate_tags, predict_commercialization


def import_topic(topic: str, limit: int = 50, sources: list = None, rate: bool = True):
    """
    按主题导入论文
    
    Args:
        topic: 搜索主题关键词
        limit: 每个数据源的最大论文数
        sources: 数据源列表 ['ss', 'oa', 'arxiv']
        rate: 是否自动评级
    """
    print(f"\n{'='*60}")
    print(f"  论文导入工具")
    print(f"  主题: {topic}")
    print(f"  数量: {limit}")
    print(f"  数据源: {sources or ['Semantic Scholar', 'OpenAlex', 'arXiv']}")
    print(f"{'='*60}\n")

    # 初始化数据库
    init_db()

    # 搜索论文
    fetcher = PaperFetcher()
    papers = fetcher.search(topic, limit, sources)

    if not papers:
        print("\n[!] 未找到任何论文，请检查网络连接或关键词")
        return 0

    # 存储论文
    stored = 0
    rated = 0

    for i, paper in enumerate(papers, 1):
        title_short = (paper.get("title") or "")[:50]
        print(f"  [{i}/{len(papers)}] 导入: {title_short}...", end=" ")

        if insert_paper(paper):
            stored += 1

            # 自动评级
            if rate:
                ratings = rate_paper(paper)
                overall = insert_rating(paper["id"], ratings)
                rated += 1
                level = ratings["rating_level"]
                score = ratings["overall_score"]
                print(f"OK [{level}] {score}")
            else:
                print("OK")
        else:
            print("FAIL")

    # 统计
    stats = get_stats()
    print(f"\n{'='*60}")
    print(f"  导入完成")
    print(f"  搜索结果: {len(papers)} 篇")
    print(f"  成功导入: {stored} 篇")
    print(f"  完成评级: {rated} 篇")
    print(f"  数据库总计: {stats['total_papers']} 篇论文, {stats['total_ratings']} 条评级")

    if stats.get("level_distribution"):
        print(f"\n  评级分布:")
        for level in ["S", "A", "B", "C", "D"]:
            count = stats["level_distribution"].get(level, 0)
            if count:
                bar = "#" * min(count, 20)
                print(f"    {level}: {bar} {count}")

    print(f"{'='*60}")
    return stored


def import_by_doi(doi: str):
    """通过DOI导入单篇论文"""
    print(f"\n  通过DOI导入: {doi}")

    init_db()
    fetcher = PaperFetcher()

    # 先用Semantic Scholar查
    paper = fetcher.ss.get_paper(f"DOI:{doi}")

    if not paper:
        print("  [!] 未找到该DOI对应的论文")
        return False

    if insert_paper(paper):
        ratings = rate_paper(paper)
        insert_rating(paper["id"], ratings)

        print(f"\n  标题: {paper['title']}")
        print(f"  作者: {', '.join(paper['authors'][:3])}")
        print(f"  期刊: {paper.get('journal', 'N/A')}")
        print(f"  年份: {paper.get('year', 'N/A')}")
        print(f"  引用: {paper.get('citations', 0)}")
        print(f"\n  评级结果:")
        print(f"    综合评分: {ratings['overall_score']} [{ratings['rating_level']}]")
        print(f"    学术影响力: {ratings['academic_impact']}")
        print(f"    商业潜力:   {ratings['commercial_potential']}")
        print(f"    创新指数:   {ratings['innovation_index']}")
        print(f"    可复现性:   {ratings['reproducibility']}")
        print(f"    组合价值:   {ratings['combo_value']}")

        comm = predict_commercialization(paper)
        print(f"\n  商业化预测: TRL {comm['trl']} → {comm['base_time']} (置信度: {comm['confidence']})")

        tags = generate_tags(paper)
        print(f"\n  自动标签:")
        for tag in tags:
            print(f"    [{tag['category']}] {tag['name']} ({tag['confidence']})")

        return True
    else:
        print("  [!] 存储失败")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="论文导入工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 按主题导入
    topic_parser = subparsers.add_parser("topic", help="按主题导入论文")
    topic_parser.add_argument("query", help="搜索关键词")
    topic_parser.add_argument("-n", "--limit", type=int, default=30, help="每个数据源最大数量 (默认30)")
    topic_parser.add_argument("-s", "--sources", nargs="+", choices=["ss", "oa", "arxiv"],
                               default=["ss", "oa"], help="数据源 (默认 ss+oa)")
    topic_parser.add_argument("--no-rate", action="store_true", help="不自动评级")

    # 按DOI导入
    doi_parser = subparsers.add_parser("doi", help="按DOI导入单篇论文")
    doi_parser.add_argument("doi", help="论文DOI号")

    args = parser.parse_args()

    if args.command == "topic":
        import_topic(args.query, args.limit, args.sources, rate=not args.no_rate)
    elif args.command == "doi":
        import_by_doi(args.doi)
    else:
        parser.print_help()
