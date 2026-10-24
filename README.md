# Cursor 汉化补丁（静态注入版）

> 🔁 **本项目长期维护**：跟随 Cursor 版本持续适配，欢迎 [Issues](../../issues) 反馈问题和需求。

给 Cursor 的**自研界面**（Agent / Chat 面板、Settings、Changes 等）加简体中文，并在标题栏正中间放一个**实时额度挂件**（圆环 + 剩余百分比，悬停看明细）。

## 特性

- **汉化**：复用 [Ver3ce/cursor-zh](https://github.com/Ver3ce/cursor-zh) 的词典（MIT），把翻译脚本**静态注入**到 workbench 包，无需运行时注入工具——Cursor 3.x 已拒绝 `--remote-debugging-port`。
- **额度挂件**：从 Cursor 登录态读 token，调官方用量接口，经本机只读服务转发，标题栏实时展示用量。

## 目录结构

```
cursor-zh/
├── inline/
│   ├── patch.py          打补丁 / 重复打补丁（按版本自动备份）
│   ├── restore.py        还原（默认只检查，--apply 才写）
│   ├── translator.js     注入的翻译脚本（__DICT__ 占位）
│   ├── dict-extra.json   本地补词（优先于主词典）
│   └── screenshot_win.py 验证用窗口截图（无第三方依赖）
├── quota/
│   ├── server.py         额度本地只读服务（127.0.0.1:47821）
│   └── widget.js         标题栏额度挂件（注入）
├── dict/
│   └── zh-CN.json        cursor-zh 主词典
├── LICENSE
└── README.md
```

> `backup/<版本>/`（原始 workbench 备份）由 `patch.py` 首次运行时自动生成，不随本仓库分发。

## 快速开始

### 1. 配置 Cursor 安装路径（可选）

`patch.py` / `restore.py` 会自动尝试常见安装位置（`%LOCALAPPDATA%\Programs\Cursor` 等）；如果你的 Cursor 装在别处，设置环境变量即可（推荐，不改代码）：

```powershell
$env:CURSOR_APP_DIR = "D:\你的路径\Cursor\resources\app"
```

### 2. 打补丁（先完全退出 Cursor）

```bash
python inline/patch.py
```

流程：剥离旧补丁 → 与备份比对 → 注入 translator + 额度挂件 → 重算 `product.json` 校验值。看到 `verify: OK` 即成功。

### 3. 启动额度服务（挂件需要它）

服务只读转发 Cursor 用量，缓存在本机 `127.0.0.1:47821`。手动起：

```bash
pythonw quota/server.py
```

开机自启：在「启动」文件夹（`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`）放一个 vbs：

```vbs
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\path\to\pythonw.exe"" ""C:\path\to\cursor-zh\quota\server.py""", 0, False
```

把里面的两个路径改成你机器上的 `pythonw.exe` 与 `server.py` 绝对路径。

### 4. 重启 Cursor

重启后：菜单/侧栏/设置变中文；标题栏中间出现圆环「剩余 N%」，悬停看明细（自动模型 / API 用量 / 重置时间），点一下立即刷新，60 秒自动轮询。

## 还原

```bash
python inline/restore.py            # 只检查备份
python inline/restore.py --apply    # 真正还原，需先退出 Cursor
```

## 原理

- 修改 `resources/app/out/vs/workbench/workbench.desktop.main.js` 与 `workbench.glass.main.js`，在 `sourceMappingURL` 之前插入翻译脚本 + 额度挂件（约 90KB）。
- 同步重算 `product.json` 中 `workbench.desktop.main.js` 的 sha256（base64 无填充），避免启动报「installation appears to be corrupt」。
- 运行期：遍历文本节点与 `title/aria-label/placeholder` 属性，按词典精确/正则替换；`MutationObserver` 跟踪增量渲染。
- **不翻译**：Monaco、终端、输入框内容、Markdown 正文、AI 回复、代码块、文件名。

## 额度服务

```
Cursor 登录态(state.vscdb) ──▶ quota/server.py ──▶ Cursor API(GetCurrentPeriodUsage)
                                   └─ http://127.0.0.1:47821/usage ──▶ widget.js(标题栏)
```

- 只读：以只读方式直连 `state.vscdb` 取 token（不复制整个库，避免 500MB+ 库被写锁打断成 0 字节副本），不写、不外传。
- 端口 47821，仅监听 127.0.0.1；结果缓存 45 秒。
- 服务未起时挂件显示「额度 —」，每 10 秒自动重试。

## 注意事项

- **Cursor 自动更新会覆盖补丁**（文件被还原）。建议在 Cursor 设置把 `Update: Mode` 设为 `none` 关闭自动更新；失效后重跑一次 `patch.py` 即可。
- 大版本更新后若部分新文案又变回英文，往 `dict-extra.json` 加词再重打。
- 词典来源：[Ver3ce/cursor-zh](https://github.com/Ver3ce/cursor-zh)（MIT）。

## 许可证

复用 Ver3ce/cursor-zh 词典（MIT）。本仓库脚本以相同精神提供，详见 `LICENSE`。
