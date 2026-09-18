# macOS / Linux 支持计划

> 状态：**已实施基础跨平台支持**（macOS/Linux 安装、启动和 Web GUI 已提供）。
> 最后分析：2025-09-18

## 可行性结论

**高度可行**。核心视频生成管道（内容提取、Vision 分析、LLM 草稿、PPTX 生成、Azure Speech TTS、字幕、FFmpeg 合成）已在 Linux/macOS 上经过验证或可原生运行。主要障碍集中在 Windows 专有组件：

- PowerPoint COM 自动化（Windows）以及 macOS PowerPoint 的 AppleScript 自动化（`powerpoint.py`）
- PowerShell 安装/启动脚本（`setup.ps1`、`run.ps1`）
- `pywin32` 依赖（已条件化，非阻塞）

## 当前跨平台状态速查

| 模块 | 文件 | macOS/Linux 状态 | 备注 |
|------|------|-----------------|------|
| 资源扫描 | `resources.py` | ✅ 完全兼容 | |
| 内容读取 | `presentation.py` | ✅ 完全兼容 | python-pptx、pypdf、python-docx、openpyxl 均跨平台 |
| Vision 分析 | `vision.py` | ✅ 完全兼容 | 纯 HTTP API |
| LLM 草稿 | `llm.py` | ✅ 完全兼容 | |
| Azure Speech TTS | `speech.py` | ✅ 兼容 | SDK 支持 macOS；当前版本已通过 Python 编译检查 |
| 字幕生成 | `subtitles.py` | ✅ 完全兼容 | |
| PPTX 创建 | `presentation.py` | ✅ 完全兼容 | python-pptx |
| PDF 渲染 | `render.py` | ✅ 兼容 | PowerPoint 可用时使用原生导出，否则使用 LibreOffice |
| 视频合成 | `render.py` | ✅ 兼容（需 FFmpeg） | FFmpeg 需手动或通过 Homebrew 安装 |
| PowerPoint 渲染 | `powerpoint.py` / `powerpoint_render.ps1` | ✅ Windows/macOS | Windows 使用 COM；macOS 使用 AppleScript + PyMuPDF |
| Word/Excel PDF 渲染 | `office_mac.py` / `web_gui.py` | ✅ Windows/macOS | Windows 使用 COM；macOS 使用 Office AppleScript；用于 Vision 输入 |

| 安装脚本 | `setup.ps1` / `setup.sh` | ✅ 已提供 | Windows 使用 PowerShell；macOS/Linux 使用 Bash |
| 启动脚本 | `run.ps1` / `run.sh` | ✅ 已提供 | 支持后台启动、端口检查、runtime 文件和日志 |
| 桌面 GUI | `gui.py` | ❌ Windows-only | 依赖 pywin32；Web GUI 已跨平台 |
| Web GUI 后端 | `web_gui.py` | ✅ 完全兼容 | |

## 改动清单

### 已完成

1. **新增 `setup.sh`** — macOS/Linux 安装脚本
   - 检测并安装 Python 3.10+
   - 通过 Homebrew 安装：`node`、`git`、`ffmpeg`、`libreoffice`、`poppler`
   - 创建 `.venv`，`pip install -e .`
   - 检测 Azure CLI / Pi CLI
   - 参考 `setup.ps1` 的逻辑结构

2. **新增 `run.sh`** — macOS/Linux 启动脚本
   - 端口冲突检测（用 `lsof`/`ss` 替代 PowerShell `TcpListener`）
   - 后台启动 Python 进程（`nohup` + `disown` 或 `&`）
   - 生成 `.video-work/web-gui-runtime.json`
   - 轮询等待 HTTP 端口就绪
   - 参考 `run.ps1` 的逻辑结构

3. **检查 `speech.py` 跨平台兼容性**
   - 当前文件无语法错误，已通过编译和测试检查。

### 已完成

4. **支持 macOS PowerPoint 自动化**
   - 自动检测 Microsoft PowerPoint.app
   - 通过 `osascript` 导出 PPTX/PPT PDF
   - 使用 PyMuPDF 渲染视频帧，避免 macOS PowerPoint 路径依赖 Poppler
   - PPTX Vision 输入也优先使用 PowerPoint 导出的 PDF
   - 首次运行需要在系统 Automation 权限中允许应用控制 PowerPoint

5. **更新 `README.md`**
   - 补充 macOS/Linux 安装章节
   - 说明 `VIDEO_RENDERER=auto` 在检测到 PowerPoint 时使用原生渲染
   - 列出 Homebrew 安装命令作为 FFmpeg/Poppler/LibreOffice 的备选方案

6. **更新 `pyproject.toml`**
   - `pywin32` 已按 Windows 条件安装，其他依赖保持跨平台。

### 本阶段新增 Office 生态输入支持

7. **Outlook `.eml` 邮件**
   - 资源扫描和邮件头/正文/附件名提取已支持

8. **OneNote 页面**
   - `.one` 文件纳入内容扫描
   - 使用可读字符串进行 best-effort 文本提取
   - 视觉内容建议先从 OneNote 导出 PDF；原生 OneNote UI 导出留待后续

9. **Windows Visio**
   - `.vsdx`/`.vsd` 纳入内容扫描
   - `.vsdx` 支持 XML 文本提取
   - Windows Visio COM 可导出 PDF 供 Vision 分析

10. **Pages / Numbers / Keynote**
   - macOS 检测对应应用并通过 AppleScript 导出 PDF
   - `.pages`、`.numbers`、`.key` 可进入 Vision 页面流程

### 后续可选工作

11. **`.gitlab-ci.yml` 添加 macOS Runner**
   - 在现有 CI 中增加 macOS job，验证 LibreOffice 渲染路径

12. **macOS 原生 GUI（可选）
   - 当前 Web GUI 已完全满足需求
   - 若需要原生窗口，可用 `pywebview` 或 `customtkinter` 封装 `web_gui`

## 下一阶段计划（暂不实现）

以下项目继续记录在 macOS/Linux 支持计划中，留到后续阶段：

### Office 组件扩展

1. **OneNote 原生视觉导出**
   - 评估 OneNote for Mac 的 AppleScript/UI Automation
   - 将 `.one` 页面直接导出为 PDF/图片

2. **Outlook `.msg` 和附件深度处理**
   - 评估 `.msg` 解析依赖
   - 邮件附件进入独立资源流程

3. **Visio macOS 替代方案**
   - macOS 不假设存在 Visio Desktop
   - 优先支持用户提供的 PDF/SVG/PNG

4. **Project / Access / Publisher**
   - 不直接依赖 macOS 原生应用
   - 先支持其导出的 PDF、XLSX、CSV 等通用格式
   - 只有在明确的文件样本和解析方案成熟后再增加原生格式支持

### 其它 macOS 办公套件

5. **Apple Pages / Numbers / Keynote**
   - 评估通过 macOS 自动化导出 PDF
   - 作为 Office 之外的 macOS 原生办公文件输入

### 工程化工作

6. **macOS CI Runner**：验证 PowerPoint、Word、Excel 自动化和 LibreOffice fallback
7. **macOS 原生 GUI（可选）**：用 `pywebview` 或 `customtkinter` 封装 Web GUI

## 已知限制

- macOS PowerPoint 需要通过 **系统设置 → 隐私与安全性 → 自动化** 授权运行 GUI 的应用控制 Microsoft PowerPoint
- PowerPoint for Mac 不提供 Windows COM 的 `CreateVideo` 接口；项目使用 PowerPoint PDF + PyMuPDF + FFmpeg 生成视频
- 未安装或无法自动化 PowerPoint 时，视频 fallback 仍需要 LibreOffice 和 Poppler；未安装或无法自动化 Word 时，DOCX Vision 输入需要 LibreOffice
- FFmpeg 必须安装（macOS：`brew install ffmpeg`；Debian/Ubuntu：`sudo apt-get install ffmpeg`）
- Azure Speech SDK 在 macOS 上需要 `libsoundtouch` 等系统依赖（通常通过 `brew install speech-sdk` 或 pip 自动处理）

## 参考文件

- Windows 安装脚本：`setup.ps1`
- Windows 启动脚本：`run.ps1`
- PowerPoint 渲染：`video_mcp/powerpoint.py`、`video_mcp/powerpoint_render.ps1`
- 跨平台渲染逻辑：`video_mcp/render.py`
- Bug 位置：`video_mcp/speech.py` 第 123 行附近
