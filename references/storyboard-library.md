# 分镜配方库

## 已内置的数据

Skill 自带 [`assets/storyboard-library/catalog.json`](../assets/storyboard-library/catalog.json)，包含 68 个 `SB-001`–`SB-068` 漫画分镜配方。每条记录均包含中文／英文构图提示、预览、预览哈希、机器标签、结构化容量、优势、前置条件和风险。预览位于 `assets/storyboard-library/previews/`；安装 Skill 后即可离线检索和查看，不需要下载其他仓库或执行同步。

第三方引用与许可证统一记录在 `assets/storyboard-library/THIRD_PARTY_NOTICES.md` 和 `LICENSE.handraw-style`，不参与运行时检索。

## 配方不是精确几何

`SB` 配方描述的是分镜机制并提供完成图预览，没有给出机器可复用的面板坐标。因此目录明确标记：

- `templateKind: reference-recipe`
- `geometryStatus: reference-only`

不得从预览臆造精确坐标，也不得把预览中的人物、对白或故事内容当成新作品资产。选中配方后，必须根据当前页面节拍实例化格数、矩形／多边形几何、面积层级和阅读顺序；该实例才是生产版分镜，可按 `assets/storyboard-template-catalog.schema.json` 记录。

## 检索

用自然语言检索：

```bash
python3 scripts/search_storyboards.py \
  --catalog assets/storyboard-library/catalog.json \
  --query "双人日常对白，稳定阅读顺序" \
  --top 5 --json
```

已有页面需求 JSON 时：

```bash
python3 scripts/search_storyboards.py \
  --catalog assets/storyboard-library/catalog.json \
  --requirements /absolute/path/to/page-requirements.json \
  --top 5 --json
```

页面有硬约束时，不要只靠自然语言扣分，直接过滤：

```bash
python3 scripts/search_storyboards.py \
  --catalog assets/storyboard-library/catalog.json \
  --query "安静诗意告别，克制留白" \
  --require-tag quiet \
  --exclude-tag impact \
  --forbid-requirement preceding-intensity \
  --top 5 --json
```

`--require-tag`、`--exclude-tag` 和 `--forbid-requirement` 均可重复。还可用 `--dialogue-density`、`--action-continuity`、`--max-reading-complexity` 过滤结构化容量。需求 JSON 对应字段为 `requireTags`、`excludeTags`、`forbidRequirements`、`dialogueDensity`、`actionContinuity`、`maxReadingComplexity`。未知标签或前置条件会直接报错，不静默忽略。

搜索默认不返回零分候选；需要提高门槛时使用 `--min-score` 或 JSON 的 `minScore`。硬过滤先于分数，不得用高分覆盖“不允许屏幕媒介”“没有前置爆发”“必须双线并行”等事实条件。`require-tag` 会缩小召回范围，只把真正不可妥协的要求设为硬条件；“可能更适合安静氛围”这类偏好应留在自然语言查询和最终人工评分中。

脚本分数只用于召回候选，并附带命中证据、优势、容量、前置条件和风险；最终仍按 `storyboard-selection.md` 的结构匹配、文字容量、目标尺寸可读性和连续性评分做选择。搜索结果没有合适候选时使用 `custom`，不要挑一个分数最高但结构不合适的配方。

## 实例化生产版分镜

对每个入选配方记录：

1. `recipeId` 和配方预览；
2. 当前页来源节拍及严格顺序；
3. 实际格数和每格归一化坐标／多边形；
4. 主格、次格、转场格和阅读序号；
5. 人物／物件槽位、对白安全区与目标观看尺寸风险；
6. 与原配方不同之处及原因。

同一个 `SB` 配方可以针对不同故事实例化成不同几何。复用的是构图机制，不是预览中的示例故事。
