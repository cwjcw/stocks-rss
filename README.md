# 我的A股盯盘RSS

stocks-rss/
├─ configs/
│  └─ users/                     # 每个用户一份 YAML 配置
│     ├─ alice.yaml
│     └─ bob.yaml
├─ public/                       # 生成的静态 RSS 会放到这里（将被部署到 Cloudflare Pages）
│  └─ feeds/
│     └─ (自动生成 *.xml)
├─ src/
│  ├─ main.py                    # 单个用户：抓数据→生成一个 RSS
│  ├─ build_all.py               # 多用户：批量读 configs/users/*.yaml → 生成多个 RSS
│  ├─ data_providers.py
│  ├─ rss_builder.py
│  ├─ utils.py
│  └─ defaults.yaml              # 全局默认项（标题、代理等）
├─ requirements.txt
├─ README.md
├─ LICENSE
└─ .github/
   └─ workflows/
      └─ cf_pages_rss.yml        # GitHub Actions：定时抓取→生成 RSS→部署 Cloudflare Pages


> 实时查看 **涨跌**、**北向资金**、**主力/超大/大/中/小单净流入**，输出为 **RSS** 订阅源，可被 Folo / Inoreader / Tiny Tiny RSS 等阅读器订阅。基于 **AKShare** 实现。

## 功能
- 自定义股票清单
- 实时快照（最新价、涨跌幅、成交额）
- 个股当日资金净流入（主力/超大/大/中/小单）
- 北向资金当日净流入（沪股通/深股通/合计）
- 输出 RSS（XML）

## 快速开始

```bash
pip install -r requirements.txt
python src/main.py
# RSS 文件默认输出到 public/a-shares.xml
```

# 非常重要
出于隐私的需要，YAML文件是必需的，但我已设置为ignore,因此，下面是一份专门教大家如何编写**私有 YAML 配置**。我写得尽量详细、一步一图纸，照着做就能跑起来。

---

# Stocks RSS – 私有 YAML 配置指南

本项目用于生成“按自选股实时行情 + 资金流”的 RSS 源（支持每位用户独立订阅、独立 token）。
**出于安全考虑，用户清单 YAML 文件不会提交到 GitHub**（已在 `.gitignore` 中忽略），每个使用者需要在自己机器上创建一份私有配置。

---

## 目录结构（与 YAML 相关的部分）

```
.
├─ configs/
│  ├─ users/                # ← 放每个用户的私有 YAML（不会进仓库）
│  │  ├─ jerry.yaml         # 示例：每个用户一个文件
│  │  └─ <your_id>.yaml
├─ src/
│  ├─ build_all.py          # 读取 configs/users/*.yaml 并生成 RSS
│  └─ data_providers.py     # 行情/资金抓取适配
└─ /var/www/stockrss/feeds/ # ← 生成的 RSS 输出目录（由部署者设定）
```

> 注意：`configs/users/*.yaml` 被忽略提交，**不要**把真实 YAML 推到 GitHub 公网仓库。

---

## 一分钟上手

1. 在本地创建目录（如果没有的话）：

   ```bash
   mkdir -p configs/users
   ```

2. 新建你的文件 `configs/users/<你的ID>.yaml`，粘贴下面的模板（按需改）：

   ```yaml
   user_id: "alice"                 # 你的用户ID（文件名也建议用它）
   title: "Alice 的盯盘"            # RSS 标题（可中文）
   stocks:                          # 自选股清单（大小写不敏感）
     - sh600519   # 贵州茅台
     - sz000858   # 五粮液
     - sz300750   # 宁德时代
     - sh688981   # 中芯国际（科创板用 sh688xxx）
   token: "A1B2C3"                  # 6~32 位字母数字，作为订阅URL中的“密码”
   ```

3. 生成 RSS：

   ```bash
   # 建议使用项目自带虚拟环境的 Python
   python src/build_all.py
   ```

4. 找到输出文件（部署者约定的输出目录，比如 `/var/www/stockrss/feeds/`）：

   ```
   /var/www/stockrss/feeds/alice-A1B2C3.xml
   ```

5. 订阅 URL（部署者提供的域名，例如）：

   ```
   https://stockrss.xxx.cn/feeds/alice-A1B2C3.xml
   ```

---

## YAML 字段详解

| 字段        | 类型/示例                         | 说明                                                                                                      |
| --------- | ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| `user_id` | `"alice"`                     | **用户唯一 ID**。建议与文件名一致（`alice.yaml`）。只支持字母数字与下划线/短横线。                                                     |
| `title`   | `"Alice 的盯盘"`                 | 生成的 RSS `<title>`，可中文。                                                                                  |
| `stocks`  | `["sh600519","sz000858",...]` | **股票代码列表**。支持带前缀写法（推荐），如 `sh600519`、`sz000001`、`sh688xxx`、`sz300xxx`。不带前缀也可（程序会自动推断），但**强烈建议带前缀**以减少歧义。 |
| `token`   | `"A1B2C3"`                    | **订阅令牌**，6–32 位的字母或数字。订阅 URL 必须带上它，等同于“私密地址的一部分”。需要轮换时直接改这里即可。                                          |

> **安全提示**：`token` 不是强加密，只是“带密钥的私有链接”。不要把你的订阅链接随意公开分享；泄露后请在 YAML 里更换 `token`，旧链接会立即失效。

---

## 股票代码如何书写？

* **上交所**：`sh` + 6 位代码，例如 `sh600519`（主板）、`sh688981`（科创板）。
* **深交所**：`sz` + 6 位代码，例如 `sz000001`（主板）、`sz300750`（创业板）。
* 也支持不带前缀的 6 位代码，程序会自动补全，但为避免歧义，**推荐始终带前缀**。
* YAML 中可以写注释（以 `#` 开头），示例：

  ```yaml
  stocks:
    - sh603000   # 示例注释：人民网
    - sz000002   # 示例注释：万科A
  ```

---

## 多用户如何配置？

**一个用户 = 一个 YAML 文件。**
举例：`configs/users/jerry.yaml` 与 `configs/users/chensi.yaml` 各自维护独立自选股与 token：

```yaml
# configs/users/jerry.yaml
user_id: "jerry"
title: "Jerry 的盯盘"
stocks:
  - sz000981   # 山子高科
  - sz301293   # 三博脑科
  - sz300825   # 阿尔特
  - sh603004   # 鼎龙科技
  - sh603019   # 中科曙光
  - sh600096   # 云天化
token: "811118"
```

```yaml
# configs/users/chensi.yaml
user_id: "chensi"
title: "Chensi 的盯盘"
stocks:
  - sh601318   # 中国平安（示例）
  - sz000858   # 五粮液（示例）
  - sh600036   # 招商银行（示例）
token: "870809"
```

生成后会得到：

```
/var/www/stockrss/feeds/jerry-811118.xml
/var/www/stockrss/feeds/chensi-870809.xml
```

---

## 常见问题（踩坑必看）

### 1）运行时提示 `Can not decode value starting with character '<'`

* 你的 YAML 文件**开头被粘贴进了 HTML**（比如从网页复制带了 `<` 标签），或文件不是纯文本。
* **解决**：用文本编辑器（推荐 VS Code / nano），删除所有非 YAML 内容；确保**第一行**就是 `user_id: "..."`。
* 文件编码用 **UTF-8**；不要用富文本编辑器（如 Word/记事本的 RTF）。

### 2）`YAML 解析失败` / 缩进错误

* YAML 使用**空格**缩进（推荐每级 2 个空格），不要用 Tab。
* 字符串建议加引号，尤其包含中文或前导零时（例如 `token: "001122"`）。
* 可以用下面的快速校验命令（需已安装 Python 和 PyYAML）：

  ```bash
  python - <<'PY'
  import yaml,glob,sys; ok=True
  for p in sorted(glob.glob('configs/users/*.yaml')):
      try:
          data=yaml.safe_load(open(p,'r',encoding='utf-8'))
          assert isinstance(data,dict) and 'user_id'in data and 'stocks'in data and 'token'in data
          print('[OK]',p,'=>',data['user_id'],len(data['stocks']),'stocks')
      except Exception as e:
          print('[ERR]',p,'->',e); ok=False
  sys.exit(0 if ok else 2)
  PY
  ```

### 3）生成成功但访问 403

* 订阅 URL **必须**带 `-<token>.xml`。例如：

  ```
  ✅ /feeds/alice-A1B2C3.xml
  ❌ /feeds/alice.xml
  ```
* 如果你用的是部署者提供的域名（如 `https://stockrss.cuixiaoyuan.cn`），访问无 token 的链接会被 Nginx 拒绝（403）。

### 4）看不到最新数据？

* 本项目通常按**工作日交易时段每 10 分钟**生成一次。
* 部署者可在服务器上查看生成日志（例如：`tail -n 100 /home/<user>/code/stocks-rss/logs/run.log`）。
* Cloudflare/浏览器缓存：我们已设置 `Cache-Control: no-store`；如仍怀疑缓存，可强刷或在 URL 后增加无意义参数（`?t=...`）。

### 5）token 要多久换一次？

* 视个人需求，可随时在 YAML 里更换 `token`。更换后**旧链接立即失效**。

---

## 进阶：给团队同事也用

* 每个同事各自创建一份 `configs/users/<id>.yaml`，设定不同的 `token`。
* 将**本地运行结果**部署到同一后端输出目录（如 `/var/www/stockrss/feeds/`），就能同时服务多位同事的订阅。
* **不要**把私人 YAML 提交到仓库（已通过 `.gitignore` 默认忽略）。

---

## 生成与订阅（完整流程备忘）

1. 填好 `configs/users/<id>.yaml`
2. 执行：

   ```bash
   python src/build_all.py
   ```
3. 在输出目录找到 `/<id>-<token>.xml`
4. 在你的订阅器（例如 Folo）中添加：

   ```
   https://<你的域名>/feeds/<id>-<token>.xml
   ```

   示例：

   ```
   https://stockrss.cuixiaoyuan.cn/feeds/jerry-811118.xml
   ```

---

## 免责声明

本项目用于学习与个人使用。行情与资金数据来源于第三方接口（AkShare 封装），可能受接口变更影响。请理性参考数据，不构成任何投资建议。

---

有问题或改进建议，欢迎在 Issues 里反馈（请勿上传或粘贴你的私有 `*.yaml` 内容与真实 token）。
