"""
교육부 위키 생성기
------------------
kordoc(parse_chunks)로 뽑아낸 청크 JSON + 메타데이터 JSON을 입력받아
나무위키 스타일 HTML 문서(목차 + 문단 구조)를 생성한다.

사용법:
    python generate_wiki.py <slug>
    (data/<slug>.chunks.json, data/<slug>.meta.json 을 읽어
     articles/<slug>.html 을 생성하고 index.html을 갱신한다)

    python generate_wiki.py --rebuild-index
    (기존 data/*.meta.json 목록만으로 index.html만 다시 생성)
"""
import json
import re
import sys
import html
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
ARTICLES_DIR = ROOT / "articles"
ASSETS_DIR = ROOT / "assets"
CATEGORIES_DIR = ROOT / "categories"
TOPICS_DIR = ROOT / "topics"
ORG_DIR = ROOT / "org"
DATA_TOPICS_DIR = DATA_DIR / "topics"
CATEGORY_MAP = json.loads((ROOT / "category_map.json").read_text(encoding="utf-8"))
ORG_CHART = json.loads((ROOT / "org_chart.json").read_text(encoding="utf-8"))
CSS_VERSION = 9  # style.css 수정할 때마다 올려서 모바일 브라우저 캐시를 무효화한다.
SUGGESTION_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScnEvpD9gdbr80YJziQmLPxqcAkw6V1sgxrQpQk9LidgnqYKw/viewform"
# 업무계획 문서 id 목록(연간/반기별). data/workplan-<id>.json 하나당 workplan-<id>.html 하나 생성.
WORKPLAN_IDS = ["2026", "2026-h2"]

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ATTACH_RE = re.compile(r"붙임\s*(\d+)")

# 나무위키식 문서 간 키워드 자동 연결.
# {"phrase": 텍스트, "targets": {소스slug: 링크할slug, ...}} — phrase가 소스 문서 본문에
# 등장하면 첫 번째 등장한 곳만 targets[소스slug]로 링크한다(자기 자신이 target이면 건너뜀).
KEYWORD_LINKS = [
    {"phrase": "포용교육 시대, 특수교육이 만들어가는 변화", "targets": {"106773": "106680"}},
    {"phrase": "계약학과", "targets": {
        "106666": "106740", "106661": "106740", "106326": "106740", "106147": "106740",
        "105790": "106740", "105889": "106740", "106235": "106740", "106579": "106740",
    }},
    {"phrase": "지역성장 인재양성", "targets": {
        "106666": "106688", "106688": "106666", "106345": "106688", "106504": "106688",
        "106145": "106688", "106278": "106688", "106307": "106688",
        "105790": "106688", "105814": "106688", "105889": "106688", "105929": "106688",
        "106106": "106688", "106147": "106688", "106235": "106688", "106740": "106688",
    }},
    {"phrase": "자기주도 학습센터", "targets": {"105742": "106582"}},
    {"phrase": "마이스터고", "targets": {"106223": "106475", "106235": "106475", "106684": "106475"}},
    {"phrase": "협약형 특성화고", "targets": {"106223": "106388", "106235": "106388"}},
    {"phrase": "직업계고-전문대학", "targets": {"105766": "106393"}},
    {"phrase": "STOB리그", "targets": {"105909": "106728"}},
    {"phrase": "육아종합지원센터", "targets": {
        "105472": "106030", "105636": "106030", "105837": "106030", "106410": "106030",
    }},
    {"phrase": "온동네 초등돌봄", "targets": {"105936": "106245", "106245": "106751"}},
    {"phrase": "거점국립대학", "targets": {
        "105889": "106463", "105943": "106463", "106221": "106463", "106790": "106463",
    }},
    {"phrase": "성장엔진 연계 지역인재 양성방안", "targets": {"105889": "106463", "105967": "106463"}},
    {"phrase": "모두의 한국어", "targets": {"105835": "106222", "106222": "106690", "106235": "106690"}},
    {"phrase": "글로컬대학", "targets": {"106422": "106254", "106467": "106254", "106590": "106254"}},
    {"phrase": "고등교육혁신특화지역", "targets": {"106326": "106422", "106467": "106422"}},
    {"phrase": "첨단산업 인재양성 부트캠프", "targets": {
        "105764": "106424", "105939": "106424", "106021": "106424",
        "106147": "106424", "106235": "106424", "106666": "106424",
        "106846": "106424", "106878": "106424",
    }},
    {"phrase": "청년도약 인재양성 부트캠프", "targets": {
        "105856": "106478", "106021": "106478", "106424": "106478", "106846": "106478",
    }},
    {"phrase": "한국교육원", "targets": {
        "106806": "106749", "106749": "106806", "106603": "106806", "105666": "106603",
        "106879": "106806", "106888": "106806",
    }},
    {"phrase": "데이터로 읽는 우리 교육", "targets": {
        "106680": "106773", "106436": "106571", "106571": "106680",
        "106054": "106180", "106180": "106324", "106324": "106436",
        "105614": "105736", "105736": "105924", "105924": "106054",
        "106773": "106880",
    }},
]


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def inline_format(line: str) -> str:
    line = esc(line)
    line = BOLD_RE.sub(r"<strong>\1</strong>", line)
    return line


def render_prose(text: str) -> str:
    """일반 텍스트(굵게/글머리표/문단)를 HTML로 변환."""
    paras = [p for p in text.split("\n\n") if p.strip()]
    out = []
    for para in paras:
        lines = [l for l in para.split("\n") if l.strip()]
        if all(re.match(r"^[▪‣\-]\s+", l) for l in lines) and len(lines) > 1:
            stripped = [re.sub(r"^[▪‣\-]\s+", "", l) for l in lines]
            items = "".join(f"<li>{inline_format(s)}</li>" for s in stripped)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>".join(inline_format(l) for l in lines) + "</p>")
    return "\n".join(out)


def render_pipe_table(text: str) -> str:
    rows = [r for r in text.split("\n") if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|[\s:\-|]+\|$", r.strip())]
    out = ["<table class='wiki-table'>"]
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        out.append("<tr>" + "".join(f"<td>{inline_format(c)}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def render_chunk_body(text: str) -> str:
    if "<table" in text:
        return f"<div class='table-scroll'>{text}</div>"
    if re.search(r"^\s*\|.*\|\s*$", text, re.MULTILINE):
        return f"<div class='table-scroll'>{render_pipe_table(text)}</div>"
    return render_prose(text)


IMAGE_MD_RE = re.compile(r"!\[image\]\([^)]*\)")


def is_logo_header(text: str) -> bool:
    if "보도자료" not in text:
        return False
    stripped = IMAGE_MD_RE.sub("", text)
    stripped = re.sub(r"[|\-\s]", "", stripped)
    return len(stripped) < 20


def is_date_meta(text: str) -> bool:
    return "배포" in text and "보도시점" in text


def is_title_chunk(text: str, title: str) -> bool:
    """제목을 그대로 반복하는 '표제 문단'인지 확인. 본문 중간에 제목 일부 단어가
    우연히 재등장하는 것과 구별하기 위해, 문단이 제목으로 '시작'하는지만 본다."""
    return text.replace("\n", "").strip().startswith(title[:12])


def is_contact_table(text: str) -> bool:
    return "책임자" in text and "담당자" in text


def parse_html_table(text: str):
    rows = re.findall(r"<tr>(.*?)</tr>", text, re.DOTALL)
    result = []
    for r in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.DOTALL)
        cells = [re.sub(r"<br\s*/?>", "\n", c) for c in cells]
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        result.append(cells)
    return result


def parse_pipe_table(text: str):
    rows = [r for r in text.split("\n") if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|[\s:\-|]+\|$", r.strip())]
    return [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]


def attachment_label(text: str) -> str | None:
    m = ATTACH_RE.search(text)
    if m and "|" in text:
        # 셀에서 설명 텍스트 추출 (예: "| 붙임 1 |  | 개요 |")
        cells = [c.strip() for c in text.strip().strip("|").split("\n")[0].split("|")]
        cells = [c for c in cells if c]
        desc = cells[-1] if cells else ""
        return f"붙임 {m.group(1)}. {desc}".strip()
    return None


def load_chunks(slug: str) -> list[dict]:
    """data/<slug>.chunks.json(구조화 JSON) 또는 data/<slug>.md(원본 마크다운) 중
    있는 쪽을 읽어 {"text": ...} 청크 리스트로 변환."""
    chunks_path = DATA_DIR / f"{slug}.chunks.json"
    if chunks_path.exists():
        return json.loads(chunks_path.read_text(encoding="utf-8"))
    md_path = DATA_DIR / f"{slug}.md"
    text = md_path.read_text(encoding="utf-8")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    return [{"text": b} for b in blocks]


def extract_contact(chunks: list[dict]):
    """담당부서 표 청크에서 (bureau, division, contact) 추출.
    "책임자" 셀 바로 왼쪽 셀이 조직명(실/국/관, 때로는 <br>로 과까지 함께)이라는
    규칙으로 위치를 찾는다 — 단독 보도자료/공동(타부처) 보도자료 두 형식 모두 대응.
    표에 여러 부처가 함께 있으면 맨 처음(교육부) 블록만 사용한다."""
    for ch in chunks:
        text = ch.get("text", "")
        if not is_contact_table(text):
            continue
        parsed = parse_html_table(text) if "<table" in text else parse_pipe_table(text)
        parsed = [r for r in parsed if any(r)]
        if not parsed:
            continue

        def resp_col(row):
            return next((i for i, c in enumerate(row) if "책임자" in c), None)

        header_idx = next((i for i, r in enumerate(parsed) if resp_col(r) is not None), 0)
        header_row = parsed[header_idx]
        ri = resp_col(header_row)
        org_cell = header_row[ri - 1] if ri and ri > 0 else (header_row[1] if len(header_row) > 1 else "")

        if "\n" in org_cell:
            parts = [p for p in org_cell.split("\n") if p.strip()]
            bureau = parts[0]
            division = parts[1] if len(parts) > 1 else parts[0]
        else:
            bureau = org_cell
            division = bureau
            if header_idx + 1 < len(parsed):
                nxt = parsed[header_idx + 1]
                idx = ri - 1 if ri else 1
                if len(nxt) > idx >= 0 and nxt[idx].strip():
                    division = nxt[idx]

        contact = ""
        if header_idx + 1 < len(parsed):
            nxt = parsed[header_idx + 1]
            if len(nxt) >= 2:
                phone = nxt[-1] if re.search(r"\d{2,}", nxt[-1]) else ""
                name = nxt[-2] if phone else ""
                contact = " ".join(p for p in [name, phone] if p)
        if not contact and len(header_row) >= 2:
            phone = header_row[-1] if re.search(r"\d{2,}", header_row[-1]) else ""
            name = header_row[-2] if phone else ""
            contact = " ".join(p for p in [name, phone] if p)
        return bureau, division, contact
    return "", "", ""


def classify(bureau: str, division: str):
    """조직명을 (대분류, 중분류)로 매핑. 못 찾으면 (미분류, None)."""
    dmap = CATEGORY_MAP["division_map"]
    bmap = CATEGORY_MAP["bureau_map"]
    if division in dmap:
        main, sub = dmap[division]
        return main, sub
    if bureau in bmap:
        main, sub = bmap[bureau]
        return main, sub
    return "미분류", None


def build_sections(chunks: list[dict], title: str):
    """청크 목록을 (개요 섹션 + 붙임 섹션들)으로 분할."""
    sections = []
    current_name = "개요"
    current_chunks = []
    seen_contact = False

    for ch in chunks:
        text = ch.get("text", "")
        if not seen_contact and (is_logo_header(text) or is_date_meta(text) or is_title_chunk(text, title)):
            continue
        if not seen_contact and is_contact_table(text):
            seen_contact = True
            continue
        label = attachment_label(text)
        if label:
            if current_chunks:
                sections.append((current_name, current_chunks))
            current_name = label
            current_chunks = []
            continue
        current_chunks.append(ch)
    if current_chunks:
        sections.append((current_name, current_chunks))
    return sections


PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 교육부 위키</title>
<link rel="stylesheet" href="../assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="../index.html">교육부 위키</a> &gt; {category_path}</div>
  <h1 class="wiki-title">{title}</h1>
  <div class="wiki-subtitle">{subtitle}</div>
{background_block}
  <table class="infobox">
    <tr><th>배포일</th><td>{date}</td></tr>
    <tr><th>담당부서</th><td>{dept}</td></tr>
    <tr><th>담당자</th><td>{contact}</td></tr>
    <tr><th>출처</th><td><a href="{source_url}" target="_blank" rel="noopener">교육부 보도자료 원문 ↗</a></td></tr>
  </table>

  <div class="toc">
    <div class="toc-title">목차</div>
    <ol>
{toc_items}
    </ol>
  </div>

{body}

  <div class="wiki-footer">
    <a href="../index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


def apply_keyword_links(slug: str, text: str) -> str:
    """KEYWORD_LINKS에 정의된 문구가 본문에 있으면 첫 등장만 다른 문서로 링크."""
    for entry in KEYWORD_LINKS:
        target = entry["targets"].get(slug)
        if not target or target == slug:
            continue
        phrase_html = esc(entry["phrase"])
        if phrase_html in text:
            link = f'<a href="{target}.html">{phrase_html}</a>'
            text = text.replace(phrase_html, link, 1)
    return text


def category_link(main: str, sub: str | None) -> str:
    cat = next((c for c in CATEGORY_MAP["categories"] if c["name"] == main), None)
    cid = cat["id"] if cat else "uncategorized"
    path = f'<a href="../categories/{cid}.html">{esc(main)}</a>'
    if sub:
        path += f" &gt; {esc(sub)}"
    return path


def render_article(slug: str):
    meta = json.loads((DATA_DIR / f"{slug}.meta.json").read_text(encoding="utf-8"))
    chunks = load_chunks(slug)

    sections = build_sections(chunks, meta["title"])
    main_cat, sub_cat = classify(meta.get("bureau", ""), meta.get("division", ""))
    dept = " ".join(p for p in [meta.get("bureau", ""), meta.get("division", "")] if p) or "미상"

    background_block = ""
    if meta.get("background"):
        bg_html = apply_keyword_links(slug, render_prose(meta["background"]))
        background_block = f'  <div class="wiki-background">{bg_html}</div>'

    toc_items = []
    body_parts = []
    for i, (name, chs) in enumerate(sections, 1):
        anchor = f"sec{i}"
        toc_items.append(f'      <li><a href="#{anchor}">{esc(name)}</a></li>')
        section_html = "\n".join(render_chunk_body(c["text"]) for c in chs)
        body_parts.append(
            f'  <h2 id="{anchor}">{i}. {esc(name)}</h2>\n{section_html}'
        )
    body = apply_keyword_links(slug, "\n\n".join(body_parts))

    html_out = PAGE_TEMPLATE.format(
        css_ver=CSS_VERSION,
        title=esc(meta["title"]),
        subtitle=esc(meta.get("subtitle", "")),
        category_path=category_link(main_cat, sub_cat),
        background_block=background_block,
        date=esc(meta.get("date", "")),
        dept=esc(dept),
        contact=esc(meta.get("contact", "")),
        source_url=meta.get("source_url", "#"),
        toc_items="\n".join(toc_items),
        body=body,
    )
    ARTICLES_DIR.mkdir(exist_ok=True)
    out_path = ARTICLES_DIR / f"{slug}.html"
    out_path.write_text(html_out, encoding="utf-8")
    return meta, out_path


TOPIC_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 교육부 위키</title>
<link rel="stylesheet" href="../assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="../index.html">교육부 위키</a> &gt; 정책 위키</div>
  <h1 class="wiki-title">{title}</h1>
  <div class="wiki-subtitle">{subtitle}</div>
  <div class="topic-meta">다루는 기간 {period} · 관련 보도자료 {count}건</div>

  <div class="toc">
    <div class="toc-title">목차</div>
    <ol>
{toc_items}
    </ol>
  </div>

{body}

  <h2 id="related">관련 보도자료</h2>
  <div class="doc-card-list">
{related_rows}
  </div>

  <div class="wiki-footer">
    <a href="../index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


def render_topic(topic_id: str):
    """data/topics/<topic_id>.json(수기로 종합 작성한 주제별 정책 문서)을 읽어
    topics/<topic_id>.html 을 생성한다. 개별 보도자료 문서(render_article)와 달리
    kordoc 청크가 아니라, 여러 보도자료를 종합해 사람이(Claude가) 직접 쓴 섹션들을 렌더링한다."""
    topic = json.loads((DATA_TOPICS_DIR / f"{topic_id}.json").read_text(encoding="utf-8"))

    toc_items = []
    body_parts = []
    for i, sec in enumerate(topic["sections"], 1):
        anchor = f"sec{i}"
        toc_items.append(f'      <li><a href="#{anchor}">{esc(sec["heading"])}</a></li>')
        body_parts.append(f'  <h2 id="{anchor}">{i}. {esc(sec["heading"])}</h2>\n{render_prose(sec["body"])}')
    toc_items.append('      <li><a href="#related">관련 보도자료</a></li>')

    related_rows = []
    for seq in topic["related"]:
        meta = json.loads((DATA_DIR / f"{seq}.meta.json").read_text(encoding="utf-8"))
        related_rows.append(
            f'    <a class="doc-card" href="../articles/{seq}.html">'
            f'<span class="doc-date">{esc(meta.get("date", ""))}</span>'
            f'<span class="doc-title">{esc(meta["title"])}</span></a>'
        )

    html_out = TOPIC_PAGE_TEMPLATE.format(
        css_ver=CSS_VERSION,
        title=esc(topic["title"]),
        subtitle=esc(topic.get("subtitle", "")),
        period=esc(topic.get("period", "")),
        count=len(topic["related"]),
        toc_items="\n".join(toc_items),
        body="\n\n".join(body_parts),
        related_rows="\n".join(related_rows),
    )
    TOPICS_DIR.mkdir(exist_ok=True)
    out_path = TOPICS_DIR / f"{topic_id}.html"
    out_path.write_text(html_out, encoding="utf-8")
    return topic, out_path


def _collect_topics():
    if not DATA_TOPICS_DIR.exists():
        return []
    topics = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(DATA_TOPICS_DIR.glob("*.json"))]
    topics.sort(key=lambda t: t.get("period", ""), reverse=True)
    return topics


ORG_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>조직도 - 교육부 위키</title>
<link rel="stylesheet" href="assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="index.html">교육부 위키</a> &gt; 조직도</div>
  <h1 class="wiki-title">교육부 조직도</h1>
  <div class="wiki-subtitle">교육부의 실제 조직 체계를 한눈에 보고, 부서별 보도자료 건수를 확인할 수 있습니다.</div>
  <p class="section-desc">숫자가 있는 과·팀을 클릭하면 그 부서 명의로 발표된 보도자료만 모아서 볼 수 있습니다.</p>

  <div class="org-tree">
{tree}
  </div>

  <div class="wiki-footer">
    <a href="index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


ORG_NODE_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - 교육부 위키</title>
<link rel="stylesheet" href="../assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="../index.html">교육부 위키</a> &gt; <a href="../org.html">조직도</a></div>
  <h1 class="wiki-title">{path}</h1>
  <div class="wiki-subtitle">이 부서 명의로 발표된 보도자료입니다.</div>

  <div class="doc-card-list">
{rows}
  </div>

  <div class="wiki-footer">
    <a href="../org.html">&larr; 조직도로</a>
  </div>
</div>
</body>
</html>
"""


def _org_count(node, metas) -> int:
    children = node.get("children")
    if not children:
        return sum(1 for m in metas if m.get("division") == node["name"])
    return sum(_org_count(c, metas) for c in children)


def _render_org_node(node, metas, depth: int, path: list) -> str:
    count = _org_count(node, metas)
    children = node.get("children")
    name_html = esc(node["name"])
    count_html = f'<span class="org-count">{count}건</span>' if count else ""
    if children:
        my_path = path + [node["name"]]
        inner = "\n".join(_render_org_node(c, metas, depth + 1, my_path) for c in children)
        return (
            f'<div class="org-node org-level{depth}">'
            f'<div class="org-row"><span class="org-name">{name_html}</span>{count_html}</div>'
            f'<div class="org-children">{inner}</div>'
            f'</div>'
        )
    if count:
        _write_org_node_page(node["name"], path, metas)
        row = f'<a class="org-row org-leaf-link" href="org/{node["name"]}.html"><span class="org-name">{name_html}</span>{count_html}</a>'
    else:
        row = f'<div class="org-row org-leaf"><span class="org-name">{name_html}</span>{count_html}</div>'
    return f'<div class="org-node org-level{depth}">{row}</div>'


def _write_org_node_page(division_name: str, path: list, metas: list):
    """조직도에서 특정 과/팀(leaf)을 눌렀을 때, 그 부서명(division)이 정확히 일치하는
    보도자료만 모아 org/<부서명>.html 을 생성한다. (분류 페이지는 대분류 단위라 여러
    부서 문서가 섞여 나오므로, 조직도에서는 부서 단위로 별도 페이지를 둔다.)"""
    members = [m for m in metas if m.get("division") == division_name]
    rows = "\n".join(_doc_card(m, "../", "") for m in members)
    full_path = " &gt; ".join(esc(p) for p in path + [division_name])
    ORG_DIR.mkdir(exist_ok=True)
    (ORG_DIR / f"{division_name}.html").write_text(
        ORG_NODE_PAGE_TEMPLATE.format(
            css_ver=CSS_VERSION, name=esc(division_name), path=full_path, rows=rows
        ),
        encoding="utf-8",
    )


def render_org():
    metas = _collect_metas()
    tree_html = "\n".join(_render_org_node(node, metas, 1, []) for node in ORG_CHART)
    (ROOT / "org.html").write_text(
        ORG_PAGE_TEMPLATE.format(css_ver=CSS_VERSION, tree=tree_html), encoding="utf-8"
    )


# ---------- 정책 지도(policy-map.html): 활동 타임라인 + 업무계획 과제 ↔ 정책 위키 연결망 ----------
# 정책 위키 9건의 related(관련 보도자료) ID를 그대로 겹치는지만 보고 "연결"로 쓰면, 대부분
# 5/20 발표된 옴니버스 성과보고(106235) 하나 때문에 생기는 가짜 연결이라(실제로 9개 주제 중
# 8개가 이 문서 하나로만 서로 얽힘) 신뢰할 수 없다. 대신 워크플랜(data/workplan-*.json)의
# 각 섹션이 이미 수기로 달아둔 related_topics(그 과제를 실제로 구현하는 정책 위키)를 연결
# 근거로 쓴다. 정책 위키끼리의 직접 교차 참조는 KEYWORD_LINKS와 같은 방식으로 원문에 실제
# 있는 문구만 아래 TOPIC_CROSS_REFS에 수기로 등록한다.
TOPIC_CROSS_REFS = [
    {
        "from": "private-education-cost", "to": "early-childhood-care",
        "note": "private-education-cost 개요가 영유아 사교육 인식개선 캠페인을 early-childhood-care로 안내",
    },
]

# 정책 지도 하단 '정책 위키' 노드 나열 순서 — 상단 업무계획 허브와의 연결선이 최대한 덜
# 겹치도록 수동으로 정했다. 새 정책 위키 주제를 추가하면 이 목록에 없어도 끝에 자동으로
# 붙지만(_policy_map_topic_order), 선이 꼬이지 않게 하려면 이 목록에도 추가할 것.
POLICY_MAP_TOPIC_ORDER = [
    "regional-higher-edu", "advanced-industry-talent", "vocational-edu-innovation",
    "data-read-our-education", "ai-digital-edu-expansion", "early-childhood-care",
    "private-education-cost", "korean-language-edu", "special-education-support",
]

HUB_PREFIX_RE = re.compile(r"^(방향|핵심분야)[①-⑩]\s*")


def _policy_map_hubs():
    """워크플랜의 각 섹션 중 related_topics가 있는 것만 '허브'로 뽑는다. 라벨은 그 섹션의
    실제 heading 텍스트를 그대로 쓰고 새로 지어내지 않는다."""
    hubs = []
    for wid in WORKPLAN_IDS:
        plan = json.loads((DATA_DIR / f"workplan-{wid}.json").read_text(encoding="utf-8"))
        for i, sec in enumerate(plan["sections"], 1):
            related = sec.get("related_topics") or []
            if not related:
                continue
            hubs.append({
                "heading": sec["heading"],
                "href": f"workplan-{wid}.html#sec{i}",
                "plan_title": plan["title"],
                "topics": [t["id"] for t in related],
            })
    return hubs


# 네트워크 다이어그램 노드 라벨이 너무 길어 옆 노드와 겹칠 때만 쓰는 축약 라벨.
# _topic_short_title()의 자동 축약(제목의 " — " 앞부분)으로 충분하지 않은 경우에만 등록한다
# (예: early-childhood-care는 제목에 " — " 구분자가 없어 전체 제목이 그대로 잡혀 겹침).
POLICY_MAP_SHORT_LABELS = {
    "early-childhood-care": "유보통합·돌봄",
}


def _topic_short_title(t: dict) -> str:
    if t["id"] in POLICY_MAP_SHORT_LABELS:
        return POLICY_MAP_SHORT_LABELS[t["id"]]
    return t["title"].split(" — ")[0].strip()


def _wrap_label(text: str, max_line: int = 8) -> list[str]:
    """SVG 노드 라벨용 단순 2줄 줄바꿈(중앙에서 가장 가까운 공백 기준)."""
    if len(text) <= max_line:
        return [text]
    spaces = [i for i, c in enumerate(text) if c == " "]
    if spaces:
        mid = len(text) / 2
        cut = min(spaces, key=lambda i: abs(i - mid))
        return [text[:cut].strip(), text[cut:].strip()]
    return [text[:max_line], text[max_line:]]


def _policy_map_topic_order(topics: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in topics}
    ordered = [by_id[i] for i in POLICY_MAP_TOPIC_ORDER if i in by_id]
    rest = [t for t in topics if t["id"] not in POLICY_MAP_TOPIC_ORDER]
    return ordered + rest


def _policy_map_layout(topics: list[dict], hubs: list[dict], width: float = 860, margin: float = 70):
    """정책 위키 노드는 고정 순서로 가로 배치하고, 업무계획 허브는 자신이 연결하는 정책들의
    평균 x좌표 순으로 배치해(연결선이 최대한 덜 꼬이도록) 좌표를 계산한다."""
    ordered_topics = _policy_map_topic_order(topics)
    topic_ids = [t["id"] for t in ordered_topics]
    n = len(topic_ids)
    step = (width - 2 * margin) / max(n - 1, 1)
    topic_x = {tid: margin + i * step for i, tid in enumerate(topic_ids)}

    for h in hubs:
        xs = [topic_x[tid] for tid in h["topics"] if tid in topic_x]
        h["avg_x"] = sum(xs) / len(xs) if xs else width / 2
    hubs_sorted = sorted(hubs, key=lambda h: h["avg_x"])
    m = len(hubs_sorted)
    hub_step = (width - 2 * margin) / max(m - 1, 1) if m > 1 else 0
    for i, h in enumerate(hubs_sorted):
        h["x"] = margin + i * hub_step if m > 1 else width / 2

    return ordered_topics, topic_x, hubs_sorted


def _policy_map_network_svg(ordered_topics, topic_x, hubs_sorted, width=860):
    hub_y, topic_y, height = 55, 230, 300
    parts = [
        f'<svg class="pm-network" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="업무계획 과제와 정책 위키 주제의 연결 관계">'
    ]

    for h in hubs_sorted:
        x1, y1 = h["x"], hub_y + 15
        for tid in h["topics"]:
            if tid not in topic_x:
                continue
            x2, y2 = topic_x[tid], topic_y - 10
            ymid = (y1 + y2) / 2
            parts.append(
                f'<path class="pm-edge" d="M{x1:.1f} {y1:.1f} C{x1:.1f} {ymid:.1f} {x2:.1f} {ymid:.1f} {x2:.1f} {y2:.1f}"/>'
            )

    for ref in TOPIC_CROSS_REFS:
        if ref["from"] not in topic_x or ref["to"] not in topic_x:
            continue
        x1, x2 = topic_x[ref["from"]], topic_x[ref["to"]]
        y = topic_y - 10
        peak = y - 34
        parts.append(
            f'<path class="pm-edge pm-edge-ref" d="M{x1:.1f} {y:.1f} C{x1:.1f} {peak:.1f} {x2:.1f} {peak:.1f} {x2:.1f} {y:.1f}">'
            f'<title>{esc(ref["note"])}</title></path>'
        )

    for i, h in enumerate(hubs_sorted, 1):
        x = h["x"]
        parts.append(
            f'<a href="{h["href"]}"><g class="pm-hub">'
            f'<circle cx="{x:.1f}" cy="{hub_y}" r="15"/>'
            f'<text x="{x:.1f}" y="{hub_y + 5}" text-anchor="middle">{i}</text>'
            f'<title>{esc(h["plan_title"])} · {esc(h["heading"])}</title>'
            f'</g></a>'
        )

    for t in ordered_topics:
        x = topic_x[t["id"]]
        lines = _wrap_label(_topic_short_title(t))
        tspans = "".join(
            f'<tspan x="{x:.1f}" dy="{0 if j == 0 else 13}">{esc(line)}</tspan>' for j, line in enumerate(lines)
        )
        parts.append(
            f'<a href="topics/{t["id"]}.html"><g class="pm-topic">'
            f'<circle cx="{x:.1f}" cy="{topic_y}" r="8"/>'
            f'<text x="{x:.1f}" y="{topic_y + 22}" text-anchor="middle" class="pm-topic-label">{tspans}</text>'
            f'<title>{esc(t["title"])}</title>'
            f'</g></a>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _policy_map_timeline_html(metas: list[dict], topics: list[dict]):
    monthly: dict[str, int] = {}
    for m in metas:
        ym = m.get("date", "")[:7]
        if ym:
            monthly[ym] = monthly.get(ym, 0) + 1
    months = sorted(monthly.keys())
    max_count = max(monthly.values()) if monthly else 1

    bars = []
    for ym in months:
        cnt = monthly[ym]
        pct = round(cnt / max_count * 100)
        bars.append(
            '    <div class="pm-bar-col">'
            f'<div class="pm-bar-count">{cnt}</div>'
            f'<div class="pm-bar" style="height:{pct}%"></div>'
            f'<div class="pm-bar-label">{esc(_month_label(ym).replace("년 ", ".").replace("월", ""))}</div>'
            '</div>'
        )
    monthly_html = '  <div class="pm-monthly-chart">\n' + "\n".join(bars) + "\n  </div>"

    date_by_slug = {m["slug"]: m.get("date", "") for m in metas}
    n_months = len(months)
    month_index = {ym: i for i, ym in enumerate(months)}

    def frac(d: str) -> float:
        ym, day = d[:7], int(d[8:10])
        idx = month_index.get(ym)
        if idx is None or n_months == 0:
            return 0.0
        return (idx + min(day - 1, 30) / 30) / n_months

    ordered_topics = _policy_map_topic_order(topics)
    rows = []
    for t in ordered_topics:
        ds = sorted(date_by_slug[s] for s in t["related"] if date_by_slug.get(s))
        if not ds:
            continue
        left = frac(ds[0]) * 100
        right = frac(ds[-1]) * 100
        width_pct = max(right - left, 1.2)
        rows.append(
            '    <div class="pm-gantt-row">'
            f'<a class="pm-gantt-label" href="topics/{t["id"]}.html">{esc(_topic_short_title(t))}</a>'
            f'<div class="pm-gantt-track"><div class="pm-gantt-bar" style="left:{left:.1f}%;width:{width_pct:.1f}%">'
            f'<span class="pm-gantt-range">{esc(ds[0])} ~ {esc(ds[-1])}</span></div></div>'
            '</div>'
        )
    gantt_html = '  <div class="pm-gantt">\n' + "\n".join(rows) + "\n  </div>"
    return monthly_html, gantt_html


POLICY_MAP_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>정책 지도 - 교육부 위키</title>
<link rel="stylesheet" href="assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="index.html">교육부 위키</a> &gt; 정책 지도</div>
  <h1 class="wiki-title">정책 지도</h1>
  <div class="wiki-subtitle">교육부가 그동안 발표한 정책의 흐름과, 정책 위키 주제들이 업무계획 안에서 어떻게 연결되는지 한눈에 봅니다.</div>

  <h2 id="timeline">그동안의 활동량과 정책별 진행 기간</h2>
  <p class="section-desc">막대는 월별 보도자료 건수, 아래 띠는 각 정책 위키 주제가 다루는 보도자료들의 발표 기간입니다.{month_caveat}</p>
  <div class="table-scroll pm-scroll">
{monthly_chart}
  </div>
{gantt}

  <h2 id="network">업무계획 과제 ↔ 정책 위키 연결망</h2>
  <p class="section-desc">위쪽 번호 노드는 2026년 업무계획(연간·하반기)이 명시한 과제이고, 아래쪽 노드는 정책 위키 주제입니다. 실선은 업무계획이 직접 연결한 정책, 점선은 위키 본문에서 따로 이어둔 정책 간 참조입니다. 두 경우 모두 이미 문서에 있는 연결만 표시하며, 이 페이지가 새로 추론한 관계는 없습니다.</p>
  <div class="table-scroll pm-scroll">
{network_svg}
  </div>

  <ol class="pm-hub-legend">
{hub_legend}
  </ol>

  <div class="wiki-footer">
    <a href="index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


def render_policy_map():
    metas = _collect_metas()
    topics = _collect_topics()
    hubs = _policy_map_hubs()

    monthly_chart, gantt = _policy_map_timeline_html(metas, topics)
    ordered_topics, topic_x, hubs_sorted = _policy_map_layout(topics, hubs)
    network_svg = _policy_map_network_svg(ordered_topics, topic_x, hubs_sorted)
    hub_legend = "\n".join(
        f'    <li><a href="{h["href"]}">{esc(h["plan_title"])} · {esc(h["heading"])}</a></li>'
        for h in hubs_sorted
    )

    today = date.today().isoformat()
    month_caveat = ""
    if any(m.get("date", "")[:7] == today[:7] for m in metas):
        month_caveat = " (이번 달은 아직 진행 중이라 다른 달보다 건수가 적게 보일 수 있습니다)"

    html_out = POLICY_MAP_PAGE_TEMPLATE.format(
        css_ver=CSS_VERSION,
        month_caveat=month_caveat,
        monthly_chart=monthly_chart,
        gantt=gantt,
        network_svg=network_svg,
        hub_legend=hub_legend,
    )
    (ROOT / "policy-map.html").write_text(html_out, encoding="utf-8")


WORKPLAN_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 교육부 위키</title>
<link rel="stylesheet" href="assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="index.html">교육부 위키</a> &gt; 업무계획</div>
  <h1 class="wiki-title">{title}</h1>
  <div class="wiki-subtitle">{subtitle}</div>

  <div class="toc">
    <div class="toc-title">목차</div>
    <ol>
{toc_items}
    </ol>
  </div>

{body}

  <p><a href="{source_url}" target="_blank" rel="noopener">교육부 원문 페이지 ↗</a></p>

  <div class="wiki-footer">
    <a href="index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


def render_workplan(workplan_id: str):
    """data/workplan-<id>.json(카드뉴스 등 공식 발표 자료를 바탕으로 재구성한 연간 업무계획 요약)을
    읽어 workplan-<id>.html 을 생성한다. 정책 위키(topics/)와 달리 index.html에서 별도 섹션으로 노출된다."""
    plan = json.loads((DATA_DIR / f"workplan-{workplan_id}.json").read_text(encoding="utf-8"))

    toc_items = []
    body_parts = []
    for i, sec in enumerate(plan["sections"], 1):
        anchor = f"sec{i}"
        toc_items.append(f'      <li><a href="#{anchor}">{esc(sec["heading"])}</a></li>')
        section_html = f'  <h2 id="{anchor}">{esc(sec["heading"])}</h2>\n{render_prose(sec["body"])}'
        related = sec.get("related_topics") or []
        if related:
            links = " · ".join(f'<a href="topics/{t["id"]}.html">{esc(t["label"])}</a>' for t in related)
            section_html += f'\n  <p class="related-topics-line"><strong>관련 정책 위키:</strong> {links}</p>'
        body_parts.append(section_html)

    html_out = WORKPLAN_PAGE_TEMPLATE.format(
        css_ver=CSS_VERSION,
        title=esc(plan["title"]),
        subtitle=esc(plan.get("subtitle", "")),
        toc_items="\n".join(toc_items),
        body="\n\n".join(body_parts),
        source_url=esc(plan["source_url"]),
    )
    out_path = ROOT / f"workplan-{workplan_id}.html"
    out_path.write_text(html_out, encoding="utf-8")
    return plan, out_path


INDEX_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>교육부 위키</title>
<link rel="stylesheet" href="assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <header class="site-header">
    <h1 class="site-title">교육부 위키</h1>
    <p class="site-subtitle">교육부 보도자료를 위키 형태로 정리한 아카이브</p>
  </header>

  <div class="site-notice">
    <p><strong>📌 안내</strong></p>
    <p>이 위키는 교육부 보도자료를 바탕으로 <strong>격주</strong>로 업데이트됩니다. 업데이트되면 이 페이지에 <strong>자동으로 최신 내용이 반영</strong>되므로, 새 링크를 받을 필요 없이 지금 이 주소를 그대로 저장해두고 보시면 됩니다.</p>
    <p class="site-notice-updated">최근 업데이트: {updated_date}</p>
    <p>
      · <strong>익명 제안함</strong> — 이 위키에 대한 의견·건의사항을 로그인 없이 익명으로 남길 수 있습니다.<br>
      · <strong>교육부 조직도</strong> — 실·국·과 단위 조직 체계와 각 부서가 작성한 보도자료 건수를 한눈에 볼 수 있습니다.<br>
      · <strong>교육부 업무계획</strong> — 교육부가 발표한 연간·반기별 업무계획(방향·핵심 과제)을 한 페이지씩 정리했습니다.<br>
      · <strong>정책 지도</strong> — 그동안의 정책 발표 흐름과, 정책 위키 주제들이 업무계획 과제와 어떻게 연결되는지 시각화로 볼 수 있습니다.<br>
      · <strong>정책 위키</strong> — 여러 보도자료를 하나의 주제로 종합해, 교육부가 지금 무엇을 추진하고 있는지 한눈에 볼 수 있도록 정리한 문서입니다.<br>
      · <strong>분류</strong> — 초중등교육·고등교육 등 조직 체계를 기준으로 개별 보도자료를 나눠서 볼 수 있습니다.<br>
      · <strong>최신 문서</strong> — 가장 최근에 추가된 보도자료 원문 기반 문서를 월별로 나눠서 볼 수 있습니다.
    </p>
    <p class="site-notice-signature">(제작 by NSG)</p>
  </div>

  <a class="org-link-card" href="{suggestion_form_url}" target="_blank" rel="noopener">💬 위키에 익명으로 제안하기 &rarr;</a>

  <h2 class="section-label">교육부 조직도</h2>
  <p class="section-desc">실·국·과 단위 조직 체계와 각 부서가 작성한 보도자료 건수를 한눈에 볼 수 있습니다.</p>
  <a class="org-link-card" href="org.html">🏛️ 교육부 조직도 한눈에 보기 &rarr;</a>

  <h2 class="section-label">교육부 업무계획</h2>
  <p class="section-desc">교육부가 올해 무엇을 하겠다고 밝혔는지, 연간·반기별 업무계획의 방향과 핵심 과제를 한 페이지씩 정리했습니다.</p>
{workplan_cards}

  <h2 class="section-label">정책 지도</h2>
  <p class="section-desc">그동안의 정책 발표 흐름과, 정책 위키 주제들이 업무계획 과제와 어떻게 연결되는지 한 페이지에서 볼 수 있습니다.</p>
  <a class="org-link-card" href="policy-map.html">🗺️ 정책 지도 보기 &rarr;</a>

  <h2 class="section-label">정책 위키</h2>
  <p class="section-desc">여러 보도자료를 주제별로 종합해, 교육부가 지금 무엇을 추진하고 있는지 한눈에 볼 수 있도록 정리한 문서입니다.</p>
  <div class="topic-grid">
{topic_cards}
  </div>

  <h2 class="section-label">분류</h2>
  <div class="category-grid">
{category_cards}
  </div>

  <h2 class="section-label">최신 문서</h2>
{rows}
</div>
</body>
</html>
"""

CATEGORY_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>분류:{name} - 교육부 위키</title>
<link rel="stylesheet" href="../assets/style.css?v={css_ver}">
</head>
<body>
<div class="wiki-page">
  <div class="wiki-breadcrumb"><a href="../index.html">교육부 위키</a> &gt; 분류</div>
  <h1 class="wiki-title">분류: {name}</h1>
{subcats}
{content}
  <div class="wiki-footer">
    <a href="../index.html">&larr; 목록으로</a>
  </div>
</div>
</body>
</html>
"""


def _collect_metas():
    metas = []
    for f in sorted(DATA_DIR.glob("*.meta.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        main, sub = classify(m.get("bureau", ""), m.get("division", ""))
        m["_main_cat"], m["_sub_cat"] = main, sub
        metas.append(m)
    metas.sort(key=lambda m: m.get("date", ""), reverse=True)
    return metas


def _doc_card(m: dict, base: str, tag: str) -> str:
    return (
        f'    <a class="doc-card" href="{base}articles/{m["slug"]}.html">'
        f'<span class="doc-date">{esc(m.get("date",""))}</span>'
        f'<span class="doc-title">{esc(m["title"])}</span>'
        f'<span class="doc-tag">{tag}</span></a>'
    )


def _subcat_section(label: str, members: list[dict]) -> str:
    rows = [_doc_card(m, "../", "") for m in members]
    return (
        f'  <div class="subcat-section">\n'
        f'    <h2 class="section-label">{esc(label)}</h2>\n'
        f'    <div class="doc-card-list">\n' + "\n".join(rows) + "\n    </div>\n"
        f"  </div>"
    )


def _month_label(ym: str) -> str:
    year, month = ym.split("-")
    return f"{year}년 {int(month)}월"


def _doc_month_sections(metas: list[dict]) -> str:
    """metas(날짜 내림차순)를 월(YYYY-MM) 단위로 묶어, <details>로 접었다 펼 수 있는 목록 HTML을 만든다.
    전부 기본으로 접어서 스크롤 부담을 줄인다(JS 없이 네이티브 요소로 구현)."""
    groups: list[tuple[str, list[dict]]] = []
    for m in metas:
        ym = m.get("date", "")[:7]
        if groups and groups[-1][0] == ym:
            groups[-1][1].append(m)
        else:
            groups.append((ym, [m]))

    sections = []
    for ym, members in groups:
        cards = []
        for m in members:
            cat_label = m["_main_cat"] + (f" &gt; {esc(m['_sub_cat'])}" if m["_sub_cat"] else "")
            cards.append(_doc_card(m, "", cat_label))
        sections.append(
            f'  <details class="subcat-section">\n'
            f'    <summary class="section-label month-summary">{esc(_month_label(ym))} <span class="chip">{len(members)}건</span></summary>\n'
            f'    <div class="doc-card-list">\n' + "\n".join(cards) + "\n    </div>\n"
            f"  </details>"
        )
    return "\n".join(sections)


def rebuild_categories():
    metas = _collect_metas()
    CATEGORIES_DIR.mkdir(exist_ok=True)
    for cat in CATEGORY_MAP["categories"]:
        name = cat["name"]
        members = [m for m in metas if m["_main_cat"] == name]
        subcats_html = ""
        if cat["children"]:
            chips = "".join(f'<span class="chip">{esc(c)}</span>' for c in cat["children"])
            subcats_html = f'  <div class="category-subcats" style="margin-bottom:20px">{chips}</div>'

            sections = []
            for sub in cat["children"]:
                sub_members = [m for m in members if m["_sub_cat"] == sub]
                if sub_members:
                    sections.append(_subcat_section(sub, sub_members))
            others = [m for m in members if m["_sub_cat"] not in cat["children"]]
            if others:
                sections.append(_subcat_section("기타", others))
            content = "\n\n".join(sections) if sections else '  <div class="doc-empty">아직 문서 없음</div>'
        else:
            rows = [_doc_card(m, "../", esc(m["_sub_cat"] or "-")) for m in members]
            content = (
                '  <div class="doc-card-list">\n' + "\n".join(rows) + "\n  </div>"
                if rows else '  <div class="doc-empty">아직 문서 없음</div>'
            )

        html_out = CATEGORY_PAGE_TEMPLATE.format(
            css_ver=CSS_VERSION,
            name=esc(name),
            subcats=subcats_html,
            content=content,
        )
        (CATEGORIES_DIR / f"{cat['id']}.html").write_text(html_out, encoding="utf-8")


def rebuild_index():
    metas = _collect_metas()
    topics = _collect_topics()

    workplan_cards = []
    for wid in WORKPLAN_IDS:
        plan = json.loads((DATA_DIR / f"workplan-{wid}.json").read_text(encoding="utf-8"))
        workplan_cards.append(
            f'  <a class="org-link-card" href="workplan-{wid}.html">📋 {esc(plan["title"])} 보기 &rarr;</a>'
        )

    topic_cards = [
        f'    <a class="topic-card" href="topics/{t["id"]}.html">'
        f'<div class="topic-card-title">{esc(t["title"])}</div>'
        f'<div class="topic-card-subtitle">{esc(t.get("subtitle", ""))}</div>'
        f'<span class="topic-card-count">관련 보도자료 {len(t["related"])}건</span></a>'
        for t in topics
    ]

    cards = []
    for cat in CATEGORY_MAP["categories"]:
        count = sum(1 for m in metas if m["_main_cat"] == cat["name"])
        chips = "".join(f'<span class="chip">{esc(c)}</span>' for c in cat["children"])
        cards.append(
            f'    <a class="category-card" href="categories/{cat["id"]}.html">'
            f'<div class="category-card-top"><span class="category-name">{esc(cat["name"])}</span>'
            f'<span class="category-count">{count}</span></div>'
            f'<div class="category-subcats">{chips}</div></a>'
        )

    rows = _doc_month_sections(metas)

    (ROOT / "index.html").write_text(
        INDEX_TEMPLATE.format(
            css_ver=CSS_VERSION,
            updated_date=date.today().isoformat(),
            suggestion_form_url=SUGGESTION_FORM_URL,
            workplan_cards="\n".join(workplan_cards),
            topic_cards="\n".join(topic_cards) if topic_cards else '    <div class="doc-empty">아직 문서 없음</div>',
            category_cards="\n".join(cards),
            rows=rows,
        ),
        encoding="utf-8",
    )


def ingest(slug: str):
    """data/<slug>.md + _batch_manifest.json 항목으로 meta.json 생성 (담당부서 추출·분류 포함)."""
    manifest = json.loads((DATA_DIR / "_batch_manifest.json").read_text(encoding="utf-8"))
    entry = next((e for e in manifest if e["boardSeq"] == slug), None)
    if entry is None:
        raise SystemExit(f"manifest에서 boardSeq={slug} 를 찾을 수 없음")
    chunks = load_chunks(slug)
    bureau, division, contact = extract_contact(chunks)
    meta = {
        "slug": slug,
        "title": entry["title"],
        "subtitle": "",
        "date": entry["date"],
        "bureau": bureau,
        "division": division,
        "contact": contact,
        "source_url": entry["source_url"],
    }
    (DATA_DIR / f"{slug}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    main, sub = classify(bureau, division)
    print(f"{slug}: {entry['title'][:30]}... -> {bureau}/{division} => {main}/{sub}")
    return meta


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "--rebuild-index":
        for t in _collect_topics():
            render_topic(t["id"])
        for wid in WORKPLAN_IDS:
            render_workplan(wid)
        rebuild_categories()
        rebuild_index()
        render_org()
        render_policy_map()
        print("index.html / categories/*.html / topics/*.html / org.html / workplan-2026.html / policy-map.html 갱신 완료")
    elif sys.argv[1] == "--ingest":
        ingest(sys.argv[2])
    elif sys.argv[1] == "--topic":
        topic, path = render_topic(sys.argv[2])
        rebuild_index()
        print(f"생성됨: {path}")
    else:
        slug = sys.argv[1]
        meta, path = render_article(slug)
        rebuild_categories()
        rebuild_index()
        print(f"생성됨: {path}")
