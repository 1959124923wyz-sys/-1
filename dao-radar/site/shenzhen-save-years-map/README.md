# 深圳 · 攒房地图

一个纯静态、无需 API Key 的深圳小区房价可视化。地图不是展示“元/㎡”，而是展示：

> **攒够整套房款所需年数 = 小区参考单价 × 假设面积 ÷（每月储蓄 × 12）**

默认每月储蓄 5,000 元、面积 90㎡。网页可切换 50/70/90/120㎡、修改每月储蓄、搜索小区和按区筛选，并可把参数写入分享链接。

## 数据口径

- 地图上的价格是公开网站的**小区挂牌/参考均价**，不是网签成交价，也不是估值。
- 初始包带 13 个已核对点位，覆盖深圳 10 个行政区/新区，确保下载后直接能看到全城分布；它们只是首屏样本，不代表完整小区库。
- `scripts/update_prices.py` 会尝试每天刷新这些小区；同时从房天下小区目录分批发现更多当前价格，再和一个公开的历史链家地理编码数据集按小区名匹配坐标。目录扫描会保存“下一页”游标，下一次定时任务继续往后扫，而不是每天只重复第一页。
- 历史链家数据**只用于坐标缓存**，不会把旧价格冒充成当前价格；其坐标来自高德体系时会先从 GCJ-02 近似转换为 WGS84，再叠加到 OpenStreetMap。
- 遇到 403、429、验证码、页面结构异常会停止该来源，不绕过验证；旧数据会保留，页面会显示刷新失败数量。

## 本地打开

直接双击 `index.html` 即可。需要联网加载 Leaflet 与 OpenStreetMap 瓦片。

也可以：

```bash
python -m http.server 8000
```

然后访问 `http://localhost:8000/`。

## 自动更新

```bash
pip install -r requirements.txt
python scripts/update_prices.py --discover-pages 8
```

脚本会更新 `data/communities.json` 与 `data/communities.js`。`communities.js` 是为了让网页即使从 `file://` 双击打开也不被浏览器跨域规则拦住。

仓库自带 `.github/workflows/refresh.yml`：每天 08:17（中国时区，等价 UTC 00:17）自动执行。GitHub 定时任务不是硬实时，可能延迟；公开仓库长期无活动时，GitHub 也可能暂停 scheduled workflows。

## 发布成任何人可访问的网页

最省事：把整个文件夹发布到一个 **public GitHub repository**，然后在该仓库 `Settings → Pages → Build and deployment → Deploy from a branch`，选择 `main` 和 `/(root)`，保存。稍后仓库 Settings/Pages 会显示公开 URL。

如果你不熟命令行，推荐 GitHub Desktop：`File → Add local repository` 选择本文件夹；若提示不是仓库则 `Create a repository`；然后 `Publish repository`，取消 Private；最后按上一段打开 Pages。

## 自动扩容的现实限制

没有官方/商业房产 API 的前提下，公开网页抓取不可能保证 100% 稳定。房天下、58、链家等都可能改 HTML、限流或要求验证。这个项目的策略是“**可验证地失败**”：不会伪造更新，也不会在失败时清空旧数据。

要长期做到上万小区稳定覆盖，建议后续把数据层替换成获得授权的房产数据源；前端和“攒房年数”逻辑无需改。
