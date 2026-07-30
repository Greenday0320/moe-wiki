"""
교육부 보도자료 목록/첨부파일 수집기 (kordoc 불필요, 순수 HTTP)
------------------------------------------------------------
최근 N일치 보도자료의 제목/날짜/boardSeq를 목록 페이지에서 뽑고,
각 상세 페이지에서 첨부파일(hwpx/hwp/pdf/docx) 다운로드 링크를 찾아
raw/ 폴더에 내려받은 뒤 data/_batch_manifest.json 에 기록한다.

사용법:
    python fetch_batch.py --days 21
"""
import argparse
import datetime
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
DATA_DIR = ROOT / "data"
BOARD_ID = "294"
LIST_URL = "https://www.moe.go.kr/boardCnts/listRenew.do?boardID={board}&m=020402&s=moe&page={page}"
DETAIL_URL = ("https://www.moe.go.kr/boardCnts/viewRenew.do?boardID={board}&boardSeq={seq}"
              "&lev=0&searchType=null&statusYN=W&page=1&s=moe&m=020402&opType=N")
FILE_URL = "https://www.moe.go.kr{href}"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ROW_RE = re.compile(
    r"goView\('294',\s*'(\d+)'.*?title=\"([^\"]+)\".*?<td>([\d\-]{10})</td>",
    re.DOTALL,
)
ATTACH_NAME_RE = re.compile(r"<span>([^<]*\.(hwpx|hwp|pdf|docx))")
ATTACH_HREF_RE = re.compile(r"(/boardCnts/fileDown\.do\?[^\"]+)")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def list_rows(page: int):
    html = fetch(LIST_URL.format(board=BOARD_ID, page=page))
    return ROW_RE.findall(html)


def find_attachment(seq: str):
    html = fetch(DETAIL_URL.format(board=BOARD_ID, seq=seq))
    name_m = ATTACH_NAME_RE.search(html)
    href_m = ATTACH_HREF_RE.search(html)
    if not (name_m and href_m):
        return None
    ext = name_m.group(2)
    href = href_m.group(1).replace("&amp;", "&")
    return ext, href


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()

    cutoff = datetime.date.today() - datetime.timedelta(days=args.days)
    RAW_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    manifest = []
    page = 1
    stop = False
    while not stop and page <= 30:
        rows = list_rows(page)
        if not rows:
            break
        for seq, title, date_str in rows:
            d = datetime.date.fromisoformat(date_str)
            if d < cutoff:
                stop = True
                continue
            title = title.strip()
            print(f"[{date_str}] {title} (boardSeq={seq})")
            attach = find_attachment(seq)
            if not attach:
                print("  -> 첨부파일 없음, 건너뜀")
                continue
            ext, href = attach
            raw_path = RAW_DIR / f"{seq}.{ext}"
            if not raw_path.exists():
                data = urllib.request.urlopen(
                    urllib.request.Request(FILE_URL.format(href=href), headers=HEADERS),
                    timeout=30,
                ).read()
                raw_path.write_bytes(data)
            manifest.append({
                "boardSeq": seq,
                "title": title,
                "date": date_str,
                "source_url": DETAIL_URL.format(board=BOARD_ID, seq=seq),
                "raw_path": str(raw_path),
            })
        page += 1

    (DATA_DIR / "_batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n총 {len(manifest)}건 다운로드 완료 -> data/_batch_manifest.json")


if __name__ == "__main__":
    main()
