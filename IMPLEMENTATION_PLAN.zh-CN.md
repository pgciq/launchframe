# LaunchFrame 实施计划

> **v1 已基本可用（v0.1.34 状态）：** Windows Web GUI、Azure/Voice 配置、Pi/CodeMie/DIAL/ELITEA Provider 接入、Vision/Draft/PPT/音频/字幕审核、FFmpeg 本地发现、Office/PyMuPDF 文档分析、音频/字幕/视频审核、独立构建阶段、单目录访问边界模型、操作取消、Pi 自动启动已经完成。后续计划主要用于完善 Provider 端到端测试、自动化测试、异常恢复和生产化认证。本文较后部分保留早期 Release/Pages 规划，当前项目不自动发布视频。

## 1. 目标

将视频制作能力做成一个独立、资源驱动、国际化、可审核、可发布的项目：

```text
产品文字 / 图片 / 文档 / 表格 / 视频 / 音频
        ↓
自动扫描和分类
        ↓
Azure 登录与 Speech 资源发现
        ↓
Vision 分析
        ↓
LLM 提取要点和生成 Outline
        ↓
生成英文主语言内容
        ↓
生成可配置的第二语言内容
        ↓
人工审核
        ↓
生成 PPT
        ↓
生成语音和字幕
        ↓
生成 PDF 和视频
        ↓
审核视频
        ↓
发布 GitHub Release
```

## 2. 关键设计决策

### 2.1 Pi 的职责

Pi 使用 `pi-codemie`：

- 企业 SSO 登录；
- 动态模型发现；
- LLM 模型选择；
- Vision 模型选择；
- 交互式配置；
- Draft 审核；
- 进度和错误展示；
- 调用视频 MCP。

Pi 不负责视频编码，也不直接读取 Azure Speech Key。

### 2.2 视频 MCP 的职责

`launchframe` MCP 负责：

- 资源扫描；
- Azure MCP 启动和资源发现；
- PPT 生成；
- Azure Speech；
- word-boundary；
- 字幕；
- PDF；
- MP4；
- 中间文件；
- GitHub Release 发布。

### 2.3 Azure MCP 的来源

不复制 Azure MCP 源码，使用主仓库子目录：

```text
vendor/azure-mcp
```

通过配置固定版本：

```json
{
  "azure": {
    "repository": "vendor/azure-mcp",
    "ref": "<stable-commit-or-tag>",
    "checkout_dir": "vendor/azure-mcp"
  }
}
```

生产环境禁止默认跟踪 `main`，应固定 Commit 或 Tag。

## 3. 目标目录结构

```text
launchframe/
├── .pi/
│   ├── settings.json
│   └── mcp.json
├── pi/
│   └── extensions/
│       └── video-workflow.ts
├── video_mcp/
│   ├── config.py
│   ├── resources.py
│   ├── azure_mcp.py
│   ├── vision.py
│   ├── llm.py
│   ├── presentation.py
│   ├── speech.py
│   ├── subtitles.py
│   ├── render.py
│   ├── pipeline.py
│   └── release.py
├── scripts/
├── docs/
├── examples/
├── server.py
├── cli.py
├── pyproject.toml
└── package.json
```

## 4. 运行状态模型

每次运行创建独立 Run：

```text
.video-work/<run-id>/
├── resource-manifest.json
├── azure-session.json          # 不包含 Key
├── vision-analysis.json
├── content-draft.json
├── outline.json
├── narration-primary.json
├── narration-secondary.json
├── primary-manifest.json
├── secondary-manifest.json
├── presentation.pptx
├── presentation.pdf
├── subtitles/
├── audio/
├── video/
└── run-state.json
```

状态：

```text
created
scanning
azure-authenticated
resources-selected
vision-running
content-draft-ready
content-approved
ppt-ready
ppt-approved
speech-running
subtitles-ready
video-ready
video-approved
publishing
published
failed
cancelled
```

## 5. Phase 0 — 修正基础契约

### 任务

- 保留 `video-project.json` 作为 CLI/示例项目的显式配置；Web GUI 允许直接选择资源目录并使用应用内部会话配置；
- 主语言固定英文；
- 第二语言默认为 `zh-CN`；
- 支持 `target_duration_seconds`；
- Azure MCP repository/ref 配置；
- 统一输出文件名和 Manifest；
- 为每次运行增加 `run_id`；
- 明确中间文件和最终文件边界。

### 验收

- 示例项目可被扫描；
- 配置错误能提前发现；
- 选中的产品资源目录自动成为 `VIDEO_PROJECT_ROOT`、访问边界和 Pi 工作目录，路径不会逃逸该边界；
- 所有阶段能够定位到同一个 Run。

## 6. Phase 1 — Azure MCP 集成

### 流程

```text
azure-mcp checkout
    ↓
启动 azure-mcp stdio Server
    ↓
azure_auth_status
    ↓
list_resources
    ↓
选择 Speech Resource
    ↓
ARM listKeys
    ↓
Speech voices/list
```

### 任务

- 从 Git Clone `azure-mcp`；
- 固定 Commit/Tag；
- 自动安装其 Python 依赖；
- 通过 MCP 调用资源发现；
- 只在内存中保存 Speech Key；
- 获取支持的 Voice、Locale、Gender、Style；
- GUI 提供资源和 Voice 选择。

### 安全要求

- Key 不写入项目配置；
- Key 不进入 LLM Prompt；
- Key 不进入日志；
- `listKeys` 需要显式 Azure 权限；
- Azure 变更工具默认不可用。

## 7. Phase 2 — 素材扫描和 Vision

### 任务

- 自动扫描文字、文档、表格、图片、视频和音频；
- 按扩展名和文件名约定归类；
- 对图片计算 Hash；
- Vision 分析只处理新增或变更图片；
- 生成描述、OCR、关键点、Alt Text 和 suggested_slide；
- 人工审核 Vision 结果；
- 根据 `suggested_slide` 放置图片。

### 验收

- 图片识别不依赖图片文件名；
- 图片可正确关联到 PPT 页面；
- 重复图片不重复调用 Vision；
- Vision 失败不会破坏原始素材。

## 8. Phase 3 — Pi CodeMie LLM 集成

### 目标

使用 Pi 当前选择的企业 LLM，不再要求视频项目为每个模型配置 API Key。

### 任务

- `.pi/settings.json` 自动安装 `pi-codemie`；
- Pi SSO 登录；
- 动态显示模型；
- 检查 Vision 能力；
- 通过 Pi 生成结构化 Draft；
- 将 Draft 写入 `.video-work/<run-id>/`；
- 通过 MCP 启动后续构建；
- 保留 OpenAI-compatible API 作为无 Pi 的备用模式。

### 重要边界

```text
Pi Provider → LLM / Vision
视频 MCP → 确定性构建
```

不允许 Python 服务读取 Pi 的 `auth.json`。

## 9. Phase 4 — PPT 生成和审核

### PPT 输入模式

#### 已有 PPTX

```text
验证 PPTX → 直接进入语音/视频阶段
```

#### 初级素材生成 PPTX

```text
文本 / 文档 / 表格 / 图片
    ↓
LLM Outline
    ↓
模板渲染
    ↓
PPTX
```

### 审核功能

- 预览 PPT；
- 查看每页标题和要点；
- 查看图片来源；
- 查看英文和第二语言讲稿；
- 修改单页内容；
- 重新生成当前页；
- Approve / Reject。

## 10. Phase 5 — Speech、字幕和视频

### 任务

- 根据主语言和第二语言 Voice 生成音频；
- 记录 word-boundary；
- 生成单语言和双语字幕；
- 合并多语言音频；
- 生成 PDF；
- 生成主语言 MP4；
- 生成第二语言 MP4；
- 生成双轨 MP4；
- 支持目标时长调整；
- 视频完成后进行元数据检查。

### 审核

- 播放英文视频；
- 播放第二语言视频；
- 检查音频和字幕同步；
- 检查字幕字体和位置；
- 检查全屏；
- Approve / Regenerate。

## 11. Phase 6 — GUI

推荐分两步：

### 第一阶段：Pi TUI Extension

提供命令：

```text
/video-scan
/video-inspect
/video-login-azure
/video-select-model
/video-analyze-images
/video-draft
/video-approve
/video-build
/video-review
/video-publish
```

使用 Pi UI：

```text
select
input
confirm
custom
setStatus
setWidget
```

### 第二阶段：本地 Web/Tauri GUI

```text
GUI
  ↓ WebSocket / HTTP
Workflow Controller
  ├── Pi RPC
  ├── launchframe MCP
  └── azure-mcp MCP
```

GUI 页面：

1. 环境检查；
2. Azure 登录；
3. Speech Resource 选择；
4. 语言和 Voice 选择；
5. LLM/Vision 选择；
6. 产品目录选择；
7. 资源扫描；
8. Draft 审核；
9. PPT 审核；
10. 视频审核；
11. Release 发布。

## 12. Phase 7 — Release 和 Pages

### Presentation Release

```text
release-presentation
```

生成并上传：

- 主语言 MP4；
- 第二语言 MP4；
- 双语双轨 MP4；
- PDF；
- PPTX；
- SRT/WebVTT；
- M4A。

### Pages

- Pages 页面默认显示对应语言视频；
- WebVTT 字幕复制到同源 Pages；
- 页面支持自定义字幕控制；
- Release 版本自动写入页面链接。

## 13. 风险和处理方式

| 风险 | 处理方式 |
|---|---|
| LLM 编造产品信息 | 来源引用、低温度、人工审核 |
| Vision 误识别图片 | confidence、人工审核 |
| Azure Key 泄露 | 内存使用、不返回 LLM、不写文件 |
| 多语言内容数量不一致 | 构建前验证 slide 编号和句子数量 |
| 目标时长不自然 | 目标时长限制和试听审核 |
| Office COM 不稳定 | Linux-native fallback |
| Package Registry 认证失败 | 视频直连、字幕同源 Pages |
| Pages Artifact 过大 | 大视频不复制到 Pages |
| LLM/Voice 成本失控 | 预估、缓存、人工确认和发布门禁 |

## 14. 交付顺序

1. 固定资源 Schema；
2. 完成 Azure MCP 资源发现；
3. 完成 Pi CodeMie SSO 和模型选择；
4. 完成 Vision 审核；
5. 完成 LLM Draft 审核；
6. 完成 PPT 审核；
7. 完成视频审核；
8. 完成 Release 发布；
9. 最后封装 Web/Tauri GUI。
