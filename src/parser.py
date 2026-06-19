"""LawRefBook 法律 markdown 通用解析器。

LawRefBook 的 markdown 格式（各部法律基本一致）：
- `# 中华人民共和国XX法`         法律名（每个文件第一个一级标题）
- `# 总则` / `# 物权编` ...       编（仅民法典等少数法律有，作为后续一级标题）
- `## 第一章 ...`                章
- `### 第一节 ...`               节
- 标题与正文之间有制定/修正日期等元信息，以 `<!-- INFO END -->` 结尾
- 条文：`第一条 ...`，**一条可能跨多个自然段**（段间空行），需全部收入正文

解析成统一 schema（LawArticle），按「条」为最小单元切分。解析器是通用的，
新增任何一部 LawRefBook 法律都无需改代码（见 law_catalog.py）。
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class LawArticle:
    """统一的法律条文数据结构（通用 schema，可扩展到任意法律）。"""
    law_name: str              # 法律名称，如"中华人民共和国民法典""中华人民共和国公司法"
    part: str                  # 编，如"总则"（无编的法律为空）
    chapter: str = ""          # 章，如"第一章 基本规定"
    section: str = ""          # 节，如"第一节 监护"
    article_no: int = 0        # 条号（数字），如 1、101
    sub_no: int = 0            # 附加条序号："第X条之一"→1，"之二"→2，普通条为 0
    article_text: str = ""     # 条文正文（含多段）
    effective_date: str = ""   # 生效日期

    @property
    def article_label(self) -> str:
        """可读条号，如"第133条""第133条之一"。"""
        base = f"第{self.article_no}条"
        return base + (f"之{_int_to_cn(self.sub_no)}" if self.sub_no else "")


# 条文起始行：第X条 / 第X条之一（X 支持中文或阿拉伯数字），其后须接空白
_ARTICLE_HEAD_RE = re.compile(r'^第([一二三四五六七八九十百千零\d]+)条(之[一二三四五六七八九十]+)?[\s　]+(.*)$')


def parse_law_markdown(
    md_path: Path,
    law_name: Optional[str] = None,
    effective_date: str = "",
) -> List[LawArticle]:
    """解析一部 LawRefBook 法律 markdown，按条切分（正确处理多段条文）。

    Args:
        md_path: markdown 文件路径
        law_name: 法律名；为 None 时从文件第一个 `# 标题` 自动识别
        effective_date: 生效日期（写入每条）
    """
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    articles: List[LawArticle] = []
    part = ""
    chapter = ""
    section = ""
    seen_law_title = False  # 第一个 `#` 是法律名，其后的 `#` 才是「编」

    cur: Optional[LawArticle] = None      # 正在累积正文的条文
    cur_paragraphs: List[str] = []        # 当前条文的各段

    def _flush():
        nonlocal cur, cur_paragraphs
        if cur is not None:
            cur.article_text = "\n".join(p for p in cur_paragraphs if p).strip()
            articles.append(cur)
        cur = None
        cur_paragraphs = []

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue

        # 一级标题：法律名（首个）或编（后续）
        if line.startswith("# "):
            _flush()
            title = line[2:].strip()
            if not seen_law_title:
                seen_law_title = True
                if law_name is None:
                    law_name = title
                # 法律名这一行不算编
            else:
                part = title
                chapter = ""
                section = ""
            continue

        # 二级标题：章
        if line.startswith("## "):
            _flush()
            chapter = line[3:].strip()
            section = ""
            continue

        # 三级标题：节
        if line.startswith("### "):
            _flush()
            section = line[4:].strip()
            continue

        # 条文起始行
        m = _ARTICLE_HEAD_RE.match(line)
        if m:
            _flush()
            cn_num, suffix, text = m.groups()
            article_no = _num_to_int(cn_num)
            sub_no = chinese_to_arabic(suffix[1:]) if suffix else 0
            cur = LawArticle(
                law_name=law_name or "",
                part=part,
                chapter=chapter,
                section=section,
                article_no=article_no,
                sub_no=sub_no,
                article_text="",
                effective_date=effective_date,
            )
            cur_paragraphs = [text]
            continue

        # 其它正文行：若正在某条文内，作为该条的续段累积；否则（标题前的日期等元信息）忽略
        if cur is not None:
            cur_paragraphs.append(line)

    _flush()
    return articles


def _num_to_int(s: str) -> int:
    """条号转 int：阿拉伯数字直接转，中文数字走 chinese_to_arabic。"""
    if s.isdigit():
        return int(s)
    return chinese_to_arabic(s)


_CN_DIGITS = "零一二三四五六七八九"


def _int_to_cn(n: int) -> str:
    """小整数转中文（仅用于"之一/之二"等附加条序号，n 一般 1~12）。"""
    if n <= 0:
        return ""
    if n <= 10:
        return "十" if n == 10 else _CN_DIGITS[n]
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    tens, ones = divmod(n, 10)
    return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")


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


# ---- 民法典专用包装（按编拆分的多文件目录，整体接入）----

def parse_civil_code_markdown(md_path: Path) -> List[LawArticle]:
    """解析民法典单个 markdown（按编拆分的文件之一），固定 law_name 与生效日期。"""
    return parse_law_markdown(
        md_path,
        law_name="中华人民共和国民法典",
        effective_date="2021-01-01",
    )


def parse_all_civil_code(data_dir: Path) -> List[LawArticle]:
    """解析 data_dir 下所有民法典 markdown（总则、物权编……），合并返回。"""
    all_articles = []
    for md_file in sorted(data_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        all_articles.extend(parse_civil_code_markdown(md_file))
    return all_articles


def save_to_json(articles: List[LawArticle], out_path: Path):
    """保存为 JSON（便于后续检查、调试、复用）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump([asdict(a) for a in articles], f, ensure_ascii=False, indent=2)

