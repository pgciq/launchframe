# 常见问题解答

## 1. 适用场景

### LaunchFrame 最适合制作哪类视频？

LaunchFrame 专为**从现有产品文档生成结构化推广与讲解视频**而设计。以下场景最为适合：

- 主题是软件产品、平台、服务或技术项目。
- 素材已经存在：Markdown 文件、PDF、Word 文档、PPTX 演示文稿、电子表格、产品截图或架构图。
- 视频形式是旁白幻灯片演示 —— 标题页、核心功能、技术架构、路线图、行动号召。
- 受众是内部（团队演示、管理层评审、新员工培训）或外部（产品落地页、会议录播、发版公告）。
- 需要双语交付：主语言英语轨道 + 一种可配置的副语言轨道。
- 团队需要可重复、可审计的流程：每个阶段都生成可审阅的产物，通过后才进入下一阶段。

典型时长：**3 到 20 分钟**。短于 3 分钟的视频也可生成，但每张幻灯片的旁白内容会很有限。超过 20 分钟的视频在技术上可行，但消耗更多 LLM token 和 Azure Speech 额度，审阅周期也会更长。

---

### 哪些场景不适合使用？

| 不适合的场景 | 原因 |
|---|---|
| 真人出镜 / 主播讲解视频 | 无摄像头采集，无视频剪辑功能 |
| 屏幕录制与操作演示 | 无屏幕录制；参考视频可作为素材但不会被嵌入 |
| 营销创意 / 品牌广告 | LLM 输出内容基于事实，不是广告文案 |
| 叙事 / 故事 / 娱乐类视频 | 不支持非演示文稿格式的脚本 |
| 背景音乐或音效 | 音频流程仅支持旁白，无配乐功能 |
| 实时直播推流 | 输出为本地文件，发布完全手动 |
| 自动发布到任何平台 | 出于设计原则不在范围内，用户手动上传 |
| 单个视频超过两种语言 | 每次运行仅支持一种主语言（英语）+ 一种副语言 |
| 完全无人值守的自动生成 | 每次运行至少需要人工审批 Draft 后才能生成视频 |

---

### 需要准备多少素材？

启动构建至少需要**一个受支持的内容文件**（文档、图片、表格、PDF/DOCX 或 PPTX）。素材越丰富，LLM 生成的大纲就越详细。

实践建议：

- **素材较少**（只有一个简短的 Markdown 文件）：LLM 会生成简短而笼统的草稿。建议补充要点列表、截图或简单的 PPTX。
- **素材丰富**（多个文档、图片、PPTX、带字幕的参考视频）：LLM 能生成与现有内容对齐的详细结构化草稿。
- **素材过多**：LLM 的上下文窗口有限。若所有内容文件的纯文本总量超过约 50–100 KB，建议将项目拆分为多个聚焦的小视频，或删减相关性较低的文档。

---

## 2. 依赖与限制

### 需要哪些外部服务？

| 服务 | 用于 | 说明 |
|---|---|---|
| **Azure AI Speech** | 音频合成、字幕、视频 | 必须。没有 Speech 资源 = 无音频、无字幕、无视频。PPT 和 PDF 审阅仍可使用。 |
| **LLM Provider**（CodeMie / DIAL / ELITEA）| 草稿生成、Vision 分析 | 生成草稿必须。Vision 可选。 |
| **Pi** | Web GUI 中的 LLM 与 Vision 调度 | 加载目录时自动启动。直接使用 CLI 时不需要。 |

LaunchFrame 不负责创建上述任何服务。Azure Speech 资源必须由具有权限的 Azure 管理员提前创建。

---

### Vision 分析是必须的吗？

不是。Vision 是**可选功能**。禁用或跳过时：

- 图片文件仍会被扫描，其文件名会被包含在 LLM 提示词中。
- PPTX 幻灯片文字和视频字幕仍会被提取并发送给 LLM。
- 草稿及所有下游阶段正常进行。

当产品图片、架构图或幻灯片截图包含文字无法描述的视觉信息时，建议启用 Vision。

---

### 需要安装哪些本地软件？

| 软件 | 是否必须 | 用途 |
|---|---|---|
| **FFmpeg** | 必须 | 音频归一化、atempo 拉伸、视频渲染 |
| **Pi** | 必须（Web GUI）| LLM 与 Vision 调度 |
| **Python 3.10+** | 必须 | 运行环境 |
| **Microsoft PowerPoint Desktop** | 推荐（Windows；macOS 支持自动化）| PPTX→PDF 渲染；`VIDEO_RENDERER=auto` 检测到时自动使用 |
| **Microsoft Word / Excel for Mac** | 可选 | DOCX/XLSX→PDF 渲染，用于 Vision 页面 |
| **LibreOffice** | 回退方案 | Office 转 PDF 时原生 Office 不可用的备用方案 |
| **Poppler（`pdftoppm`）** | 回退方案 | 使用 LibreOffice 渲染时的 PDF→PNG 帧提取；macOS PowerPoint 路径使用 PyMuPDF |
| **Azure CLI（`az`）** | 推荐 | 通过 `az login` 使用 `DefaultAzureCredential`；其他凭据来源也支持 |

FFmpeg 不包含在代码仓库中，也不需要 Git LFS。`setup.ps1 -InstallMissing` 会通过 Winget 安装 `Gyan.FFmpeg.Shared`。Winget 不可用时，可以使用手动备用脚本或设置 `FFMPEG_PATH` 指向已有安装。LibreOffice 和 Poppler 为可选安装；如需要但未安装，GUI 会报告缺失。

---

### Windows 下推荐如何安装和卸载？

发布 ZIP 解压后，双击 `install.bat`。它会解除本地脚本阻止、使用进程级 PowerShell 绕过运行 setup、创建或更新桌面快捷方式，并询问是否立即启动 GUI。普通快捷方式会隐藏后台服务，需要查看输出时使用 `debug.bat`。如需卸载本地应用，使用 `uninstall.bat`；它会保留产品素材和共享软件。只有明确输入 `DELETE` 后才会删除整个安装目录。

**主语言固定为英语**（`en-US` 或 `en-GB`），由验证逻辑强制执行：

```python
if config.primary_language.lower() not in {"en", "en-us", "en-gb"}:
    errors.append("primary_language must be English")
```

**副语言**可配置为 Azure Speech 支持的任意 Neural 语音 locale，例如 `zh-CN`、`ja-JP`、`ko-KR`、`de-DE`、`fr-FR`、`es-ES`。每次运行**只支持一种副语言**。

如需生成第三种语言的视频，更改 `secondary_language` 配置后重新运行流程。

---

### 可以在 Linux 或 macOS 上运行吗？

CLI 及大部分流程在 Linux 和 macOS 上可以运行，但存在以下限制：

| 功能 | Linux / macOS |
|---|---|
| CLI（`ai-video scan/inspect/build`）| ✅ 完全支持 |
| Web GUI | ✅ 支持 |
| PowerPoint 渲染 | ✅ Windows COM 或 macOS PowerPoint 自动化；LibreOffice 作为回退 |
| DOCX/PPTX/XLSX Vision 渲染（Word/PowerPoint/Excel）| ✅ macOS 优先使用已安装的 Office；LibreOffice 作为备用方案 |
| Windows"选择文件夹"对话框 | ❌ 不可用；需手动输入路径 |
| `setup.ps1` / `run.ps1` | ❌ PowerShell 脚本；需使用等效的 Shell 命令 |

在 Linux/macOS 上设置 `VIDEO_RENDERER=libreoffice` 可强制使用 LibreOffice + Poppler。macOS 的 `auto` 模式会在检测到 PowerPoint 且获得 Automation 权限时使用 PowerPoint。

---

### 生成过程中需要联网吗？

| 阶段 | 是否需要联网 |
|---|---|
| 资源扫描、配置加载 | 否 |
| Vision 分析 | 是 — 调用 LLM Vision API |
| 草稿生成 | 是 — 调用 LLM API |
| PPT 构建、PDF 渲染 | 否 |
| 音频合成 | 是 — 调用 Azure Speech TTS API |
| 字幕生成 | 否 |
| 视频渲染 | 否 |
| 发布 | 从不 — 仅手动上传 |

使用 DIAL 时还需要连接**公司 VPN** 才能访问 API。

---

## 3. 时长控制

### 如何控制视频时长？

在 Web GUI 的配置面板中设置目标时长，或在 `video-project.json` 中填写：

```json
{
  "output": {
    "target_duration_seconds": 300
  }
}
```

最小允许值为 **30 秒**。留空则使用旁白的自然时长。

生成草稿时，LLM 会收到如下指令：

> *"目标时长为 300 秒。请按自然语速规划足够的旁白内容以接近该时长，不要人为放慢语速。"*

音频合成完成后，流程会检查实际旁白时长与目标的偏差是否在 20%（或 10 秒，取较大值）以内。偏差在范围内时，FFmpeg `atempo` 会精确拉伸至目标时长；超出容忍范围时，系统不会阻断构建，因为用户在批准草稿时已被告知预估时长并选择了继续。

---

### 预估时长低于目标怎么办？

这是在草稿阶段（音频生成前）根据文字量粗略估算的提示，不是阻断条件。点击**Approve draft**时会弹出确认对话框告知估算值，用户确认后才继续构建。

| 原因 | 解决方法 |
|---|---|
| 旁白文字量不足 | 编辑草稿，为每张幻灯片增加更多内容；或增加幻灯片数量 |
| 旁白文字量过多 | 编辑草稿，缩短每张幻灯片的旁白；或调大目标时长 |
| 目标时长对内容来说设置过短 | 增大 `target_duration_seconds`，或在大纲中减少幻灯片 |

估算偏差仅供参考，不影响构建流程。若估算偏差过大，可在批准前修改草稿并重新生成。

---

### 多少文字能生成多长的音频？

以 Azure Neural TTS 自然语速为参考：

| 语言 | 语速 | 5 分钟视频所需文字量 |
|---|---|---|
| 英语（`en-US`）| 约 150 词/分钟 | 约 750 词 |
| 普通话（`zh-CN`）| 约 250 字/分钟 | 约 1250 字 |
| 日语（`ja-JP`）| 约 400 字/分钟 | 约 2000 字 |
| 德语（`de-DE`）| 约 130 词/分钟 | 约 650 词 |

以上为近似值，实际时长取决于所选语音和 SSML 语速设置。

---

### `gap_seconds` 有什么作用？

`gap_seconds`（默认 `0.5` 秒）是组装双轨 WAV 时每张幻灯片旁白之间插入的静音间隔。10 张幻灯片的视频，默认会额外增加 5 秒时长。调大该值可让观众在幻灯片切换时有更多喘息时间：

```json
{ "output": { "gap_seconds": 1.0 } }
```

有效范围：`0` 到 `10` 秒。

---

## 4. 内容质量

### 可以自定义 Draft 和 PPT 提示词吗？

可以。Draft 区域提供独立的 **Customize the draft prompt** 编辑框，并有 **Load saved prompt** 和 **Save prompt**。点击生成 Draft 时会立即使用当前提示词，即使还没有保存。修改提示词后界面会标记为已修改；如果在有未保存修改时加载已保存版本，会显示统一风格的确认对话框。

Stage build and review 区域的 **Customize the PPT generation prompt** 位于 **Build PPT** 上方，提供独立的加载和保存按钮。PPT 提示词修改后，生成 PPT 前必须先保存。两个提示词分别保存在项目设置的 `draft_instructions` 和 `presentation_instructions` 字段中。

### LLM 生成的草稿质量不好，如何改善？

草稿质量与输入素材的丰富程度直接相关。按影响大小排序：

1. **增加结构化文本**：有清晰标题和要点列表的 Markdown 文件对 LLM 的指导效果最好；PDF 和 DOCX 文档也会被提取。
2. **提供现有 PPTX**：幻灯片的标题、正文和备注会被提取并作为首要输入送入 LLM —— 这是改善旁白对齐程度最有效的手段。
3. **为参考视频添加配套字幕**：演示视频 `.mp4` 旁边若有同名 `.srt` 或 `.vtt` 文件，转录文字会被包含在 LLM 提示词中。
4. **启用 Vision**：图片分析结果作为补充信息送入 LLM，对图表密集型产品尤为有用。
5. **直接编辑草稿**：审批前草稿可以自由编辑。在审批前调整大纲、改写旁白段落、增删幻灯片。

---

### Vision 分析结果不准确或前后不一致，怎么处理？

- **审批前手动修改**：Vision 审阅面板允许在审批前修改 `vision-analysis.json` 中的任何字段。直接修正描述、`suggested_slide` 分配和 `key_points`。
- **禁用 Vision**：如果图片内容已经在文本中有完整描述，Vision 价值不大，其错误还可能误导 LLM。取消勾选"启用 Vision 图像分析"并保存配置。
- **更换模型**：更强的 Vision 模型（如 `gpt-4.1` 优于 `gpt-4o-mini`）对复杂架构图通常有更好的识别效果。在配置中更换模型后重新分析。
- **减少图像噪声**：含有大量 UI 界面元素或代码文字的截图容易干扰 Vision。在加入资源目录前对图片进行裁剪或标注。

---

### 旁白与幻灯片内容对不上怎么办？

这通常发生在 LLM 只能看到文本文档而无法看到幻灯片实际内容时。

解决方法：
- 将源 PPTX 放入资源目录。其幻灯片文字和备注会被提取并加入 LLM 提示词。
- 草稿生成后审阅大纲 —— `outline` 中每个 `slide` 编号必须与 PPTX 中对应的幻灯片匹配。在审批前编辑 `primary_narration` 和 `secondary_narration` 条目，使其与实际幻灯片内容对齐。

---

### 多个 PPTX 文件如何区分？

GUI 会区分源 PPT 和幻灯片模板。用户可以在 **Source PPT presentations** 中选择一个或多个 PPTX：只选择一个时直接复用源 PPT，选择多个时合并提取文字和备注作为 LLM 参考素材，并生成新的 `outputs/presentation.pptx`。位于 `templates/` 目录下或命名为 `*.template.pptx` 的文件会被识别为模板候选。存在多个源 PPT 时，系统不会静默选择第一个文件。

---

### 视频会有多少张幻灯片？

幻灯片数量由 LLM 根据素材内容和目标时长决定，没有硬性上限。实践建议：

- 以自然语速（每张幻灯片约 1–2 分钟）估算，5 分钟的视频通常有 4–8 张幻灯片。
- 大纲审批前可以自由编辑，可在草稿中增加、删除或调整幻灯片顺序。
- 如果使用了现有 PPTX，幻灯片数量由该 PPTX 决定，LLM 会为每张已有幻灯片生成旁白。

---

## 5. 安全与凭据

### Azure Speech 密钥存在哪里？

Speech 密钥在运行时通过 `DefaultAzureCredential` 从 Azure ARM API 获取，**仅保存在内存中**。它不会被写入任何文件，不会被记录到日志，也不会被提交到 Git。订阅 ID 在 Web GUI 中会被脱敏显示。

---

### DIAL 和 ELITEA 的 Token 存在哪里？

Token 通过 `keyring` 存储在 **Windows 凭据管理器**中，不会写入：

- `video-project.json` 或任何项目文件
- 浏览器 `localStorage`
- Git 历史记录
- 应用日志

如果 `keyring` 不可用，每次会话都需要重新输入 Token。

---

### 生成视频时，产品内容会被发送到外部服务吗？

是的，在以下两个阶段会发送：

| 阶段 | 发送的数据 | 目标服务 |
|---|---|---|
| Vision 分析 | 图片字节（base64 编码）| LLM Vision API（CodeMie / DIAL / ELITEA）|
| 草稿生成 | 从所有内容文件、PPTX、字幕文件和 Vision 结果中提取的文本 | LLM API（CodeMie / DIAL / ELITEA）|
| 音频合成 | 旁白文本（SSML 格式）| Azure Speech TTS API |

视频渲染、字幕生成及所有审阅阶段**完全在本地执行**，不进行任何外部 API 调用。

在将本工具用于保密产品材料之前，请确认所选 LLM Provider 和 Azure Speech 区域符合贵组织的数据合规要求。

---

### 产品资源目录中不应该放什么？

- API 密钥、密码或 Token
- 个人隐私数据（PII）
- 机密文件或具有法律特权的文件

访问边界机制可防止路径穿越到所选目录之外，但 LLM 会读取并处理它在目录中找到的每一个受支持文件。

---

## 6. 流程与审批

### 有哪些阶段可以跳过？

| 阶段 | 可跳过？ | 方式 |
|---|---|---|
| Vision 分析 | ✅ 可以 | 取消勾选"启用 Vision 图像分析"并保存配置 |
| 草稿审批 | ❌ 不可以 | PPT 构建前必须审批；CI 流程可用 `VIDEO_MCP_APPROVE_DRAFT=1` 绕过 |
| PPT / PDF 审核 | ✅ GUI 审核后继续 | GUI 开始生成音频时会自动接受已审核的 PPT；独立流水线调用仍可要求审批，或使用 `VIDEO_MCP_APPROVE_PRESENTATION=1` |
| 音频生成 | ✅ 自动接受 | 生成后可直接本地审核，不设审批门控 |
| 字幕生成 | ✅ 自动接受 | 生成后可直接本地审核，不设审批门控 |
| 视频审阅 | ✅ 可以 | 无审批门控，审阅为非正式流程 |

`VIDEO_MCP_APPROVE_*` 环境变量仅供 CI 自动化流程使用，不建议在正式生产运行中用于绕过人工审阅。

---

### 可以只生成 PPT 而不生成视频吗？

可以。必要时先编辑并保存 PPT 提示词，然后点击 **Build PPT** 并停止。PPTX 和 PDF 会写入项目工作区/输出目录供审核。点击 **Build audio + subtitles** 之前不会生成音频、字幕和视频；GUI 在开始音频阶段时会自动接受已审核的 PPT。

通过 CLI：
```powershell
ai-video build D:\projects\my-product  # 完整运行
```
CLI 始终运行到完成；部分停止需要在 API 直接调用时使用 `stop_after` 参数。

---

### 审批了某个阶段后还能重新生成吗？

可以。在 Web GUI 中点击已完成阶段的 **Regenerate** 链接。这会清除该阶段的输出文件及所有下游显式审批记录，之后可以从该阶段重新构建。音频和字幕重新生成后会自动接受。

可单独重新生成的阶段：草稿、PPT、音频+字幕、视频。

---

### 切换资源目录后，之前的审批记录还保留吗？

不保留。切换目录会**重置前一个目录的所有运行状态**：正在运行的构建被取消，Pi 被停止，所有显式审批记录和输出文件引用从界面中清除。审批文件（`.video-work/approvals.json`）仍保存在旧目录的磁盘上，切换回该目录时会自动恢复。

Azure 认证状态和 Provider Token 在目录切换时保留。

---

### 可以对同一个目录多次运行流程吗？

可以。流程会将现有文件作为缓存使用：

- 若 `content-draft.json` 已存在且已审批，跳过草稿生成。
- 若 PPTX 已存在且已审批，跳过 PPT 生成；GUI 会在开始音频前显示当前 PPT/PDF 供审核。
- 若音频文件已存在，跳过语音合成。

如需强制重新生成，在 Web GUI 中点击相应阶段的 **Regenerate**，或手动删除 `.video-work/` 中的对应文件。

---

## 7. 输出格式

### 输出文件在哪里？

```text
<资源目录>/
├── .video-work/                     中间文件与审批记录
│   ├── vision-pages/                渲染的 PNG 帧（PDF 页面、PPTX 幻灯片、视频关键帧）
│   ├── vision-analysis.json
│   ├── content-draft.json
│   ├── narration-primary.json
│   ├── narration-secondary.json
│   ├── audio-primary/slide-*.wav
│   ├── audio-secondary/slide-*.wav
│   ├── primary.wav
│   ├── secondary.wav
│   ├── review-primary.wav
│   ├── review-secondary.wav
│   └── approvals.json
└── outputs/
    ├── presentation.pptx
    ├── presentation.pdf
    ├── presentation-primary.srt
    ├── presentation-primary.vtt
    ├── presentation-secondary.srt
    ├── presentation-secondary.vtt
    ├── presentation-bilingual.srt
    ├── presentation-bilingual.vtt
    ├── presentation-primary.mp4
    ├── presentation-secondary.mp4
    └── presentation-dual.mp4
```

---

### 可以自定义 PPTX 模板或幻灯片样式吗？

当前版本不直接支持。生成的 PPTX 使用内置的深蓝色主题（标题页 + 带要点和可选图片的内容页）。

使用自定义样式的方法：

1. 用你的模板创建一个 PPTX，确保幻灯片数量与内容对应。
2. 将其放入资源目录作为源文件。
3. 流程会直接使用该 PPTX 生成音频、字幕和视频，跳过 PPT 生成阶段。

更丰富的模板支持和品牌定制功能计划在后续版本中提供。

---

### 会生成哪些字幕格式？

三条轨道，每条提供两种格式：

| 文件 | 内容 |
|---|---|
| `presentation-primary.srt/.vtt` | 仅主语言（英语）|
| `presentation-secondary.srt/.vtt` | 仅副语言 |
| `presentation-bilingual.srt/.vtt` | 双语交替排列 |

字幕由 Azure Speech 词边界事件生成，时间轴与审阅音频同步（若设置了目标时长，则在 atempo 归一化后对齐）。

---

### 视频使用什么编码格式？

FFmpeg 默认设置：**MP4 容器**，**H.264 视频**（`libx264`），**AAC 音频**。三个输出视频分别为：

| 文件 | 音频轨道 |
|---|---|
| `presentation-primary.mp4` | 仅主语言旁白 |
| `presentation-secondary.mp4` | 仅副语言旁白 |
| `presentation-dual.mp4` | 双语交替（每张幻灯片：英语旁白 + 静音填充，然后中文旁白 + 静音填充）|

分辨率由 PPTX 幻灯片尺寸决定；PowerPoint 默认宽屏为 1920 × 1080。
