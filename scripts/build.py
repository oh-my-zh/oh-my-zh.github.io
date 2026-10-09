#!/usr/bin/env python3
"""把 markdowns/ 下的 Markdown 构建成 _site/ 静态站点。

用法：
    python scripts/build.py

产物输出到 _site/，可直接用 GitHub Pages 部署，或本地
    python3 -m http.server 8000 --directory _site
预览。

评论数据来自 comments/comments.json（由 scripts/fetch_comments.py 生成）。
"""
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
MARKDOWNS_DIR = ROOT / "markdowns"
TEMPLATES_DIR = ROOT / "templates"
ASSETS_DIR = ROOT / "assets"
OUT_DIR = ROOT / "_site"
COMMENTS_FILE = ROOT / "comments" / "comments.json"

SITE_NAME = "我的浅书"
SITE_DESC = "这里发布浅书的故事、随笔与杂记。"

# (分类名, 锚点)，顺序即首页「分类索引」的展示顺序
CATEGORIES = [
    ("故事", "cat-gushi"),
    ("随笔", "cat-suibi"),
    ("杂记", "cat-zaji"),
]

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")


def parse_filename(name: str):
    """从 'YYYY-MM-DD-slug.md' 解析 (date, slug)。无日期前缀时返回 (None, name)。"""
    m = FILENAME_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return None, name[:-3] if name.endswith(".md") else name


def parse_markdown(text: str):
    """解析 frontmatter + 正文，返回 (meta: dict, body: str)。"""
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = yaml.safe_load("\n".join(lines[1:i])) or {}
            body = "\n".join(lines[i + 1:])
            return meta, body
    return {}, text


def load_comments():
    """读取评论数据，返回 list；文件不存在或损坏时返回空列表。"""
    if not COMMENTS_FILE.exists():
        return []
    try:
        data = json.loads(COMMENTS_FILE.read_text(encoding="utf-8"))
        return data.get("comments", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        return []


def comment_target(comment: dict):
    """评论归属：'index' 表示首页，否则是作品相对 url（如 'works/xxx.html'）。"""
    page = comment.get("page", "")
    path = urlparse(page).path.strip("/")
    if path in ("", "index.html"):
        return "index"
    return path


def render_comments_html(comments):
    """把评论列表渲染成 HTML 片段。"""
    if not comments:
        return '<p class="empty-state">还没有评论，来抢沙发～</p>'
    items = []
    for c in comments:
        name = html.escape(c.get("name") or "匿名访客")
        msg = html.escape(c.get("message") or "")
        t = html.escape(c.get("time") or "")
        items.append(
            '<div class="comment-item">'
            '<div class="comment-item-head">'
            f'<span class="comment-item-name">{name}</span>'
            f'<span class="comment-item-time">{t}</span>'
            '</div>'
            f'<p class="comment-item-body">{msg}</p>'
            '</div>'
        )
    return "\n".join(items)


def render_work(work: dict, template: str) -> str:
    return (
        template
        .replace("{{SITE_NAME}}", SITE_NAME)
        .replace("{{TITLE}}", html.escape(work["title"]))
        .replace("{{DATE}}", work["date"])
        .replace("{{CATEGORY}}", html.escape(work["category"]))
        .replace("{{CAT_ANCHOR}}", work["anchor"])
        .replace("{{SUMMARY}}", html.escape(work["summary"]))
        .replace("{{CONTENT}}", work["body_html"])
        .replace("{{COMMENTS}}", work.get("comments_html", ""))
    )


def build():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "works").mkdir(parents=True)
    shutil.copytree(ASSETS_DIR, OUT_DIR / "assets")

    cname = ROOT / "CNAME"
    if cname.exists():
        shutil.copy2(cname, OUT_DIR / "CNAME")

    index_tpl = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    work_tpl = (TEMPLATES_DIR / "work.html").read_text(encoding="utf-8")

    comments = load_comments()
    category_names = [c for c, _ in CATEGORIES]
    works = []
    for md_file in sorted(MARKDOWNS_DIR.rglob("*.md")):
        rel = md_file.relative_to(MARKDOWNS_DIR)
        category_from_dir = rel.parts[0] if len(rel.parts) > 1 else None
        date, slug = parse_filename(rel.parts[-1])
        meta, body_text = parse_markdown(md_file.read_text(encoding="utf-8"))
        title = str(meta.get("title", slug)).strip()
        summary = str(meta.get("summary", "")).strip()
        if category_from_dir in category_names:
            category = category_from_dir
        else:
            category = str(meta.get("category", "随笔")).strip()
            if category not in category_names:
                category = "随笔"
        body_html = markdown.markdown(
            body_text,
            extensions=["extra", "sane_lists"],
        )

        anchor = next((a for c, a in CATEGORIES if c == category), "cat-suibi")

        out_name = f"{date}-{slug}.html" if date else f"{slug}.html"
        url = f"works/{out_name}"

        work = {
            "date": date or "",
            "slug": slug,
            "title": title,
            "category": category,
            "summary": summary,
            "anchor": anchor,
            "body_html": body_html,
            "url": url,
            "out_name": out_name,
            "comments_html": "",
        }
        works.append(work)

    works.sort(key=lambda w: w["date"], reverse=True)

    # 评论按归属分组：URL 匹配 → 标题匹配（旧格式）→ 首页兜底
    index_comments = []
    work_comments = {}
    url_to_work = {w["url"]: w for w in works}
    title_to_work = {w["title"]: w for w in works}
    for c in comments:
        target = comment_target(c)
        if target == "index":
            index_comments.append(c)
            continue
        w = url_to_work.get(target)
        if w is None:
            w = title_to_work.get((c.get("page") or "").strip())
        if w is None:
            w = title_to_work.get(target)
        if w is not None:
            work_comments.setdefault(w["url"], []).append(c)
        else:
            index_comments.append(c)

    for w in works:
        w["comments_html"] = render_comments_html(work_comments.get(w["url"], []))

    # 归属完成后，再渲染并写作品页（此时评论已就位）
    for w in works:
        page = render_work(w, work_tpl)
        (OUT_DIR / "works" / w["out_name"]).write_text(page, encoding="utf-8")

    # 首页「最新发布」列表
    if works:
        cards = []
        for w in works:
            cards.append(
                '<article class="work-card">\n'
                f'            <p class="work-date">{w["date"]}</p>\n'
                f'            <h3><a href="{w["url"]}">{html.escape(w["title"])}</a></h3>\n'
                f'            <p>{html.escape(w["summary"])}</p>\n'
                f'            <span class="work-meta"><a class="work-cat" href="#{w["anchor"]}">{html.escape(w["category"])}</a></span>\n'
                '          </article>'
            )
        latest_html = "\n".join(cards)
    else:
        latest_html = '<p class="empty-state">暂无发布</p>'

    # 首页「分类索引」
    groups = []
    for cat, anchor in CATEGORIES:
        items = [w for w in works if w["category"] == cat]
        if items:
            lis = "\n".join(
                f'<li><a href="{w["url"]}">{html.escape(w["title"])}</a></li>'
                for w in items
            )
            body = f"<ul>\n{lis}\n</ul>"
        else:
            body = '<p class="empty-state">暂无作品</p>'
        groups.append(
            f'<div class="category-group" id="{anchor}">\n<h3>{cat}</h3>\n{body}\n</div>'
        )
    categories_html = "\n".join(groups)

    page = (
        index_tpl
        .replace("{{SITE_NAME}}", SITE_NAME)
        .replace("{{SITE_DESC}}", SITE_DESC)
        .replace("{{LATEST}}", latest_html)
        .replace("{{CATEGORIES}}", categories_html)
        .replace("{{COMMENTS}}", render_comments_html(index_comments))
    )
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")

    print(f"构建完成：{len(works)} 篇作品，{len(comments)} 条评论 → {OUT_DIR}")


if __name__ == "__main__":
    build()
