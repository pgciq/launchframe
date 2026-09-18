# LaunchFrame 第一版产品宣传视频制作流程

> **独立项目 v1 状态：** 当前可用的 Windows Web GUI 流程请先阅读 [docs/FIRST_RELEASE.zh-CN.md](docs/FIRST_RELEASE.zh-CN.md)。后文旧的 Release/Pages 章节属于历史架构参考，不代表当前项目功能。该流程包含后台 Pi 自动启动、Provider/模型选择、独立的 Draft/PPT 提示词编辑器（支持加载和保存）、Vision/Draft 审核、生成后的音频/字幕自动接受、FFmpeg 查找、音频和字幕本地审核，以及独立的 Build PPT、Build audio + subtitles、Build video 阶段。视频生成后本地审核，不再单独审批视频。本文保留更完整的架构和 MCP 流程参考。

本文档用于团队内部分享，说明从产品文字、图片、文档和 PPTX 素材开始，先生成 PPT，再通过 Azure Neural Voice、字幕和视频渲染生成 MP4、PDF，并由用户自行下载、审核和上传到目标网站的完整流程。

> 当前流程以 Linux-native 构建为推荐路径，Windows/PowerPoint 流程作为需要 PowerPoint 原生渲染或带音频 PPTX 时的备用路径。

## 1. 最终产物概览

每次 Presentation Release 主要生成以下交付物：

```text
English narrated MP4
Mandarin narrated MP4
Bilingual dual-track MP4
English narrated PPTX
Mandarin narrated PPTX
Presentation PDF
English subtitles: SRT + WebVTT
Chinese subtitles: SRT + WebVTT
Bilingual subtitles: SRT + WebVTT
English standalone audio: M4A
Mandarin standalone audio: M4A
```

当前页面展示方式：

- English 页面播放英文主语言旁白 MP4，默认英文字幕；
- 中文页面播放配置的第二语言旁白 MP4，默认对应语言字幕；
- 两个页面均可切换英文、中文、双语字幕或关闭字幕；
- 字幕由同源 Pages 上的 WebVTT 文件提供；
- 双语 MP4、双语字幕和 PDF 作为页面下载入口；
- HLS 不作为当前 Pages 默认播放路径。

当前示例版本：

```text
presentation-v1.3.0
```

## 可选的图片 Vision 分析

当产品目录中有图片时，可以启用 `vision_analysis`，提取图片中的可见文字、图片类型、描述、关键点、Alt Text 和建议放置页面。结果保存到：

```text
.video-work/vision-analysis.json
```

配置示例：

```json
{
  "vision_analysis": {
    "enabled": true,
    "provider": "openai-compatible",
    "model": "gpt-4.1",
    "base_url": "https://api.openai.com/v1",
    "require_review": true,
    "max_image_bytes": 5000000
  }
}
```

图片 Vision 阶段可以使用 `VIDEO_VISION_API_KEY`、`OPENAI_API_KEY` 或 `AZURE_OPENAI_API_KEY`。该阶段默认可选，并要求人工审核。审核后的 `suggested_slide` 会控制图片在生成 PPT 中的放置页面；未启用 Vision 时，图片按确定性的列表顺序放置。如果同时启用了文本 LLM，审核后的图片分析结果会参与 Presentation Outline 生成。

## 可选的大模型内容阶段

项目可以在生成 PPTX 之前可选调用大模型：

```text
产品初级素材
  → LLM 提取产品要点
  → 生成 Presentation Outline
  → 生成英文主语言内容
  → 生成可配置的第二语言内容
  → 人工审核
  → 生成 PPT
  → 生成语音和视频
```

配置示例：

```json
{
  "content_generation": {
    "enabled": true,
    "provider": "openai-compatible",
    "model": "gpt-4.1-mini",
    "base_url": "https://api.openai.com/v1",
    "require_review": true
  }
}
```

可使用以下任一 Key：

```text
VIDEO_LLM_API_KEY
OPENAI_API_KEY
AZURE_OPENAI_API_KEY
```

使用 Azure OpenAI 时，还需要：

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
```

大模型会生成结构化 Outline、英文主语言稿和第二语言稿，并保存到：

```text
.video-work/content-draft.json
```

如果 `require_review=true`，必须人工审核后设置：

```text
VIDEO_MCP_APPROVE_DRAFT=true
```

否则流程不会继续生成 PPT 和视频。

## 2. 目录结构

相关源文件位于主仓库：

```text
presentations/
├── create_internal_share_ppt.py
├── narration.json
├── narration_zh.json
├── subtitles.json
├── speech_synthesis_helpers.py
├── generate_azure_narration.py
├── generate_azure_chinese_narration.py
├── generate_dual_track_subtitles.py
├── convert_srt_to_vtt.py
├── build_dual_track_audio.py
├── build_linux_video.py
├── export_dual_track_audio.py
├── export_language_videos.py
├── export_presentation_pdf.ps1
├── build_dual_track.ps1
├── publish_presentation.ps1
└── ...

scripts/
├── publish_presentation_release.py
├── publish_source_release.py
├── render_latest_presentation_links.py
└── sync_presentation_subtitles.py

tools/
├── ffmpeg-config.json
└── install-ffmpeg.ps1
```

生成的 PPTX、MP4、WAV、M4A 和大型中间文件均被 `.gitignore` 忽略，不进入 Git 历史。

## 3. 内容准备

### 3.1 产品初级素材

项目默认使用英文作为第一语言。第二语言可以配置为 Azure Speech 支持的任意语言；未指定时默认为中文 `zh-CN`。示例包括 `ja-JP`、`ko-KR`、`de-DE`、`fr-FR` 和 `es-ES`，实际可用性取决于 Azure Speech Voice。视频时长也可以通过 `output.target_duration_seconds` 配置。

视频制作的第一步不是直接生成语音，而是先选择产品资源目录。Web GUI 会将选中的目录立即作为本次运行的访问边界、`VIDEO_PROJECT_ROOT` 和 Pi 工作目录，然后自动扫描并按文件扩展名和文件名归类。`video-project.json` 在 Web GUI 中是可选的；CLI 或可复用示例项目仍可以提供它。MCP 工具 `scan_product_resources` 可以在构建前查看分类结果。项目可以读取：

- 产品简介和 Markdown/TXT/RST 文本；
- 产品截图、架构图和其他图片；
- PDF、DOCX、JSON、YAML、XML 文档；
- CSV/XLSX 表格；
- MP4、MOV、WebM 视频和 MP3、WAV、M4A 音频资源；
- 已存在的产品 PPTX。

素材应放在用户选择的产品资源目录下。目录选择完成后会自动扫描资源并启动 Pi，不需要用户创建 `video-project.json`。项目会优先根据文本、图片和文档内容生成或完善 PPTX；如果已经提供 PPTX，则先验证并使用现有 PPTX。

完整资源布局见：

```text
docs/RESOURCE_LAYOUT.md
```

### 3.2 英文演讲稿

文件：

```text
presentations/narration.json
```

每个页面包含：

- `slide`：页面编号；
- `title`：页面标题；
- `text`：完整英文讲稿。

当前演示文稿共 21 页，主体讲解约 30 分钟语音，现场分享可通过 Demo、补充说明和 Q&A 扩展到一小时。

### 3.3 中文讲稿

文件：

```text
presentations/narration_zh.json
```

中文稿不是简单的机器直译，而是经过人工技术术语校对的普通话讲稿。它与英文稿按页面和句子顺序对应，用于：

- Azure 普通话语音生成；
- 中文字幕生成；
- 中英双语字幕生成。

修改任一讲稿后，需要重新生成对应语音、Manifest 和字幕，不能只替换字幕文件。

### 3.4 页面级字幕

文件：

```text
presentations/subtitles.json
```

这些内容会渲染到 PPT 页面底部，属于“画面内嵌的简短摘要字幕”。它们与逐句 WebVTT/SRT 字幕不同：

- 页面级字幕会随页面一起进入 PDF/视频画面；
- 逐句字幕通过 WebVTT/SRT 文件随播放时间变化；
- 页面级字幕适合演示画面；
- 逐句字幕适合无障碍和精确跟读。

## 4. 环境与凭据

### 4.1 Azure 登录与 Speech 资源发现

视频项目现在优先通过 Azure CLI 登录来发现 Speech 资源、获取临时 Key，并读取 TTS Voice 列表。Windows PowerShell：

```powershell
az login
az account set --subscription "<subscription-id>"
```

Linux/macOS：

```bash
az login
az account set --subscription "<subscription-id>"
```

GUI 或 MCP 客户端应先调用：

```text
azure_login_status
discover_speech_resources
list_tts_voices
```

然后让用户选择 Speech Resource、第一语言 Voice 和第二语言 Voice。Speech Key 只在内存中使用，不写入资源目录、应用会话配置、日志或 Git。

也可以使用 Service Principal 或 Managed Identity 替代 Azure CLI。

使用的默认语音：

```text
English:  en-US-JennyNeural
Chinese:  zh-CN-YunyangNeural
Rate:     0%
```

### 4.2 GitHub Token

Release 上传和 Pages 资源同步需要：

```text
GITHUB_TOKEN
```

建议在 GitHub CI/CD Variables 中配置为：

- Masked；
- Protected；
- 仅授予所需的 API / Package Registry 权限。

## 5. 生成 PPT

安装 Python 依赖：

```bash
python -m pip install python-pptx
```

生成基础 PPT：

```bash
python presentations/create_internal_share_ppt.py
```

输出：

```text
presentations/dolphins_mcp_toolkit_internal_share.pptx
```

这个 PPT 是英文内容，包含页面级中英双语字幕，但不包含语音。

## 6. 生成 Azure 语音

### 6.1 英文语音

```bash
python -m pip install azure-cognitiveservices-speech
python presentations/generate_azure_narration.py
```

### 6.2 中文语音

```bash
python presentations/generate_azure_chinese_narration.py
```

输出目录：

```text
presentations/azure_narration_audio/
presentations/azure_zh_narration_audio/
```

每页对应一个 WAV 文件：

```text
slide-01.wav
slide-02.wav
...
slide-21.wav
```

### 6.3 Azure Speech 限流与重试

Speech F0 有实时交易频率限制。当前辅助模块默认配置：

```text
AZURE_SPEECH_MIN_REQUEST_INTERVAL_SECONDS=3.2
AZURE_SPEECH_MAX_RETRIES=5
AZURE_SPEECH_RETRY_BASE_SECONDS=4
```

语音脚本会：

1. 在请求之间等待；
2. 记录临时失败；
3. 对 429、超时、暂时不可用和连接失败使用指数退避；
4. 最终失败时抛出明确错误。

不要为了加快构建而取消限流，否则可能触发 Speech 服务的 429。

### 6.4 Word-boundary 记录

每次 Azure Speech 合成都会连接：

```python
synthesizer.synthesis_word_boundary.connect(on_boundary)
```

记录的信息包括：

```text
audio_offset
duration
text_offset
word_length
text
```

`audio_offset` 的单位是 100 纳秒 Tick，生成字幕时需要除以 `10_000_000` 转为秒。

Speech 句末标点边界用于确定每个句子的结束时间。这样字幕时间不再依赖简单的句子长度比例估算，可以跟随实际语速和停顿。

Manifest 中会保存每个页面的：

```json
{
  "duration_seconds": 80.123,
  "sentence_timings": [
    {
      "start_seconds": 0.05,
      "end_seconds": 3.42
    }
  ]
}
```

## 7. 生成字幕

### 7.1 双轨统一时间轴

运行：

```bash
python presentations/generate_dual_track_subtitles.py
```

脚本会：

1. 读取英文和中文讲稿；
2. 读取两种语言的 word-boundary Manifest；
3. 按页面合并两种语言的时间区间；
4. 避免双语字幕条目重叠；
5. 生成英文、中文和中英双语三组字幕。

输出：

```text
presentations/dolphins_mcp_toolkit_dual_track_en.srt
presentations/dolphins_mcp_toolkit_dual_track_bilingual.srt
presentations/dolphins_mcp_toolkit_dual_track_zh.srt
```

### 7.2 SRT 转 WebVTT

浏览器通常使用 WebVTT：

```bash
python presentations/convert_srt_to_vtt.py \
  presentations/dolphins_mcp_toolkit_dual_track_en.srt \
  presentations/dolphins_mcp_toolkit_dual_track_en.vtt

python presentations/convert_srt_to_vtt.py \
  presentations/dolphins_mcp_toolkit_dual_track_bilingual.srt \
  presentations/dolphins_mcp_toolkit_dual_track_bilingual.vtt

python presentations/convert_srt_to_vtt.py \
  presentations/dolphins_mcp_toolkit_dual_track_zh.srt \
  presentations/dolphins_mcp_toolkit_dual_track_zh.vtt
```

WebVTT cue 位置使用接近底部的配置：

```text
line:96% position:50% size:60% align:center
```

线上 Pages 不依赖浏览器原生 `<track>` 显示字幕，而是：

1. JavaScript 从同源 Pages 加载 WebVTT；
2. 解析 cue 起止时间；
3. 根据 `video.currentTime` 查找当前字幕；
4. 写入自定义 `<div>`；
5. 使用 CSS 控制字号、位置、背景和宽度。

当前线上默认字幕：

```text
English page: English narration + English subtitles
Chinese page: Mandarin narration + Chinese subtitles
```

两个页面都支持：

```text
English
中文
English + Chinese
Subtitles off
Fullscreen
```

## 8. Linux-native 视频构建

Linux 构建不依赖 PowerPoint COM。Windows 环境下，`VIDEO_RENDERER=auto`（默认）会优先检测本地 PowerPoint Desktop；如果存在则使用 PowerPoint COM，否则回退到 LibreOffice。设置 `VIDEO_RENDERER=libreoffice` 可以强制使用跨平台渲染器。Linux 路径使用：

```text
LibreOffice → PDF
Poppler → PNG slides
FFmpeg → visual video + audio mux
```

Ubuntu 依赖：

```bash
sudo apt-get install \
  ffmpeg \
  libreoffice-impress \
  poppler-utils \
  fonts-noto-cjk \
  python3 \
  python3-venv
```

执行：

```bash
python presentations/create_internal_share_ppt.py
python presentations/generate_azure_narration.py
python presentations/generate_azure_chinese_narration.py
python presentations/build_linux_video.py
```

`build_linux_video.py` 的主要步骤：

1. 生成或读取基础 PPTX；
2. 使用 `build_dual_track_audio.py` 对齐两种语言；
3. 使用 LibreOffice 将 PPTX 转成 PDF；
4. 保留 PDF 作为交付物；
5. 使用 `pdftoppm` 将 PDF 转成逐页 PNG；
6. 根据页面目标时长创建 FFmpeg concat 清单；
7. 生成带页面视觉内容的视频；
8. 合并英文和普通话两个音轨；
9. 导出独立英文/普通话视频；
10. 导出 M4A 音轨；
11. 生成并转换 SRT/WebVTT。

视频结果：

```text
English MP4
Mandarin MP4
Bilingual dual-track MP4
```

## 9. Windows/PowerPoint 渲染器

如果需要 PowerPoint 原生渲染，或需要带嵌入音频的 PPTX，可以设置：

```powershell
$env:VIDEO_RENDERER = "powerpoint"
```

如果希望 Windows 也完全绕过 Office，可以设置：

```powershell
$env:VIDEO_RENDERER = "libreoffice"
```

如果保持默认的 `auto`，项目会优先使用检测到的本地 PowerPoint，否则使用 LibreOffice。

```powershell
$env:AZURE_SPEECH_KEY = "<speech-key>"
$env:AZURE_SPEECH_REGION = "eastus2"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File presentations/publish_presentation.ps1 `
  -Version "1.4.0" `
  -FfmpegPath "D:\path\to\ffmpeg.exe"
```

该路径依赖：

- Windows；
- PowerPoint Desktop；
- Office 授权；
- PowerShell；
- FFmpeg。

Linux-native 路径是 CI 推荐路径。Windows 路径适合作为本地高保真备用方案。

## 10. GitHub Release 发布

当前有三个 deploy 职责：

```text
deploy-pages
release-source
release-presentation
```

### 10.1 源码 Release

手工触发：

```text
release-source
```

输入：

```text
RELEASE_VERSION=0.2.0
```

输出：

```text
v0.2.0
```

内容是只包含 Git 已跟踪文件的源码归档，不包含生成媒体。

### 10.2 Presentation Release

手工触发：

```text
release-presentation
```

输入：

```text
PRESENTATION_VERSION=1.4.0
```

自动执行：

1. 生成 PPTX；
2. 生成英文/普通话语音；
3. 记录 word-boundary；
4. 生成字幕；
5. 生成 PDF；
6. 生成英文、中文和双轨 MP4；
7. 上传媒体、字幕和 PDF；
8. 创建 `presentation-v1.4.0` Release；
9. 触发 Pages Pipeline。

### 10.3 Pages 更新

Presentation Release 成功后触发 Pages Pipeline，并传入：

```text
SYNC_PRESENTATION=true
PRESENTATION_VERSION=1.4.0
```

Pages Pipeline：

1. 将页面中的版本占位符替换为 `1.4.0`；
2. 从 Package Registry 下载三个小型 WebVTT 文件；
3. 将字幕保存到 `public/assets/presentation/`；
4. 构建 MkDocs；
5. 发布 Pages。

大视频仍通过 Package Registry 直接引用，不复制到 Pages Artifact。

## 11. 发布前验证

代码和脚本：

```bash
python -m ruff check presentations/*.py scripts/*.py
python -m pytest -q tests/
git diff --check
git status --short
```

媒体检查：

```bash
ffprobe dolphins_mcp_toolkit_dual_track.mp4
ffprobe dolphins_mcp_toolkit_english.mp4
ffprobe dolphins_mcp_toolkit_mandarin.mp4
```

确认：

- 视频编码为 H.264；
- 英文视频包含英文音轨；
- 中文视频包含普通话音轨；
- 双轨视频包含两个音轨；
- 字幕条目数量与讲稿句子数量一致；
- 字幕最后结束时间不超过视频或音频总时长；
- WebVTT 时间格式使用点号毫秒：`00:00:01.438`；
- Pages 页面中的英文和中文视频使用不同的源文件；
- English 页面默认英文字幕；
- 中文页面默认中文字幕；
- 字幕关闭和全屏控制可用。

## 12. 常见问题

### 视频可播放但字幕不显示

优先检查：

1. WebVTT 是否在 Pages 同源路径；
2. 浏览器 DevTools Network 中是否返回 200；
3. 是否还有旧页面缓存；
4. WebVTT 是否包含 `WEBVTT` 头；
5. cue 时间是否使用 `.` 而不是 `,`；
6. 页面是否加载了正确的 VTT 文件。

当前 Pages 使用自定义字幕层，不依赖浏览器原生 `<track>` 渲染。

### 中文页面播放英文语音

检查页面源文件是否使用：

```text
zho → dolphins_mcp_toolkit_mandarin.mp4
```

英文页面应使用：

```text
eng → dolphins_mcp_toolkit_english.mp4
```

### Pages 部署失败

优先检查 Pages Artifact 大小。不要将大型视频和所有 HLS 分片复制到 Pages。当前推荐：

- 大视频：Package Registry 直接引用；
- 小字幕：CI 下载到同源 Pages；
- PDF/MP4/PPT：通过 Release 下载链接提供。
