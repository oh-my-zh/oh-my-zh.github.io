# 我的浅书

一个纯静态的个人作品发布站，用于发布故事、随笔与杂记。**写 Markdown，GitHub Action 自动生成网页并部署**，浅色简洁风（纯白 · 靛蓝）。

## 如何发布一篇新作品

只需要两步：

**1. 新建一个 Markdown 文件。** 放到对应分类目录下：`markdowns/故事/`、`markdowns/随笔/` 或 `markdowns/杂记/`。文件名用 `YYYY-MM-DD-标题.md`（日期用发布日，标题建议用拼音或英文）。

文件开头写 frontmatter，下面写正文：

```markdown
---
title: 作品标题
summary: 一句话简介，会显示在首页卡片上
---

正文从这里开始，用标准 Markdown 语法：

- 段落之间空一行
- **加粗**、*斜体*、`行内代码`
- `>` 开头的引用块
- 一行 `---` 是分隔线
```

分类由文件所在的目录决定，frontmatter 里**不用再写 `category`**。

字段说明：

- `title`：作品标题（必填）
- `summary`：一句话简介，显示在首页卡片（可选）

**2. 提交并推送。** 推送后 GitHub Action 会自动构建并部署，无需其他操作。

## 本地预览

构建产物输出到 `_site/`（不提交到仓库）：

```bash
pip install -r scripts/requirements.txt
python scripts/build.py
python3 -m http.server 8000 --directory _site
# 然后访问 http://localhost:8000
```

## 目录结构

```
.
├── markdowns/                      # 你写 Markdown 的地方（按分类分目录）
│   ├── 故事/
│   ├── 随笔/
│   │   └── 2026-10-08-start-here.md
│   └── 杂记/
├── templates/                    # HTML 模板
│   ├── index.html                # 首页模板
│   └── work.html                 # 作品页模板
├── assets/                       # 样式、图标
├── scripts/
│   ├── build.py                  # 构建脚本（Markdown → HTML）
│   └── requirements.txt          # Python 依赖
├── .github/workflows/deploy.yml  # GitHub Actions 部署配置
└── _site/                        # 构建产物（自动生成，勿提交）
```

## 部署

- 推送 `main` 分支后，`.github/workflows/deploy.yml` 会自动构建并部署到 GitHub Pages。
- 首次使用前，在仓库 **Settings → Pages** 里把 Source 设为 **GitHub Actions**（Build and deployment 选 GitHub Actions）。
- 网站地址：`https://oh-my-zh.github.io/`

## 修改分类

分类在 [build.py](scripts/build.py) 顶部的 `CATEGORIES` 列表里定义。若要增删分类，改那里即可，首页「分类索引」会自动跟着变。

## 评论功能

访客在首页「留言」或作品页「评论」提交的内容，会通过 [Web3Forms](https://web3forms.com) 发送到你的邮箱，再由 GitHub Actions 定时拉取并公开展示在文章下方。

### 首次配置

1. 在 Web3Forms 注册并把**接收邮箱**设为你的 Gmail。
2. 在仓库 **Settings → Secrets and variables → Actions** 添加两个 secret：
   - `GMAIL_USER`：你的 Gmail 地址
   - `GMAIL_APP_PASSWORD`：Gmail 应用专用密码（需先开启两步验证）
3. 之后 `.github/workflows/deploy.yml` 会每 30 分钟自动读取邮箱评论、生成 `comments/comments.json` 并部署。

### 本地手动拉取评论

```bash
GMAIL_USER=你的邮箱@gmail.com GMAIL_APP_PASSWORD=你的应用密码 \
  python scripts/fetch_comments.py
```

评论数据保存在 `comments/comments.json`（由脚本自动生成并提交回仓库）。
