"""临时调试脚本：分析领研网页面结构"""
import requests
import re

resp = requests.get(
    "https://www.linkresearcher.com/theses",
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    verify=False,
    timeout=15,
)
resp.encoding = "utf-8"
html = resp.text

print(f"页面长度: {len(html)}")

# 查找所有链接
all_links = re.findall(r'href="([^"]+)"', html)
thesis_links = [l for l in all_links if "theses" in l]
print(f"\n含 'theses' 的链接: {len(thesis_links)}")
for l in thesis_links[:20]:
    print(f"  {l}")

# 查找论文标题关键词
print("\n--- 查找标题相关结构 ---")
# 查找 '期刊' 附近的内容
journal_matches = list(re.finditer(r'期刊', html))
print(f"'期刊' 出现次数: {len(journal_matches)}")
if journal_matches:
    # 打印第一个匹配附近的内容
    pos = journal_matches[0].start()
    print(f"\n第一个 '期刊' 附近内容:")
    print(html[max(0, pos-200):pos+200])

# 查找日期模式
date_matches = re.findall(r'\d{4}/\d{2}/\d{2}', html)
print(f"\n日期模式: {len(date_matches)}")
for d in date_matches[:10]:
    print(f"  {d}")

# 尝试查找论文块的结构
print("\n--- 查找论文块结构 ---")
# 可能是 Vue/React 渲染的内容，查看是否有 API 调用
api_patterns = re.findall(r'(api[^"\']+)', html, re.IGNORECASE)
print(f"\nAPI 路径: {len(api_patterns)}")
for p in api_patterns[:10]:
    print(f"  {p}")

# 检查是否是 SPA（单页应用）
if '<div id="app">' in html or '<div id="root">' in html:
    print("\n⚠️ 这是 SPA 应用，论文内容由 JS 渲染，requests 抓不到！")
    print("需要用 Selenium/Playwright 或找到 API 端点")

# 查找 JSON 数据
json_patterns = re.findall(r'window\.__\w+__\s*=\s*(\{.*?\})', html, re.DOTALL)
print(f"\n内嵌 JSON 数据: {len(json_patterns)}")

# 打印 HTML 前 3000 字符看看结构
print("\n--- HTML 前 3000 字符 ---")
print(html[:3000])
