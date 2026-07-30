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
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
ARTICLES_DIR = ROOT / "articles"
ASSETS_DIR = ROOT / "assets"
CATEGORIES_DIR = ROOT / "categories"
CATEGORY_MAP = json.loads((ROOT / "category_map.json").read_text(encoding="utf-8"))
CSS_VERSION = 2  # style.css 수정할 때마다 올려서 모바일 브라우저 캐시를 무효화한다.

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ATTACH_RE = re.compile(r"붙임\s*(\d+)")

# 나무위키식 문서 간 키워드 자동 연결.
# {"phrase": 텍스트, "targets": {소스slug: 링크할slug, ...}} — phrase가 소스 문서 본문에
# 등장하면 첫 번째 등장한 곳만 targets[소스slug]로 링크한다(자기 자신이 target이면 건너뜀).
KEYWORD_LINKS = [
    {"phrase": "포용교육 시대, 특수교육이 만들어가는 변화", "targets": {"106773": "106680"}},
    {"phrase": "계약학과", "targets": {"106666": "106740", "106661": "106740", "106326": "106740"}},
    {"phrase": "지역성장 인재양성", "targets": {
        "106666": "106688", "106688": "106666", "106345": "106688", "106504": "106688",
    }},
    {"phrase": "한국교육원", "targets": {"106806": "106749", "106749": "106806"}},
    {"phrase": "데이터로 읽는 우리 교육", "targets": {
        "106680": "106773", "106436": "106571", "106571": "106680",
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

  <h2 class="section-label">분류</h2>
  <div class="category-grid">
{category_cards}
  </div>

  <h2 class="section-label">최신 문서</h2>
  <div class="doc-card-list">
{rows}
  </div>
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
  <div class="doc-card-list">
{rows}
  </div>
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
        rows = [_doc_card(m, "../", esc(m["_sub_cat"] or "-")) for m in members]
        html_out = CATEGORY_PAGE_TEMPLATE.format(
            css_ver=CSS_VERSION,
            name=esc(name),
            subcats=subcats_html,
            rows="\n".join(rows) if rows else '    <div class="doc-empty">아직 문서 없음</div>',
        )
        (CATEGORIES_DIR / f"{cat['id']}.html").write_text(html_out, encoding="utf-8")


def rebuild_index():
    metas = _collect_metas()

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

    rows = []
    for m in metas:
        cat_label = m["_main_cat"] + (f" &gt; {esc(m['_sub_cat'])}" if m["_sub_cat"] else "")
        rows.append(_doc_card(m, "", cat_label))

    (ROOT / "index.html").write_text(
        INDEX_TEMPLATE.format(css_ver=CSS_VERSION, category_cards="\n".join(cards), rows="\n".join(rows)),
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
        rebuild_categories()
        rebuild_index()
        print("index.html / categories/*.html 갱신 완료")
    elif sys.argv[1] == "--ingest":
        ingest(sys.argv[2])
    else:
        slug = sys.argv[1]
        meta, path = render_article(slug)
        rebuild_categories()
        rebuild_index()
        print(f"생성됨: {path}")
