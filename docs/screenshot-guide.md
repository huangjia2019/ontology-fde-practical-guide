# 如何重新生成工作台截图

README 中的四张图都来自本地工作台。改过规则或界面后，用同一套申请重新演练，再截图；不要在旧图上覆盖文字。

只是阅读图片、运行退款项目，不需要安装制图工具。下面的步骤供需要更新截图的读者和维护者使用，命令均在仓库根目录执行。

## 一次生成四张图

先运行项目检查：

```bash
uv run python -m unittest discover -s tests -v
python3 run.py evaluate
```

制图使用可选依赖 Playwright。已有 Google Chrome 时，可以直接运行：

```bash
uv run --with playwright python tools/capture_screenshots.py --channel chrome
```

也可以安装 Playwright 配套的 Chromium 后运行：

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python tools/capture_screenshots.py
```

如需指定其他已经安装的 Chrome 或 Chromium，将 `CHROME_BIN` 设为浏览器可执行文件的路径。它与 `--channel` 二选一：

```bash
CHROME_BIN=/path/to/chromium uv run --with playwright python tools/capture_screenshots.py
```

首次安装依赖或浏览器可能需要联网。截图时只访问本机服务，不用 API key，不访问 CDN，也不连接真实业务系统。普通项目运行仍不依赖 Playwright。

脚本会启动一个独立的本机服务，使用系统分配的空闲端口。每张图之前先点击“重置演练”，需要执行时再点击“执行模拟”，最后切到对应视图。它不会使用已经打开的工作台，也不会改动另一进程中的演练状态。完成后会关闭浏览器和临时服务。

## 四张图分别看什么

| 文件 | 申请与视图 | 核对内容 |
|---|---|---|
| `01-ontology-workbench.png` | 遥控器单 `YF-R-0311`，业务对象 | 347 元；发票状态“待核实”；ERP 来源保留“本次查询未查到记录”；业务对象和来源编号都可读。 |
| `02-action-console.png` | 多出一分 `YF-R-0501`，退款处理 | 500.01 元；命中 `G-AMOUNT`；进入人工审核并生成审批材料，没有自动批准。 |
| `03-audit-trace.png` | 风控有异 `YF-R-0610`，决策记录 | 退款助手建议批准，风控要求复核；显示连续工具调用和人工接手结果，不得创建退款指令。 |
| `04-evaluation-dashboard.png` | 测试与评估 | 核心用例 36/36、故障回放 2/2；候选规则仍是草稿，缺失输入、业务审核和编译等条件尚未完成。 |

文件默认保存在 [assets/screenshots](assets/screenshots/) 下。浏览器视口为 1600×1000，缩放比例为 100%；PNG 采用**全页截图**，所以实际高度随内容变化，不会为了凑固定尺寸裁掉底部。

脚本检查 API 结果、可见文字、JavaScript 错误、横向溢出和图片尺寸。它也会区分两笔申请的发票依据：`YF-R-0311` 是查询 `not_found`、业务状态 `unknown`；`YF-R-0500` 则有 ERP 的 `confirmed_no_invoice` 确认，业务状态为 `none`。

需要先放到审阅目录时，使用 `--output-dir` 指定一个固定的工作目录；看过图片后再替换正式图片。不要把个人电脑的绝对路径写进仓库说明或公开截图。

## 人工再看一遍

自动检查不能判断所有排版问题。替换图片前，请打开四张 PNG，逐一确认：

1. 图里的对象编号、金额、状态、规则编号与页面实际返回一致。500 元与 500.01 元不要混用。
2. “未查到记录”没有被改成“确认没有发票”；“已批准”没有被写成“已到账”。
3. 四周没有裁切，中文能读清，长编号没有盖住相邻字段。完整 JSON 面板本身可滚动；截图只展示它当前可见的部分，完整记录可在页面复制。
4. 工具调用区、风控冲突和生产执行限制都在图内。客户名称、字段名、API 编号保留底层原样，不为统一语言而修改业务事实。
5. 图中没有本机文件路径、账号信息、密钥或其他窗口。首次使用说明在截图中折叠，页面里仍可展开阅读。

## 自己操作后截图

```bash
uv run ontology-fde serve --port 8000
```

打开 `http://127.0.0.1:8000`，选择申请，先读取事实或生成建议，再决定是否执行模拟。复制需要保留的决策记录后，才能重置演练。

网址可以用 `?view=audit&case=YF-R-0610` 预选视图和申请，但打开网址不会执行、也不会重置业务数据。修改状态始终需要明确点击按钮。
