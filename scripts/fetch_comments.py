#!/usr/bin/env python3
"""从 Gmail 读取评论邮件，生成 comments/comments.json 供构建脚本渲染。

用法：
    python scripts/fetch_comments.py            # 读取未读评论，合并进 comments.json
    python scripts/fetch_comments.py --mark-read  # 读取并把处理过的邮件标记为已读

配置（二选一，推荐前者，不会进入 git）：
    1. 在 scripts/.env.local 里写两行（该文件已被 .gitignore 忽略）：
           GMAIL_USER=你的邮箱@gmail.com
           GMAIL_APP_PASSWORD=你的应用专用密码
    2. 或设置环境变量 GMAIL_USER、GMAIL_APP_PASSWORD

应用专用密码获取：Google 账号需先开启两步验证，然后在
「Google 账号 → 安全 → 应用专用密码」为「邮件」生成 16 位应用专用密码。
"""
import email
import email.utils
import hashlib
import imaplib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMENTS_FILE = ROOT / "comments" / "comments.json"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SUBJECT_KEYWORD = "收到一条新评论"  # Web3Forms 邮件标题「【我的浅书】收到一条新评论」

# 邮件正文里出现的字段名（不区分大小写），值可为多行
FIELD_NAMES = {"name", "email", "message", "page"}


def load_config():
    env = {}
    env_file = Path(__file__).with_name(".env.local")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")

    mail_addr = os.environ.get("GMAIL_USER") or env.get("GMAIL_USER", "").strip()
    auth_code = os.environ.get("GMAIL_APP_PASSWORD") or env.get("GMAIL_APP_PASSWORD", "").strip()
    return mail_addr, auth_code


def decode_text(part):
    """把 MIME part 解码为文本，尽量按声明的 charset 解码。"""
    charset = part.get_content_charset() or "utf-8"
    payload = part.get_payload(decode=True)
    if payload is None:
        return part.get_payload() or ""
    return payload.decode(charset, errors="replace")


def extract_plain_text(msg):
    """优先返回 text/plain，否则用 text/html 去掉标签。"""
    text = None
    html_text = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and text is None:
                text = decode_text(part)
            elif ctype == "text/html" and html_text is None:
                html_text = decode_text(part)
    else:
        if msg.get_content_type() == "text/plain":
            text = decode_text(msg)
        else:
            html_text = decode_text(msg)

    if text:
        return text
    if html_text:
        return re.sub(r"<[^>]+>", " ", html_text)
    return ""


def parse_fields(body):
    """从 Web3Forms 正文里解析字段。字段名单独成行，值在下一行起。"""
    fields = {}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        candidate = lines[i].strip().rstrip(":").strip().lower()
        if candidate in FIELD_NAMES:
            value_lines = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip().rstrip(":").strip().lower()
                if nxt in FIELD_NAMES:
                    break
                value_lines.append(lines[j].strip())
                j += 1
            fields[candidate] = "\n".join(v for v in value_lines if v).strip()
            i = j
        else:
            i += 1
    return fields


def mail_date(msg):
    dt = email.utils.parsedate_to_datetime(msg.get("Date"))
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def msg_id(msg):
    raw = msg.get("Message-ID") or msg.get("Date") or ""
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def load_existing():
    if COMMENTS_FILE.exists():
        try:
            data = json.loads(COMMENTS_FILE.read_text(encoding="utf-8"))
            return data.get("comments", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_comments(comments):
    COMMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMENTS_FILE.write_text(
        json.dumps({"comments": comments}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_folders(mail):
    """列出邮箱里所有文件夹名。"""
    folders = ["INBOX"]
    try:
        status, data = mail.list()
        if status == "OK":
            for item in data:
                if isinstance(item, bytes):
                    item = item.decode("utf-8", errors="replace")
                m = re.search(r'"([^"]+)"\s*$', item)
                if m and m.group(1) and m.group(1) not in folders:
                    folders.append(m.group(1))
    except imaplib.IMAP4.error:
        pass
    return folders


def should_search(folder):
    """只搜收件箱和垃圾邮件类文件夹，跳过已发送/草稿/回收站等。"""
    low = folder.lower()
    if low == "inbox":
        return True
    return "spam" in low or "junk" in low or "垃圾" in folder


def main():
    mark_read = "--mark-read" in sys.argv
    mail_addr, auth_code = load_config()
    if not mail_addr or not auth_code:
        print("跳过拉取评论：未配置 GMAIL_USER / GMAIL_APP_PASSWORD（GitHub secrets 或 scripts/.env.local）")
        sys.exit(0)

    comments = load_existing()
    existing_ids = {c.get("id") for c in comments}
    added = 0

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        mail.login(mail_addr, auth_code)

        for folder in list_folders(mail):
            if not should_search(folder):
                continue
            try:
                status, _ = mail.select(folder)
            except imaplib.IMAP4.error:
                continue
            if status != "OK":
                continue

            # 优先查未读，为空则查全部（靠 Message-ID 去重避免重复）
            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                status, data = mail.search(None, "ALL")
            if status != "OK" or not data:
                continue

            nums = data[0].split()
            print(f"[{folder}] 待检查 {len(nums)} 封")

            for num in nums:
                status, msg_data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject_text = ""
                for part, enc in email.header.decode_header(msg.get("Subject") or ""):
                    subject_text += part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
                if SUBJECT_KEYWORD not in subject_text:
                    continue

                fields = parse_fields(extract_plain_text(msg))
                if not fields.get("message"):
                    continue

                mid = msg_id(msg)
                if mid in existing_ids:
                    continue

                comments.append(
                    {
                        "id": mid,
                        "name": fields.get("name") or "匿名访客",
                        "message": fields.get("message", ""),
                        "page": fields.get("page", ""),
                        "time": mail_date(msg),
                    }
                )
                existing_ids.add(mid)
                added += 1

                if mark_read:
                    try:
                        mail.store(num, "+FLAGS", "\\Seen")
                    except imaplib.IMAP4.error:
                        pass
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    comments.sort(key=lambda c: c.get("time", ""), reverse=True)
    save_comments(comments)
    print(f"新增 {added} 条评论，共 {len(comments)} 条，已写入 {COMMENTS_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
