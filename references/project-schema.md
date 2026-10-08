# 项目目录与工具

## 推荐目录

```text
comic-project/
├── visual-bible.md
├── asset-lock.md
├── references/
├── style-tests/                       # 仅在需要比较画风时使用
└── episodes/
    └── episode-slug/
        ├── story-brief.md
        ├── storyboard.md
        ├── prompts.md
        ├── publish/                   # 仅在需要发布包装时创建
        └── final-v1/
            ├── comic-layout.json
            ├── raw/
            │   └── page-01-art.png
            ├── page-01.png
            └── qa/
                ├── visual-review.md
                └── review-preview-pages/
```

创建新骨架时显式指定当前作品规格：

```bash
python3 scripts/init_comic_project.py /absolute/path/to/project \
  --title "作品名" --episode "episode-01" \
  --pages 6 --width 1200 --height 1600
```

若需要发布包装，再加 `--with-publish`。已有项目增加一集时加 `--episode-only`。脚本拒绝覆盖已有文件。

Skill 已内置 `assets/storyboard-library/catalog.json` 和 68 张配方预览，不必复制进项目。项目选中配方后，把针对当前页面实例化的格数、几何和阅读顺序写入 `storyboard.md`。需要跨项目复用时，再归一化为生产版分镜目录。没有合适配方时允许使用 `custom`。

## `comic-layout.json`

主要字段：

- `width/height`：当前作品的输出尺寸，必须显式提供；
- `preview.width/height`：可选审核预览尺寸；省略时按画布比例生成；
- `delivery.max_mib_per_page`：可选文件上限；
- `signature`：可选签名；
- `expected_balloon_count`、`expected_framed_text_count`：审计数量；
- `pages[].number`：两位页码；
- `pages[].source`：相对最终目录的无字原画；
- `pages[].balloons[]`：`id`、`bubble`、`shape`、`box`、`lines`、字号范围和边距；
- `pages[].framed_text[]`：`id`、`frame`、`box`、`lines`、字号、旋转和对齐。

坐标数组为 `[x, y, width, height]`。[`assets/comic-layout.example.json`](../assets/comic-layout.example.json) 只是结构示例，不是全局尺寸或平台默认值。

## 矢量排字渲染

```bash
node scripts/render_comic.cjs \
  --root /absolute/path/to/final-v1 \
  --layout /absolute/path/to/final-v1/comic-layout.json
```

依赖 `sharp`。若环境无法直接 `require("sharp")`，设置 `COMIC_SHARP_PATH` 指向可用模块。不要把某台机器的缓存绝对路径写进项目。

渲染器生成最终 PNG、审核预览、联系表、气泡与实体框审计；布局失败时非零退出。

## 直接排字审计

直接排字版也要保留 `comic-layout.json` 和无字原画。最终页命名为 `page-XX.png`，然后运行：

```bash
node scripts/audit_direct_lettering.cjs \
  --root /absolute/path/to/direct-lettering-final \
  --source-root /absolute/path/to/source-final \
  --layout /absolute/path/to/direct-lettering-final/comic-layout.json
```

`--source-root` 是布局内 `pages[].source` 的解析根目录；直接排字目录自身含 `raw/` 时可以省略。脚本不会改写成片，只生成审计、联系表和审核预览。

## 校验

```bash
python3 scripts/validate_release.py /absolute/path/to/final-v1
```

校验器默认从 `comic-layout.json` 读取尺寸和可选文件大小限制。命令行 `--width`、`--height`、`--max-mib` 可用于覆盖；`--allow-missing-audits` 只用于原型，最终交付不得使用。

对外分发或修改渲染链路后，运行完整冒烟测试：

```bash
python3 scripts/smoke_test.py
```

该测试使用临时目录创建项目，生成一张本地测试原画，验证两个气泡和一个实体文字的矢量渲染、直接排字差分审计与最终交付校验。它验证生产链路，不调用外部图像生成服务，也不评价故事或画面质量。
