# LaunchFrame — v1 第一版使用流程

本文档说明 LaunchFrame 独立项目第一版 Windows Web GUI 的可用流程，用于制作产品宣传视频。

## 当前第一版流程

```text
选择产品资源目录
  → 自动扫描资源
  → Pi 自动启动
  → Azure 登录 → Subscription 选择 → Speech Resource → Voice catalog
  → Provider 登录 → 模型选择 → 保存配置
  → 可选 Vision 分析和审批
  → LLM Draft 提示词、生成、编辑和审批
  → PPT 提示词、PPTX + PDF 生成和审核
  → Azure Speech 语音和字幕生成并自动接受
  → 多语言视频和双轨视频
  → 本地视频审核和交付，由用户自行上传
```

## 启动 Web GUI

### 首次完整安装

解压 Source ZIP 或 clone 代码仓库后，双击运行：

```text
install.bat
```

`install.bat` 是标准的一键 Windows 安装程序：会解除脚本阻止，通过 Winget 安装缺失的 Python 和 `Gyan.FFmpeg.Shared`，创建虚拟环境和桌面快捷方式，并询问是否立即启动 Web GUI。普通首次安装不需要单独执行 `setup.ps1`、`run.ps1` 或 `unblock-scripts.bat`。普通快捷方式会隐藏后台服务窗口，需要查看后台输出时使用 `debug.bat`。Web GUI 中可以在 `Progress details` 查看后端服务状态和日志，并使用红色 `Exit` 按钮退出。

## 视频渲染依赖

项目按照以下顺序查找 FFmpeg：

1. `FFMPEG_PATH`；
2. PATH 中的 `ffmpeg.exe`；
3. `<项目目录>/.tools/ffmpeg/ffmpeg.exe`；
4. `launchframe/.tools/ffmpeg/ffmpeg.exe`。

FFmpeg 不包含在代码仓库中，也不需要 Git LFS。标准的 `install.bat` 流程通过 Winget 安装 `Gyan.FFmpeg.Shared`。Winget 不可用时，可以使用手动备用脚本或设置 `FFMPEG_PATH` 指向已有安装：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\install-ffmpeg.ps1
```

备用脚本会下载公开的 FFmpeg 构建版本并校验 SHA256；标准安装流程使用 Winget。

Windows 优先使用本地 Microsoft Office：Word COM 将 DOCX 转换为 PDF，PowerPoint COM 负责 PPTX 渲染。macOS 检测到 PowerPoint 时通过 Automation 导出 PPTX PDF，再由 PyMuPDF 渲染页面。LibreOffice 作为备用方案和 macOS DOCX 转换方案。设置 `VIDEO_RENDERER=libreoffice` 可以强制使用视频/PDF 备用渲染器。

## GUI 流程

### 1. 产品资源目录

第一步选择 Product resource directory。选中的目录会立即成为本次运行的访问边界，不再需要单独设置 Workspace root。资源目录只需要包含产品文档、图片、表格、PDF/DOCX 或演示文稿，不要求存在 `video-project.json`。首次安装时，如果示例目录存在，GUI 默认选择 `examples/mock-product`。点击 `Select resource folder` 后，GUI 会自动设置访问边界、扫描资源并为该目录启动 Pi。设置保存在应用管理的 `.video-work/project-sessions/` 中，不要求修改用户资源目录。Pi 在目录选择完成后自动运行，用户不需要单独操作 Pi。

如果资源目录中存在一个或多个 PPTX，可以在 **Source PPT presentations** 中选择一个或多个文件。只选择一个时，系统会解析并复用原始 PPT，不会覆盖；选择多个时，会提取所有 PPT 的文字和备注作为 LLM 参考素材，并生成新的 `outputs/presentation.pptx`。位于 `templates/` 目录下或命名为 `*.template.pptx` 的文件会作为模板候选，单独显示在 **PPT slide template** 中。

### 2. 配置 Azure

认证成功后 GUI 会加载 Azure Subscription。顺序为：

```text
Login Azure
  → Azure Subscription
  → Discover Speech resources
  → Speech Resource
  → Load Voice catalog
```

Speech Key 通过项目内置的 `azure-mcp` 获取，只在内存中使用，不写入配置文件。

### 4. 配置语言、音色、时长和 Provider/Vision

第一语言固定为 English。第二语言从 Azure Voice catalog 中选择，默认是 `zh-CN`。

Provider 和模型控件位于同一个配置区域：

```text
Login CodeMie SSO / Logout CodeMie
Model provider：CodeMie Web / Platform 或 CodeMie CLI
CodeMie model（选择后自动应用）
Model details
Provider usage and quota
Enable Vision image analysis
Check and save configuration
```

`Model details` 会加载实时多模型列表，显示 Provider 通道、价格、输入类型、Vision/Reasoning/Tools 能力、Context Window 和最大输出，并高亮当前模型。`Refresh usage` 会加载当前 Provider 的额度和用量信息。DIAL 需要连接公司 VPN，并在 GUI 中输入有效 Token；ELITEA 需要输入有效 Token。Token 只保存在本地 Pi 进程环境中，不写入项目配置。

Pi 是后台内部服务，选择产品资源目录后自动启动。Pi 运行状态显示在产品资源区域的同行右侧，无需手动启动或停止。

选择的模型必须点击 `Check and save configuration` 后才会写入配置。只有支持图片输入的模型才显示 Vision 选项。启用 Vision 后必须人工执行 Vision 审批；`require_review` 不再作为用户可配置的绕过开关。

目标时长是可选项。留空时使用自然语音实际时长。语音生成后 GUI 会显示实际时长。如果配置的目标时长与自然语音时长相差超过 20% 或 10 秒，系统会提示增加内容，而不是把语音强行变慢。

### 5. Vision 和 Draft 审核

> 第 3 步（Azure）和第 4 步（Provider）可以按任意顺序完成，两者互相独立。

当项目存在图片、PDF 或 DOCX，选择了支持 Vision 的模型并启用 Vision 后：

```text
Analyze images
  → .video-work/vision-analysis.json
  → Approve Vision
```

Vision 结果包含 OCR、描述、关键点、Alt Text、confidence、源文件、PDF/DOCX 页码和 `suggested_slide`。Windows 下 DOCX 通过 Microsoft Word COM 转换，PDF/DOCX 页面通过 PyMuPDF 渲染后再进行 Vision 分析。LibreOffice 作为备用方案。Web GUI 会显示可编辑的 Vision 卡片。重新进行 Vision 分析会清除 Vision 以及所有下游审批。

Vision 审批后，可以先在同一区域编辑 Draft 提示词。点击 `Load saved prompt` 可恢复之前保存的提示词；修改后会启用 `Save prompt`；如果覆盖未保存修改，会使用统一风格的确认对话框。点击 `Generate LLM draft` 会立即使用当前文本，只有希望后续复用时才需要保存。

点击 `Generate LLM draft`。Pi 会调用当前选择的 Provider/model 并生成：

```text
.video-work/content-draft.json
.video-work/narration-primary.json
.video-work/narration-secondary.json
```

Draft 操作顺序：

```text
Load draft
  → 手工修改 JSON
  → Save draft
  → Approve draft
```

保存 Draft 会清除 Draft、PPT、语音、字幕和视频的旧产物；Vision、Draft 等显式审批状态也会按需重置，因为下游需要重新生成。PPT 生成后可在 GUI 中审核，GUI 开始音频阶段时自动接受；音频和字幕生成后也自动接受，不需要单独审批。

### 6. 生成和审批 PPT

Stage build and review 区域会在 `Build PPT` 上方显示独立的 PPT 提示词：

```text
Load saved prompt  |  Save PPT prompt
Build PPT
```

用户可以在这里编辑针对 PPT 生成的指导。修改后会标记为未保存；如果覆盖未保存修改，会使用统一风格的确认对话框；生成 PPT 前必须先保存。PPT 生成后同一个按钮会变成 `Regenerate PPT`。

`Build PPT` 使用已批准的 Draft 和 Vision 结果，生成：

```text
outputs/presentation.pptx
outputs/presentation.pdf
```

PPTX 下载链接和 PDF 内嵌预览显示在 PPT 行下方。用户可直接审核生成结果。GUI 开始生成音频时会自动接受已审核的 PPT；独立调用流水线时仍可以要求显式的 presentation approval。

### 7. 生成和审核音频/字幕

第二行是：

```text
Build audio + subtitles  |  Review audio/subtitles
```

音频和字幕生成后会自动视为已接受，不需要单独点击审批。音频生成后同一个按钮会变成 `Regenerate audio + subtitles`。

Azure Speech 会生成语音，并保存 word boundary 和 sentence timing：

```text
.video-work/audio-primary/
.video-work/audio-secondary/
.video-work/primary.wav
.video-work/secondary.wav
.video-work/primary-manifest.json
.video-work/secondary-manifest.json
```

网页提供：

- 可编辑的 WebVTT 字幕 cue，保存后同步更新 WebVTT 和 SRT；
- 第一语言音频播放器；
- 第二语言音频播放器；
- 可拖动进度；
- 实时同步字幕；
- SRT 和 WebVTT 审核链接。

手工字幕修改只会改变字幕文字和时间，不会改变已经生成的语音。如果要修改实际朗读内容或翻译，应从 Draft 修改、保存并审批，然后重新生成音频和字幕。只有设置了目标时长时，审核音频才会使用 FFmpeg 做时长处理。目标时长比自然语音长时使用补静音，不降低语速。目标时长留空时使用自然语音时长。

### 8. 生成和审核视频

第三行是：

```text
Build video
```

视频生成后同一个按钮会变成 `Regenerate video`，用户可以审核当前视频或重新生成。

输出：

```text
outputs/presentation-primary.mp4
outputs/presentation-secondary.mp4
outputs/presentation-dual.mp4
```

视频审核区包含三个大尺寸播放器，并提供 WebVTT 字幕。双轨播放器提供音轨选择：

```text
Embedded dual-track audio
English audio
Secondary-language audio
```

由于 Chrome、Edge 和 Firefox 对 MP4 内嵌多音轨的原生选择支持不一致，网页提供语言视频作为稳定的兼容选择。

### 9. 进度和本地交付

第 7 步为 `Progress details and local delivery`。`Refresh status` 同时读取工作流状态和实际输出文件。如果之前进程留下了过时的 `video_rendering/running`，但三个 MP4 已经存在，GUI 会自动修正为 `video_ready/completed`。

项目在视频生成完成后结束，不再需要单独的视频审批。用户下载审核后的 PPTX、PDF、音频、字幕和 MP4，再按照公司正常流程上传到目标网站发布。

如需取消正在运行的构建操作，再次点击正在闪烁的按鈕。弹出确认对话框后，点击 **Terminate** 停止当前阶段，或点击 **Continue** 继续运行。

## 故障排除

### Windows 阻止 setup.ps1 或 run.ps1

如果缺少 FFmpeg，请在项目目录运行 `tools/install-ffmpeg.ps1` 单独下载。脚本下载的是公开 FFmpeg 构建版本，并会校验 SHA256；不需要下载 Windows tools ZIP，也不会通过 Git LFS 下载。

如果已经解压，可以运行：

```text
unblock-scripts.bat
```

它可以处理常见 `RemoteSigned` 策略下 `.ps1` 和 `.bat` 文件的下载阻止。如果 PowerShell 仍然报 **“running scripts is disabled on this system”**，请使用仅对当前进程生效的绕过方式运行 setup，不要修改系统级策略：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -InstallMissing
```

可以用 `Get-ExecutionPolicy -List` 检查策略来源。如果 `MachinePolicy` 或 `UserPolicy` 被公司策略强制设置，绕过方式也可能被阻止，此时请联系 IT Security。`AllSigned`、AppLocker 或 WDAC 需要公司签名脚本或 IT 放行。

### Web GUI 端口被占用

执行：

```powershell
.\\stop.ps1
.\\run.ps1
```

如果默认端口被占用，`run.ps1` 会自动选择其他 localhost 端口。

## 生成文件

```text
.video-work/
├── content-draft.json
├── vision-analysis.json
├── narration-primary.json
├── narration-secondary.json
├── primary-manifest.json
├── secondary-manifest.json
├── primary.wav
├── secondary.wav
├── review-primary.wav
├── review-secondary.wav
└── approvals.json

outputs/
├── presentation.pptx
├── presentation.pdf
├── presentation-primary.srt
├── presentation-secondary.srt
├── presentation-bilingual.srt
├── presentation-primary.vtt
├── presentation-secondary.vtt
├── presentation-bilingual.vtt
├── presentation-primary.mp4
├── presentation-secondary.mp4
└── presentation-dual.mp4
```

大型生成媒体和运行时工具都会排除在 Git 之外。FFmpeg 不纳入代码库，用户需要在安装阶段单独下载到 Git 忽略的 `.tools/ffmpeg/` 目录。
