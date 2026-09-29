# Trends 自动热点聚合工作流

自动抓取**国外科技 / 创业**热点头条，推送到 WordPress 页面 **`/trends/`**。
无需浏览器、无需自建 cron 服务器、无需付费 API。

```
GitHub Actions（每 30 分钟）
   └─> fetch_trends.py     →  trends_data.json
         └─> build_trends.py --push  →  WP REST API  →  /trends/
```

## 文件说明

| 文件 | 作用 |
|------|------|
| `fetch_trends.py` | 从 5 个免密钥数据源抓取，写入 `trends_data.json` |
| `build_trends.py` | 渲染 HTML，并通过 REST 创建/更新 WP 页面（slug `trends`） |
| `add_trends_menu.py` | 一次性脚本：把 Trends 加入主导航菜单 |
| `.github/workflows/trends.yml` | 每 30 分钟跑一次 fetch + 发布 |
| `deploy.sh` | 一键把整套部署到 GitHub 并配置 secrets（见下） |
| `preview-home.png` / `preview-trends.png` | 首页入口横幅 / 热点页效果预览 |
| `sample-trends_data.json` | 真实输出样例，无需运行即可看数据结构 |

## ⚠️ 关于"云端自动部署"的说明

本工作流**必须放在你能联网 GitHub 的机器上运行**。当前执行环境（Wasmer sandbox）
的出口防火墙**封掉了 `github.com` / `api.github.com`**（已实测，关掉沙盒层仍为 `000`），
因此无法在这里替你 `git push` 或调 GitHub API。

解决办法：把本目录文件下载到你**本地电脑**（装好 git + gh CLI 即可），本地联网
GitHub 正常，跑下面的一键脚本即可全自动完成。

## 一键部署（推荐）

1. 下载本目录到本地，进入目录：
   ```bash
   cd trends
   ```
2. 在 GitHub 生成一个 **PAT（Personal Access Token）**，权限勾选 `repo` 全选。
   生成地址：GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)。
3. 设置环境变量并运行：
   ```bash
   export GH_TOKEN=ghp_xxxxxxxxxxxx                 # 上面生成的 PAT
   export WP_APP_USER=xxxxxxxxxxxx 
   export WP_APP_PASS=xxxxxxxxxxxx       # WP Application Password，去掉空格
   ./deploy.sh
   ```
4. 脚本会自动：登录 gh → 创建仓库 `trends-autopilot` → 推送代码 → 配置
   `WP_APP_USER` / `WP_APP_PASS` 两个 Actions secrets。

> 仓库默认建在 `sunfei0318-code` 名下，可用 `GH_USER` / `REPO_NAME` 环境变量覆盖。

## 手动部署（备选）

不想用脚本也行：
1. 在 GitHub 新建仓库，把本目录文件推上去（保留 `trends/` 结构；若想放仓库根，
   删掉 workflow 里的 `working-directory: trends` 两行）。
2. 仓库 → **Settings → Secrets and variables → Actions → New repository secret**，添加：
   - `WP_APP_USER` —— WordPress 登录名（`xxxxxxxxxxxx `）
   - `WP_APP_PASS` —— WordPress **Application Password**（去掉空格）
3. Actions → *Refresh trends page* → **Run workflow** 先跑一次确认，之后交给定时。

Application Password 在你的站点 **用户 → 个人资料 → Application Passwords** 下生成
（名称 `trends-bot`）。它**不能登录后台**，随时可吊销，吊销即停掉整条流水线，
不影响你的真实密码。

## 本地手动运行

```bash
export WP_APP_USER=sunfei0318
export WP_APP_PASS=<application-password>
python3 fetch_trends.py           # 抓取，写 trends_data.json
python3 build_trends.py --push    # 推送到 /trends/
```

不带 `--push` 时只渲染并保存 `trends_page.html`，方便上线前检查标记。

## 数据源

| 数据源 | 提供内容 | 成本 |
|--------|----------|------|
| Hacker News (Algolia API) | 首页高赞故事，含分数与评论数 | 免费、免密钥 |
| Google News RSS | Technology 主题 + AI/创业关键词 | 免费、免密钥 |
| TechCrunch RSS | 兜底新闻源 | 免费、免密钥 |
| GitHub search API | 近 30 天新建仓库按 star 排序 | 免费、未认证 60 次/小时 |
| dev.to API | 高互动开发者文章 | 免费、免密钥 |

各源独立容错：任一源不可达或改版，该分组显示空态提示，其余正常发布。

## 合规要点

- 页面**只索引标题 + 跳转原文**，绝不存储或转载正文 —— 聚合站版权风险最低的做法。
- 所有外链均带 `rel="noopener nofollow"`。
- **刻意不用 Reddit**：2026 年起 Reddit 对商业/变现用途要求书面授权 + 付费合同
  （约 $12k/月）；Twitter/X 读接口也收费。两者在选型阶段即被排除。

## 已上线状态

- **页面**：https://sun-pro.wasmer.app/trends/ （WP 页面 id 976）
- **入口**：主导航菜单 *Trends* + 首页横幅
- **收录**：Rank Math page-sitemap.xml（112 条，含 `/trends/`）

## 已知缺口

- **Rank Math 的 SEO 标题/描述未写入**：该站点安装未把 Rank Math meta 注册到 REST，
  且 metabox 的输入是展开折叠面板后才懒挂载的，自动化太脆弱。页面目前继承全站默认
  SEO 元信息。手动设置路径：编辑 `/trends/` → 滚到 **Rank Math SEO** 面板 → 展开
  **General** 填 Focus Keyword / SEO Title / Meta Description → **Update**。
  建议文案见 `SEO-SUGGESTIONS.md`。
