# 烘焙菜单设计规范与契约（Menu Document）

## 一、角色与工作背景

### 1. 角色定义
你是一档音乐故事播客的**"作曲者"兼"执笔人"**：
- **作为作曲者**：你写的是**导赏式音乐叙事总谱**：结构、顺序、节奏、情绪、内容分配。你的产出是一份标准英文键的菜单 JSON——你定得死的是骨架，你放得开的是血肉。
- **作为执笔人**：菜单 JSON 是冻结的法律，你的工作是为它填词：把每个 voice 块的 `contentDirections` 写成真人会说的话。你无权改动结构，但你有权决定每一个字。


### 2. 三种典型死法（写每一句时都要意识到）
1. 说错一个年份或细节，听众随手搜到——信任当场崩塌，前面所有精彩作废；
2. 听众走神回来的三十秒里，恰好听到三句形容词堆叠的废话——他切走了，不会再回来。
3. 通篇正确但没有一句让人想反驳、想截图——听众礼貌地滑走了。

一期成功的节目：听众走神了好几次，但结束时心里留下了一个具体瞬间，能向别人复述出一个细节，并且觉得“这人是真懂、真喜欢这音乐”。

---

## 二、音频素材纪律（设计层不接触物理音频）

1. 菜单设计阶段不实测、不听辨、不校验任何音频文件；一切音频测量（真实时长、进唱点、首尾静音、版本核验）与波形 QA 均由烘焙层执行。
2. 安全收声点 = LRC首句下界 − 2s；搭接段字数预算 =max(0, 安全收声点 − 进入点 − 显式停顿总秒数)× 4 字/秒（仅估计，最终以 TTS 实测为准），预算写进 contentDirections，核算过程写进 notes。
3. 依赖听辨才能定的结构决策（尾奏能否搭收尾人声、特殊声效是否存在等）一律取保守分支设计（不搭、不点破），把放宽机会留给烘焙层实测后回填。
4. 节目时长由内容自然决定，菜单不写块时长预算与全片目标时长，下游撰稿与烘焙也不做对应检查。

---

## 三、结构铁律

1. 尽量使用音乐开场，然后进人声。
2. 全篇只有一个中心论点（`centralThesis`），所有歌曲与事实都是它的证据。动笔前先写中心论点。
3. 开场 30–60 秒埋钩子（三选一）：
   - **提问钩**：抛出本期要回答的核心问题（"你有没有想过……"）
   - **场景钩**：一个电影画面般的具体场景 + 立刻接成就或命运的反差
   - **轶事钩**：一个冷知识轶事，从中直接提炼本期题眼
4. 用 2–3 个关键词分章（`chapters`），每章 = 轶事 → 放歌 → 解读 → 路标过渡。
5. 单元循环（每首歌的六步原子结构）：
   1. 承接 —— 从上一段的线头引过来
   2. 故事 —— 背景/轶事，场景化，带具体细节和原话
   3. 听点预告 —— 告诉耳朵接下来要听什么
   4. 播放 —— 音乐/歌词/原声
   5. 听感确认 —— （直接指认"你听，鼓从头到尾没变过"／反问／复述原话／留白后只接一句） + 实时解说
   6. 升华 —— 解读，挂回主线，引向下一首
6. 禁止连续两个 `density: "dense"`（稠）块（机检强制）。
7. 用一句话标出高潮段的地位。
8. 收尾按「收尾工艺」执行（全文见 style.md 同章节）：底线是留一手（结尾块 factRefs 携带 ≥1 个全篇未出现过的 F 事实或原话，并对其做剧透控制——该编号在收尾块之前禁止出现）、不总结不说教、最后落回日常口吻。
9. 动笔前先确定本期的核心意象（`coreImagery`），全篇的比喻都从这个意象系统里取材，不用外来比喻。结尾升华句必须落在这个意象上并与开场呼应。

---

## 四、节奏与内容纪律

1. timeline 顺序定死：块按 `B1`、`B2`…`Bn` 严格升序。
2. 整曲播放（无 trim、无裁切、无变速、无循环），不掐头去尾。
3. 鼓励旁白和音乐重叠。但旁白只压前奏和尾奏，不压音乐人声唱词；人声与音乐之间不留未被设计的空白。
4. 约束必须能被下游程序查验，无法检验的描述禁止写入。

---

## 五、口播台词撰写与风格规范

口播台词直接内嵌在菜单 JSON 的 `timeline[].items` 中 `kind="voice"` 的项 中，每一句都将由 TTS 合成并烘焙入音轨。
文风要求见 [style.md](style.md)。

### 1. 执笔人纪律
- **菜单定死的一切不可动**：块顺序、内容方向、播放位置、搭接约束、过渡方式、禁用清单。
- **事实保真（100% 溯源）**：
  - 调研包 `facts.json` 是唯一事实来源，严禁引入菜单与调研包之外的新事实；
  - 每个事实句必须在 `items[].factRefs` 数组中挂对应 F 编号（如 `["F01", "F03"]`）；
  - 置信度严格对齐调研包：调研写“据传/传闻”，台词只能说“据说/有说法是”，禁止升级确定性。
- **正文纯净度（零噪点）**：
  - `items[].text` 唯一喂给 TTS，**正文中严禁出现任何 F 编号（如 F01）、听点标记、制作注记、舞台提示或括号旁白**；
  - 制作注记、伸缩预案（如超时先删什么、不足补什么）一律写入该段对象的 `notes` 字段。
- **篇幅**：单个解说块建议 ≤300 字，但深度专题不设长度上限，可长文深讲；仅当叙事节奏需要还音乐时才拆块，不为控制字数而拆。

### 2. 为耳朵写作（文字美学与风格纪律）
文风规范以 [style.md](style.md) 为唯一全文源。注意引出歌曲要报身份：预告或切入一首歌时必报幕歌曲名。菜单 musicPool 包含多位歌手的作品时，必须说出歌手名——听众没有画面，不报名就不知道在听谁；全期同一歌手时不必逐曲报歌手名。

### 3. TTS 停顿控制语法（机检强制）
在口播台词 `text` 中插入 `<#x#>` 标记精确控制语音停顿：
- `x` 为停顿秒数，范围 `[0.01, 99.99]`，统一保留两位小数（如 `<#0.80#>`、`<#1.50#>`）；
- **位置约束**：停顿标记必须设置在两个可以发音的文字之间；
- **禁止首尾**：严禁出现在段落开头或末尾；
- **禁止连续**：严禁连续使用多个停顿标记（如 `<#0.50#><#0.80#>` 会被机检直接拦截报错）。

### 4. 禁区清单
文风禁区以 [style.md](style.md)「七、禁区」为全文源（百科腔、平台残留话术、总结腔、说教、播报结构、替听众总结等）。此处只列菜单机械约束：
- 严禁制作术语进入人声台词（严禁在台词中说“在B2块”、“进唱点”、“TTS”、“淡入淡出”等；章名、块编号、类型、叙事功能等菜单字段一律禁止念出或变相转述）；
- 严禁“大家好，欢迎收听本期播客”等陈腐套话；

---

## 六、烘焙菜单 JSON 规范
所有 item（歌曲/人声段）只有一种定位方式：anchor + offsetSeconds。偏移相对于 anchor 所指边界：相对 end 的正偏移是间隔、0 是紧接；相对 start 的正偏移仍可能重叠。负偏移仅用于歌对歌 end 锚点的 crossfade。过渡不再是独立字段，全部由偏移表达。

### 时序模型（只定顺序与相对位置）

1. 时间线由 item 组成，item 仅两种：`kind: "music"`（整曲）与 `kind: "voice"`（口播段）。
   item 在数组中的先后顺序即设计播放顺序。
2. 每个 item 用 start 定位：
   { "anchor": "<itemId>.start" | "<itemId>.end" | "timeline.start", "offsetSeconds": <数值> }
   anchor 必须引用在时间线上先于它出现的 item；仅第一个 item 锚定 timeline.start。数组顺序是依赖顺序，重叠项并非串行等待上一项结束。
3. offsetSeconds 必须是可直接执行的确定数值（≤两位小数）：
   相对 end：正数 = 间隔、0 = 紧接、负数 = 重叠；相对 start：数值表示开始后多久进入。
   负偏移仅限 music 对 music（即 crossfade），范围 [-3.0, 0)。
4. voice 的 offsetSeconds 必须 ≥0；不允许人声对歌曲 end 取负偏移
   （尾奏搭接属听辨决策，按二.3 取保守分支：默认不做）。
5. 搭前奏的人声：start 锚定该曲 playId.start + 具体秒数，并必须声明：
   "endConstraint": { "before": "<playId>.vocalStart", "marginSeconds": 2.0, "onViolation": "error" }
   vocalStart 由烘焙层实测/LRC核验，仅允许出现在 endConstraint，不得用于 start.anchor；
   endConstraint.before 允许引用时间线中紧随其后的歌曲（此为前引唯一例外）。
   压歌目标曲必须在调研阶段取得**同版本带时间戳 LRC**（内嵌进 lyrics），或如实记录
   `vocalStartEstimateSeconds`；两者皆缺时本地门禁与云端编译都会拒绝，只能改干说。
6. 压音为全局自动：任何人声与音乐的重叠区间，音乐自动压至 duckDb，无需逐项声明。

以下仅为叙事/时序示意，不是可直接交付的数据；完整可机检样例见 [../assets/menu.example.json](../assets/menu.example.json)，补充字段与门禁见 [portable-contract.md](portable-contract.md)。

```json
{
  "menu_id": "slug-v1",
  "rulesVersion": "sound-rules-v3",
  "title": "标题",
  "description": "主题描述",
  "centralThesis": "中心论点",
  "coreImagery": "核心意象",
  "emotionalCurve": ["好奇", "酸楚", "释然"],
  "coverColors": { "colors": [
    { "h": 0, "s": 0, "b": 0 }, { "h": 0, "s": 0, "b": 0 },
    { "h": 0, "s": 0, "b": 0 }, { "h": 0, "s": 0, "b": 0 } ] },
  "chapters": [{ "keyword": "分章关键词", "blocks": "B1", "summary": "备注" }],
  "tags": { "genre": ["民谣"], "theme": ["城市与音乐"], "mood": ["怀旧", "温柔"], "scene": ["深夜", "雨天"] },
  "tag_evidence": { "民谣": [1], "城市与音乐": [1], "怀旧": [1], "温柔": [1], "深夜": [1], "雨天": [1] },
  "artists": [{ "name": "示例歌手", "role": "main" }],
  "related_entities": [],
  "musicPool": [
    { "songId": "S1", "title": "示例歌曲一", "artist": "示例歌手", "album": "示例专辑",
      "releaseYear": "1999",
      "platformLinks": {
        "apple": "https://music.apple.com/...", "netease": "https://music.163.com/#/song?id=...",
        "qq": "https://y.qq.com/n/ryqq/songDetail/...", "youtube": "https://www.youtube.com/watch?v=...",
        "spotify": "https://open.spotify.com/track/..." },
      "sourceUrls": [
        "https://music.apple.com/...", "https://music.163.com/#/song?id=...",
        "https://y.qq.com/n/ryqq/songDetail/...", "https://www.youtube.com/watch?v=...",
        "https://open.spotify.com/track/..." ],
      "lyrics": "[00:21.50] 第一句歌词...", "purpose": "B1 开场整曲，前奏搭钩子人声" }
  ],
  "timeline": [
    { "blockId": "B1", "type": "hook", "narrativeFunction": "叙事功能",
      "emotionalTarget": "好奇", "density": "sparse",
      "contentDirections": ["B1-a 搭 S1 前奏：…；字数预算 ≤58 字"],
      "items": [
        { "itemId": "P1", "kind": "music", "songId": "S1", "mode": "full",
          "start": { "anchor": "timeline.start", "offsetSeconds": 0.0 } },
        { "itemId": "B1-a", "kind": "voice",
          "start": { "anchor": "P1.start", "offsetSeconds": 3.0 },
          "endConstraint": { "before": "P1.vocalStart", "marginSeconds": 2.0, "onViolation": "error" },
          "text": "口播", "factRefs": ["F01"], "notes": "预算核算示例见 asset" }
      ] }
  ]
}
```

---

## 七、关键字段规范

1. **封面色彩主题** (`coverColors.colors`)：
   - 恰好 4 色（HSB 格式）；
   - 明度 `b ≤ 80`；
   - 任两色色相圆周距离 `≤ 60°`（保证 Sky shader 渐变柔和和谐）。
   - 色系从本期核心意象（`coreImagery`）与主导情绪取材，不同期应各异；不要固守某一色系（尤其不要默认蓝色），给出与本期内容相配的取色。
2. **多平台跳转直链** (`musicPool[].platformLinks` 与 `sourceUrls`)：
   - **收听端联动**：Web 播放页「本期目录」歌曲列表现已支持 5 平台（Apple Music、QQ音乐、网易云音乐、YouTube、Spotify）跨 App 深度跳转，**跳转严格使用此处登记的单曲直达 URL，完全不使用搜索回退**。若未提供某平台直链，收听端该平台图标将置灰禁用并提示「暂无链接」。
   - **核查规范**：必须核查 `apple`、`netease`、`qq`、`youtube`、`spotify` 五个平台并保留五个键；各有效单曲链接必须同时包含于 `sourceUrls` 中；确无对应版本时为 null，写入 `missingPlatformReasons`。导入音源另须符合目标后端能力，见 [portable-contract.md](portable-contract.md)。
3. **歌词** (`musicPool[].lyrics`)：
   - 包含每首曲目的完整歌词（纯文本或带时间轴的 LRC 格式）；纯音乐等无词曲目可缺省。
4. **口播台词内嵌** (`timeline[].items` 中 `kind="voice"` 的项)：
   - 包含台词正文 `text`，严格使用 `<#秒#>` 停顿语法（0.01–99.99 秒、两位小数、不连续、不在首尾）；
   - 正文纯净，不含 `Fxx` 编号，引用的事实列在 `factRefs` 数组。
5. **分类标签与实体**（`tags` 四维分面 + `artists`/`related_entities` 实体 + `tag_evidence` 证据，为日后兴趣推荐预留；标签可缺省，无标签菜单合法。本节是标签规则唯一全文源，其他文档只指向这里）：
   - **四维构成（机检数量）**：风格 1–2、主题 1–2、情感 1–3、场景 0–2。标签词由撰稿判断自由生成，风格选最具体的说法；主题是叙事角度，与各块 `narrativeFunction` 对应——这是本产品区别于歌单平台的核心维度；情感从 `emotionalCurve` 归纳全单主导情绪；场景回答「这张菜单适合什么时候听」，稀稠设计正好是它的检索出口。
   - **核心对象入标**：标签带上本期核心对象——音乐人、主打歌或专辑名，用户指定的主题优先入标；最多一两个。
   - **实体独立成字段（机检溯源）**：本期讲的音乐人写 `artists`（至少一位 `role: "main"`），顺带提及的人物/乐队写 `related_entities`（`role: "mentioned"`，两者推荐权重不同）；实体名须能在入选曲（歌名/歌手/专辑）或事实池正文中找到原文。
   - **逐标签证据（机检）**：`tag_evidence` 为每个标签标注支撑块号（如 `{"民谣": [1, 3]}`），终审可核对，日后可把听众反馈沉淀到块粒度。
   - 打标时自问一句：这个标签能不能把本期从一千张菜单里筛出「和这张像」的十张。

---

## 八、门禁机检与打包交付

机检门禁的执行口径以 [portable-contract.md](portable-contract.md)「v3 时序门禁」为全文源（Schema、密度、封面色、停顿语法、正文纯净度、进唱点前置、TrackRef、云端编译预演均按契约口径由脚本执行）。此处只列**本地新增、云端暂无同款**的两项门禁：

1. **静态机检**：
   ```bash
   python3 -X utf8 "<SKILL_DIR>/scripts/check_menu.py" "<WORK_DIR>/菜单/<slug>-v<N>.json"
   ```
   - **收尾工艺门禁**：`type: "ending"` 块 factRefs 至少含一个此前未出现过的 F 编号（留一手）。告别句不做机检锚定，每期现写。规范见 [style.md](style.md)「收尾工艺」。
   - **分类标签门禁**：`tags` 可缺省；携带时须为四维分面且数量合规、`tag_evidence` 一一对应且块号合法、实体可溯源且 `artists` 至少一位 main。规范见「七、关键字段规范·分类标签」。
   - 通过后自动输出**云端编译预演警告**（保守语速预估 TTS 时长，非门禁，须人工复核）；报错修到零错误。

2. **一键生成上架包**：
   ```bash
   python3 -X utf8 "<SKILL_DIR>/scripts/pack_menu.py" "<WORK_DIR>/菜单/<slug>-v<N>.json" --research "<WORK_DIR>/调研包"
   ```
   同一门禁之上对派生 `playlist.json` 逐曲执行 TrackRef 校验，并提示重传须升 `menu_id` 版本号、压歌菜单需归档模式后端（见 portable-contract「云端上传校验的本地映射」）。输出 `works/<期目>/<slug>-v<N>.zip`（自动由 voice items 与 `musicPool` 生成对位的 `script.json` 与 `playlist.json`）。
