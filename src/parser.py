"""民法典 markdown 解析器。

LawRefBook 的 markdown 格式：
- 标题层级：`# 中华人民共和国民法典` / `# 总则` (编) / `## 第一章 基本规定` (章) / `### 第一节 监护` (节)
- 条文：`第一条 ...` / `第一百零一条 ...`，每条是一个段落

解析成统一 schema，按"条"为最小单元切分。
"""
import re
import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, asdict


@dataclass
class LawArticle:
    """统一的法律条文数据结构（通用 schema，可扩展到其他法律）。"""
    law_name: str              # 法律名称，如"中华人民共和国民法典"
    part: str                  # 编，如"总则"
    chapter: str = ""          # 章，如"第一章 基本规定"
    section: str = ""          # 节，如"第一节 监护"
    article_no: int = 0        # 条号（数字），如 1、101
    article_text: str = ""     # 条文正文
    effective_date: str = "2021-01-01"  # 民法典生效日期


def parse_civil_code_markdown(md_path: Path) -> List[LawArticle]:
    """解析 LawRefBook 民法典 markdown 文件，按条切分。"""
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    articles = []
    law_name = "中华人民共和国民法典"
    part = ""           # 当前编
    chapter = ""        # 当前章
    section = ""        # 当前节

    # 逐行扫描，维护当前的编/章/节状态，遇到"第X条"开头的段落就提取
    for line in lines:
        line = line.strip()
        if not line or line.startswith("<!--"):
            continue

        # 一级标题：法律名或编（总则、物权编等）
        if line.startswith("# "):
            title = line[2:].strip()
            if "民法典" not in title:  # 第二个 # 是编名
                part = title
                chapter = ""
                section = ""

        # 二级标题：章
        elif line.startswith("## "):
            chapter = line[3:].strip()
            section = ""

        # 三级标题：节
        elif line.startswith("### "):
            section = line[4:].strip()

        # 条文：以"第X条"开头（可能是"第一条"或"第一百零一条"）
        elif re.match(r'^第[一二三四五六七八九十百千零]+条\s', line):
            # 提取条号（转数字）和正文
            m = re.match(r'^第([一二三四五六七八九十百千零]+)条\s+(.+)$', line)
            if m:
                cn_num, text = m.groups()
                article_no = chinese_to_arabic(cn_num)
                articles.append(LawArticle(
                    law_name=law_name,
                    part=part,
                    chapter=chapter,
                    section=section,
                    article_no=article_no,
                    article_text=text,
                ))

    return articles


def chinese_to_arabic(cn: str) -> int:
    """中文数字 -> 阿拉伯数字（支持"第一条"到"第一千二百六十条"）。"""
    mapping = {'零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '百':100, '千':1000}
    result = 0
    tmp = 0
    for c in cn:
        val = mapping.get(c, 0)
        if val >= 10:
            tmp = tmp or 1  # "十"单独出现时当10
            result += tmp * val
            tmp = 0
        else:
            tmp = val
    return result + tmp


def parse_all_civil_code(data_dir: Path) -> List[LawArticle]:
    """解析 data/raw/ 下所有民法典 markdown 文件（总则、物权编、合同编等），合并返回。"""
    all_articles = []
    for md_file in sorted(data_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        articles = parse_civil_code_markdown(md_file)
        all_articles.extend(articles)
    return all_articles


def save_to_json(articles: List[LawArticle], out_path: Path):
    """保存为 JSON（便于后续检查、调试、复用）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump([asdict(a) for a in articles], f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    from . import config
    articles = parse_all_civil_code(config.DATA_RAW_DIR)
    print(f"解析完成：{len(articles)} 条")
    save_to_json(articles, config.DATA_PROCESSED_DIR / "civil_code.json")
    # 输出前3条看效果
    for a in articles[:3]:
        print(f"\n[{a.part} / {a.chapter}] 第{a.article_no}条\n  {a.article_text[:60]}...")
