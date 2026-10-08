# ark-story-comic

一个可移植的 Codex Skill：把创意、故事、脚本、文章或既有作品转换为分页漫画，并处理故事边界、逐页分镜、人物与道具连续性、无字原画、排字审计和最终交付。

## 能做什么

- 从一个想法发展故事，或忠实改编已有内容；
- 从内置 68 套分镜配方中按页面语义召回并实例化版式；
- 锁定人物、画风、场景、道具和连载状态；
- 先测试高风险页面，再生成整套无字原画；
- 使用可控文字层排字，检查气泡内文字的安全边距、居中和越界；
- 校验页码、尺寸、文件大小、布局数据和 QA 产物。

## 运行条件

- 能识别 Codex Skills 的客户端或 Agent；
- 生成最终漫画需要当前环境具备图像生成能力；
- 定点返修或模型直接排字需要图像编辑能力；
- Python 3；
- Node.js 20.9 或更高版本；
- `sharp`，可通过本目录的 `package.json` 安装。

没有图像生成能力时，本 Skill 仍可交付故事、逐页分镜、资产说明和绘画提示，但不能生成最终漫画成片。

## 安装

### 1. 解压 Skill

把 ZIP 中的 `ark-story-comic` 整个目录放入 Codex 的 Skills 目录：

- macOS / Linux：`~/.codex/skills/ark-story-comic`
- Windows：`%USERPROFILE%\.codex\skills\ark-story-comic`

如果你的 Codex 使用自定义 Skills 目录，以该目录为准。不要只复制 `SKILL.md`；`assets`、`references` 和 `scripts` 都是运行所必需的。

### 2. 安装排字依赖

进入 `ark-story-comic` 目录后执行：

```bash
npm install --omit=dev
```

这会在 Skill 目录内安装对应平台的 `sharp`，不会要求系统级全局安装。

### 3. 验证

macOS / Linux：

```bash
python3 scripts/smoke_test.py
```

Windows：

```powershell
py scripts/smoke_test.py
```

看到 `ARK_STORY_COMIC_SMOKE_PASS` 表示项目骨架、矢量排字、直接排字审计和交付校验链路可运行。之后重新打开 Codex 或开始一个新会话，让客户端重新发现 Skill。

## 最小用法

```text
使用 $ark-story-comic，把下面的内容制作成 3:4 漫画。
页数：12 页。
必须保留：<不可修改的设定>。
允许改写：<允许补充或调整的范围>。
先交付故事说明和逐页分镜供我确认；确认后锁定人物、画风、场景和关键道具，先测试高风险页面；通过后生成全部无字原画，统一排字并完成最终 QA。
故事或想法：<粘贴内容>。
```

完整决策流程见 [`SKILL.md`](SKILL.md)。目录和脚本说明见 [`references/project-schema.md`](references/project-schema.md)。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 scripts/smoke_test.py
```

## 许可证与第三方内容

本项目原创部分使用 MIT License，见 [`LICENSE`](LICENSE)。

内置分镜配方和预览改编自 [yang0/handraw-style](https://github.com/yang0/handraw-style)，其许可要求在再分发和衍生项目中明确保留作者与原仓库署名。完整条款见：

- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
- [`assets/storyboard-library/LICENSE.handraw-style`](assets/storyboard-library/LICENSE.handraw-style)

分镜预览只用于选择构图机制，不授权复用其中的人物、对白、故事或画风。
