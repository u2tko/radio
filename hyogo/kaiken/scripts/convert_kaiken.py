#!/usr/bin/env python3
"""
兵庫県知事記者会見 HTML -> Markdown 変換スクリプト（標準ライブラリのみ）

取得済みの兵庫県公式記者会見HTMLから、一次資料としての原文忠実性を保った
回数別Markdownファイルと年次インデックス（README.md）を生成する。
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

BASE_URL = "https://web.pref.hyogo.lg.jp"
KANGXI_MONTH = "\u2f49"  # ⽉ -> 月


def normalize_display(text: str) -> str:
    """表示用テキストの互換文字（康熙部首の⽉など）と余分な空白を最小限に整形する。"""
    text = text.replace(KANGXI_MONTH, "月")
    text = text.replace("\xa0", " ")
    return text.strip()


def normalize_inline(text: str) -> str:
    """本文内テキスト。原文の語句を変えず、NBSPと改行周りのみ最小限に整形する。"""
    text = text.replace(KANGXI_MONTH, "月")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_jp_date(text: str) -> str:
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not m:
        return text.strip()
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def extract_weekday(title: str) -> str:
    m = re.search(r"（([月火水木金土日]曜日)）", title)
    return m.group(1) if m else ""


def classify_category(title: str) -> str:
    if "当初予算" in title:
        return "当初予算"
    if "補正予算" in title:
        return "補正予算"
    if "組織改正" in title or "人事異動" in title:
        return "組織改正・人事異動"
    if "臨時" in title:
        return "臨時会見"
    return "定例会見"


def is_speaker_label(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 35:
        return False
    if not (t.endswith("：") or t.endswith(":")):
        return False
    if "。" in t or "、" in t:
        return False
    if t.startswith("※") or t.startswith("【"):
        return False
    return True


class KaikenHTMLParser(HTMLParser):
    """兵庫県公式サイトの #tmp_contents / メタ情報を構造化抽出するパーサー。"""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url

        # Page-level metadata
        self.page_id = ""
        self.updated_raw = ""
        self._meta_target: str | None = None
        self._meta_buf: list[str] = []

        # #tmp_contents traversal
        self.in_contents = False
        self.div_depth = 0

        self.h1 = ""
        self._in_h1 = False
        self._h1_buf: list[str] = []

        # Sections: list of {"heading": str, "blocks": list[dict]}
        # heading == "__HEADER__" for content before the first <h2>
        self.sections: list[dict] = [{"heading": "__HEADER__", "blocks": []}]
        self._in_h2 = False
        self._h2_buf: list[str] = []

        # Inline / block state
        self._in_p = False
        self._p_parts: list[str] = []

        self._list_stack: list[dict] = []  # {"type": "ol"|"ul", "items": list}
        self._li_stack: list[dict] = []    # {"parts": list[str], "sublists": list}

        self._in_a = False
        self._a_href = ""
        self._a_parts: list[str] = []

        self._in_del = False
        self._del_parts: list[str] = []

    def _append_inline(self, text: str) -> None:
        if self._in_del:
            self._del_parts.append(text)
        elif self._in_a:
            self._a_parts.append(text)
        elif self._li_stack:
            self._li_stack[-1]["parts"].append(text)
        elif self._in_p:
            self._p_parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "p" and d.get("id") in ("tmp_pageid", "tmp_update"):
            self._meta_target = d["id"]
            self._meta_buf = []
            return

        if tag == "div" and d.get("id") == "tmp_contents":
            self.in_contents = True
            self.div_depth = 1
            return

        if not self.in_contents:
            return

        if tag == "div":
            self.div_depth += 1
            return

        if tag == "h1":
            self._in_h1 = True
            self._h1_buf = []
        elif tag == "h2":
            self._in_h2 = True
            self._h2_buf = []
        elif tag == "p":
            self._in_p = True
            self._p_parts = []
        elif tag in ("ol", "ul"):
            self._list_stack.append({"type": tag, "items": []})
        elif tag == "li":
            self._li_stack.append({"parts": [], "sublists": []})
        elif tag == "a":
            self._in_a = True
            self._a_href = urljoin(self.page_url, d.get("href") or "")
            self._a_parts = []
        elif tag == "del":
            self._in_del = True
            self._del_parts = []
        elif tag == "br":
            self._append_inline("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._meta_target and tag == "p":
            txt = "".join(self._meta_buf).strip()
            if self._meta_target == "tmp_pageid":
                self.page_id = re.sub(r"^ページ番号[：:]\s*", "", txt)
            elif self._meta_target == "tmp_update":
                self.updated_raw = re.sub(r"^更新日[：:]\s*", "", txt)
            self._meta_target = None
            return

        if not self.in_contents:
            return

        if tag == "div":
            self.div_depth -= 1
            if self.div_depth == 0:
                self.in_contents = False
            return

        if tag == "h1" and self._in_h1:
            self.h1 = normalize_display("".join(self._h1_buf))
            self._in_h1 = False
        elif tag == "h2" and self._in_h2:
            heading = normalize_display("".join(self._h2_buf))
            self.sections.append({"heading": heading, "blocks": []})
            self._in_h2 = False
        elif tag == "del" and self._in_del:
            inner = normalize_inline("".join(self._del_parts)).strip()
            self._in_del = False
            if inner:
                self._append_inline(f"~~{inner}~~")
        elif tag == "a" and self._in_a:
            raw_label = "".join(self._a_parts)
            # リンクラベル内の改行は読みやすくスペース/詰めで1行化
            label = re.sub(r"\s*\n\s*", " ", raw_label).strip()
            label = normalize_display(label)
            href = self._a_href
            self._in_a = False
            if label and href:
                self._append_inline(f"[{label}]({href})")
            elif label:
                self._append_inline(label)
        elif tag == "p" and self._in_p:
            raw_p = "".join(self._p_parts)
            # 各行の前後空白を整える
            lines = [normalize_inline(ln).strip() for ln in raw_p.split("\n")]
            text = "\n".join(ln for ln in lines if ln != "").strip()
            self.sections[-1]["blocks"].append({"type": "p", "text": text})
            self._in_p = False
        elif tag == "li" and self._li_stack:
            li = self._li_stack.pop()
            raw_li = "".join(li["parts"])
            lines = [normalize_inline(ln).strip() for ln in raw_li.split("\n")]
            li_obj = {"lines": [ln for ln in lines if ln != ""], "sublists": li["sublists"]}
            if self._list_stack:
                self._list_stack[-1]["items"].append(li_obj)
        elif tag in ("ol", "ul") and self._list_stack:
            lst = self._list_stack.pop()
            if self._li_stack:
                self._li_stack[-1]["sublists"].append(lst)
            else:
                self.sections[-1]["blocks"].append({"type": "list", "list": lst})

    def handle_data(self, data: str) -> None:
        if self._meta_target:
            self._meta_buf.append(data)
            return
        if not self.in_contents:
            return
        if self._in_h1:
            self._h1_buf.append(data)
        elif self._in_h2:
            self._h2_buf.append(data)
        else:
            self._append_inline(data)


def extract_link_label_and_url(md_link: str) -> tuple[str, str]:
    m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", md_link)
    if m:
        return m.group(1), m.group(2)
    return md_link, ""


def convert_page(html_text: str, session_meta: dict, fetched_date: str) -> dict:
    parser = KaikenHTMLParser(session_meta["url"])
    parser.feed(html_text)

    title = parser.h1 or normalize_display(session_meta["link_title"])
    date_str = session_meta["date"]
    weekday = extract_weekday(title)
    category = classify_category(title)
    updated_iso = parse_jp_date(parser.updated_raw) if parser.updated_raw else ""

    # Header block parsing: presentation items & official notices (e.g. ※削除注記)
    presentation_items: list[dict] = []  # {"text": str, "subitems": list[str]}
    official_notes: list[str] = []
    video_url = ""
    video_label = ""
    body_sections: list[tuple[str, list[dict]]] = []

    for sec in parser.sections:
        heading = sec["heading"]
        blocks = sec["blocks"]
        if heading == "__HEADER__":
            for b in blocks:
                if b["type"] == "p":
                    t = b["text"]
                    if not t or t == "【発表項目】":
                        continue
                    if t.startswith("※"):
                        official_notes.append(t)
                    else:
                        official_notes.append(t)
                elif b["type"] == "list":
                    for item in b["list"]["items"]:
                        item_lines = []
                        for ln in item["lines"]:
                            if ln.startswith("※"):
                                official_notes.append(ln)
                            else:
                                item_lines.append(ln)
                        subitems = []
                        for sub in item["sublists"]:
                            for sub_it in sub["items"]:
                                sub_txt = " ".join(sub_it["lines"]).strip()
                                if sub_txt:
                                    subitems.append(sub_txt)
                        if item_lines:
                            presentation_items.append({
                                "text": " ".join(item_lines),
                                "subitems": subitems,
                            })
        elif heading == "動画":
            for b in blocks:
                if b["type"] == "p" and b["text"]:
                    lbl, url = extract_link_label_and_url(b["text"])
                    if url:
                        video_url = url
                        video_label = lbl
                    elif b["text"].startswith("※"):
                        official_notes.append(b["text"])
        else:
            body_sections.append((heading, blocks))

    # Determine transcript status
    transcript_texts = []
    for heading, blocks in body_sections:
        for b in blocks:
            if b["type"] == "p" and b["text"]:
                transcript_texts.append(b["text"])
    joined_body = "\n".join(transcript_texts)
    if not transcript_texts or (len(joined_body) < 40 and "作成中" in joined_body):
        transcript_status = "作成中"
    else:
        transcript_status = "公開済"

    has_redaction_notice = any("削除" in n or "不適切な表現" in n for n in official_notes)

    # Render Markdown
    md_lines: list[str] = []
    md_lines.append("---")
    md_lines.append(f"date: {date_str}")
    if weekday:
        md_lines.append(f"weekday: {weekday}")
    md_lines.append(f'title: "{title.replace(chr(34), chr(92) + chr(34))}"')
    md_lines.append(f"category: {category}")
    md_lines.append(f"source_url: {session_meta['url']}")
    if parser.page_id:
        md_lines.append(f'page_id: "{parser.page_id}"')
    if updated_iso:
        md_lines.append(f"updated: {updated_iso}")
    md_lines.append(f"fetched_at: {fetched_date}")
    if video_url:
        md_lines.append(f"video_url: {video_url}")
    md_lines.append(f"transcript_status: {transcript_status}")
    md_lines.append(f"has_redaction_notice: {'true' if has_redaction_notice else 'false'}")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(f"# {title}")
    md_lines.append("")

    # Metadata summary bullets
    date_disp = f"{date_str}（{weekday}）" if weekday else date_str
    md_lines.append(f"- **開催日**: {date_disp}")
    md_lines.append(f"- **種別**: {category}")
    meta_parts = []
    if parser.page_id:
        meta_parts.append(f"ページ番号: {parser.page_id}")
    if updated_iso:
        meta_parts.append(f"更新日: {updated_iso}")
    meta_parts.append(f"取得日: {fetched_date}")
    md_lines.append(f"- **出典**: [兵庫県公式ページ]({session_meta['url']})（{' / '.join(meta_parts)}）")
    if video_url:
        md_lines.append(f"- **動画**: [{video_label or '知事会見を動画で見る'}]({video_url})")
    else:
        md_lines.append("- **動画**: 公式ページにリンク掲載なし")
    md_lines.append(f"- **議事録ステータス**: {transcript_status}")
    for note in official_notes:
        md_lines.append(f"- **公式注記**: {note}")
    md_lines.append("")

    # Presentation items
    md_lines.append("## 発表項目・配布資料")
    md_lines.append("")
    if presentation_items:
        for idx, it in enumerate(presentation_items, 1):
            md_lines.append(f"{idx}. {it['text']}")
            for sub in it["subitems"]:
                md_lines.append(f"   - {sub}")
    else:
        md_lines.append("（公式ページに発表項目の記載なし）")
    md_lines.append("")

    # Body sections (冒頭, 知事記者会見内容, 質疑応答, etc.)
    for heading, blocks in body_sections:
        md_lines.append(f"## {heading}")
        md_lines.append("")
        is_dialogue = heading in ("質疑応答", "冒頭")
        rendered_any = False
        for b in blocks:
            if b["type"] == "p":
                txt = b["text"]
                if not txt:
                    continue
                if is_dialogue and is_speaker_label(txt):
                    if rendered_any:
                        md_lines.append("")
                    md_lines.append(f"**{txt}**")
                    md_lines.append("")
                else:
                    md_lines.append(txt)
                    md_lines.append("")
                rendered_any = True
            elif b["type"] == "list":
                lst = b["list"]
                for idx, it in enumerate(lst["items"], 1):
                    prefix = f"{idx}. " if lst["type"] == "ol" else "- "
                    md_lines.append(prefix + " ".join(it["lines"]))
                md_lines.append("")
                rendered_any = True
        if not rendered_any:
            md_lines.append("（記載なし）")
            md_lines.append("")

    # Clean trailing blank lines -> single newline
    content = "\n".join(md_lines).rstrip() + "\n"

    # Extract concise presentation item titles for index table
    short_items = []
    for it in presentation_items:
        lbl, _ = extract_link_label_and_url(it["text"])
        lbl_clean = re.sub(r"（PDF[：:][^）]+）$", "", lbl).strip()
        short_items.append(lbl_clean)

    return {
        "markdown": content,
        "title": title,
        "date": date_str,
        "weekday": weekday,
        "category": category,
        "source_url": session_meta["url"],
        "page_id": parser.page_id,
        "updated": updated_iso,
        "video_url": video_url,
        "transcript_status": transcript_status,
        "has_redaction_notice": has_redaction_notice,
        "official_notes": official_notes,
        "presentation_items": short_items,
        "char_count": len(joined_body),
    }


def assign_filenames(sessions: list[dict]) -> list[tuple[dict, str]]:
    date_counts: dict[str, int] = {}
    for s in sessions:
        date_counts[s["date"]] = date_counts.get(s["date"], 0) + 1

    result = []
    for s in sessions:
        d = s["date"]
        suffix = s.get("suffix", "")
        if date_counts[d] > 1 and suffix:
            clean_suffix = suffix.lstrip("_")
            fname = f"{d}_{clean_suffix}.md"
        else:
            fname = f"{d}.md"
        result.append((s, fname))
    return result


def build_year_readme(year: str, records: list[dict], fetched_date: str) -> str:
    published_cnt = sum(1 for r in records if r["transcript_status"] == "公開済")
    draft_cnt = sum(1 for r in records if r["transcript_status"] != "公開済")
    redacted_cnt = sum(1 for r in records if r["has_redaction_notice"])

    lines = [
        f"# {year}年 兵庫県知事記者会見 議事録一覧",
        "",
        f"- **出典**: [兵庫県｜記者会見](https://web.pref.hyogo.lg.jp/governor/cate3_603.html)（令和7年度下期バックナンバーの1〜3月分・令和8年度上期バックナンバー・最新一覧を統合）",
        f"- **最終取得日**: {fetched_date}",
        f"- **収録回数**: 全 {len(records)} 回（議事録公開済: {published_cnt} 回 / 作成中: {draft_cnt} 回 / 一部削除注記あり: {redacted_cnt} 回）",
        "- **注記**: 県公式サイト上の議事録は「発言の趣旨を損なわない程度に整理」されたものであり、発言の完全逐語録ではない点に留意すること（必要時は各回の動画URLと照合する）。",
        "",
        "| 回 | 開催日 | 種別 | 発表項目 | 議事録 | 備考 | リンク |",
        "|---:|---|---|---|---|---|---|",
    ]

    for idx, r in enumerate(records, 1):
        wd = r["weekday"].replace("曜日", "") if r["weekday"] else ""
        date_cell = f"{r['date']}（{wd}）" if wd else r["date"]
        if r["presentation_items"]:
            items_joined = " / ".join(r["presentation_items"])
            if len(items_joined) > 65:
                items_joined = items_joined[:62] + "…"
            items_cell = items_joined.replace("|", "｜")
        else:
            items_cell = "（発表項目記載なし）"

        status_cell = r["transcript_status"]
        notes = []
        if r["has_redaction_notice"]:
            notes.append("一部削除注記あり")
        if not r["video_url"]:
            notes.append("動画リンクなし")
        note_cell = "・".join(notes) if notes else "-"

        link_cell = f"[議事録](./{r['filename']}) / [公式]({r['source_url']})"
        lines.append(
            f"| {idx:02d} | {date_cell} | {r['category']} | {items_cell} | {status_cell} | {note_cell} | {link_cell} |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: convert_kaiken.py <sessions_json> <html_dir> <out_year_dir> [year]")
        sys.exit(1)

    sessions_json = Path(sys.argv[1])
    html_dir = Path(sys.argv[2])
    out_dir = Path(sys.argv[3])
    year = sys.argv[4] if len(sys.argv) >= 5 else out_dir.name

    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = json.loads(sessions_json.read_text(encoding="utf-8"))
    fetched_date = dt.date.today().isoformat()

    records = []
    for s, fname in assign_filenames(sessions):
        html_path = html_dir / f"{s['slug']}.html"
        if not html_path.exists():
            print(f"[WARN] Missing HTML: {html_path}", file=sys.stderr)
            continue
        html_text = html_path.read_text(encoding="utf-8", errors="replace")
        res = convert_page(html_text, s, fetched_date)
        res["filename"] = fname
        (out_dir / fname).write_text(res["markdown"], encoding="utf-8")
        records.append(res)

    readme_text = build_year_readme(year, records, fetched_date)
    (out_dir / "README.md").write_text(readme_text, encoding="utf-8")

    # Write machine-readable metadata index for downstream analysis
    summary_records = [
        {k: v for k, v in r.items() if k != "markdown"}
        for r in records
    ]
    (out_dir / "index.json").write_text(
        json.dumps(summary_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Generated {len(records)} markdown files + README.md + index.json in {out_dir}")
    drafts = [r["filename"] for r in records if r["transcript_status"] != "公開済"]
    redacted = [r["filename"] for r in records if r["has_redaction_notice"]]
    print("Drafts:", drafts)
    print("Redaction notices:", redacted)


if __name__ == "__main__":
    main()
