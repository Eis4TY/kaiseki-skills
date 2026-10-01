# 可移植交付契约

本文件补齐 research.md 与 menu.md 的执行字段。创作方法以两份参考为准；v3 时序以 menu.md 第六节为准。已统一旧段落的字段和停顿范围，不保留相互竞争的生成格式。

## 文件与版本

- 工具运行时只依赖本 skill 文件夹、Python 3.10+ 标准库和输入文件。可整体复制到 Windows/macOS/Linux；不需要原仓库或任何 Agent 专用接口。
- [菜单 Schema](../schemas/menu-v3.schema.json)、[调研 Schema](../schemas/research.schema.json) 随包分发。`scripts/contract.py` 执行这些 Schema 实际使用的关键词与语义规则，不支持外部 `$ref`，不声称是通用 JSON Schema 引擎。
- 后端随发行版携带同一校验器与 Schema 快照；仓库回归测试比较文件一致性，防止工具与导入端漂移。
- `menu_id` 为 slug-vN，N 从 1 开始；`createdAt` 为 YYYY-MM-DD。菜单 rulesVersion 固定 sound-rules-v3，最终状态 final。
- v3 创作菜单在后端编译成既有 kaiseki.bake/1 播放配置；其混音规则仍标 sound-rules-v2，二者分别表示创作时序版本与播放混音版本。

## 调研到菜单的字段映射

`facts.json`：topic、plan、facts、conflicts、unconfirmed、gaps、sources。sources 为 URL 字符串数组。每个 fact 有 id/text/type/confidence/sourceUrls，可补 note、conflicted。

`stories.json`、`music_pool.json`、`topics.json` 各自只负责 stories、musicPool、topics；脚本不通过任意 merge 相互覆盖。两份非空 Markdown 日志同样必需。

音乐池正式交付（和 finalize 后的菜单）除 songId/title/artist 外，还需要：

| 字段 | 口径 |
|---|---|
| durationSeconds | 已核实 MusicBrainz 参考秒数，必须大于 0；后端用音频实测长度覆盖，绝不裁切 |
| durationSource | MusicBrainz 对应版本/曲目页面 URL |
| platformLinks | apple、netease、qq、youtube、spotify 五个键，值为曲目页 URL 或 null（Web 播放端用于 5 平台跨 App 深度直达跳转） |
| sourceUrls | 各平台已核实的实际单曲/MV 直达 URL 列表，与 platformLinks 互通，Web 端拉起 App 专用 |
| missingPlatformReasons | 对每个 null 平台记录原因；缺失与未查不能混同 |
| lyrics / lyricsFile | 完整纯文本/LRC 或相对调研目录的 UTF-8 文件路径；finalize 内嵌歌词，禁止路径越界 |
| lyricsSource | `{ "url": "出处 URL", "sourceId": "可选来源记录 ID" }` |
| playback | 可选 `{ "provider": "netease或youtube", "providerTrackId": "稳定ID" }`，必须能与 platformLinks 对上 |
| recordingId | 可选版本标识，用于避免不同录音错配 |
| vocalStartEstimateSeconds | 可选 LRC 估计值；不是实测，不直接作为烘焙放行依据 |
| timingNotes | 可选 LRC/版本/下界说明 |

`sourceUrls` 与 `platformLinks` 双向保持一致：只有 `sourceUrls` 时，finalize 可以按域名分类出 `platformLinks`；只有 `platformLinks` 时，finalize 自动将其有效 URL 归集到 `sourceUrls`。同平台多链接时拒绝猜版本，须显式选定。收听端 Web 播放列表优先使用直达 URL 唤起对应平台客户端，若缺少该平台直链则置灰禁用，杜绝模糊搜索回退。不能从公开网页链接推断已获播放授权或平台实时可用。

研究池 S01…连续编号；菜单筛选后保留原 ID（例如 S02、S07），不会改为 S1/S2。musicPool 顺序决定 playlist 的逐位身份映射；实际节目播放顺序由 items 决定。每个入选 songId 仅播放一次。`factPool` 内嵌完整事实快照；各口播 factRefs 只能引用其中 ID，无事实的导赏句用 []。

双源检查合并常见公共后缀和子域名，仅为保守形式检查，不具备完整公共后缀表或来源内容判定能力。对非常见后缀、转载、同一采访转引仍需 Agent 核实；置信度不足按研究纪律降级，不以修改域名凑双源。

所有歌词应在工具和使用权限允许的范围取得；无法取得可用全文时记录缺口，不把节选伪称全文。两行口播引用也是创作上限，并不替代具体工具的内容限制。

## v3 时序门禁

- itemId 全局唯一，music 使用 P1…；voice 使用所属块 B1-a…（支持多字母后缀）。每块可有纯音乐，整期必须有口播。
- 仅首项锚定 timeline.start；其他 start 只能引用此前项的 .start/.end。数组表达依赖顺序，不要求按绝对起播时刻排序。
- offset 最多两位小数；负数仅允许 music 相对此前 music.end，范围 [-3,0)。禁止人声负偏移。实际编译必须拒绝人声互压、非法歌歌重叠、负起点。
- 搭前奏必须有 endConstraint，before 指向目标 Pn.vocalStart，marginSeconds ≥2，onViolation=error。before 可引用下一项音乐（唯一前引）；缺少核验进唱点时编译失败，不能跳过。本后端读取同一菜单版本已归档曲目的 LRC，校验歌词文件哈希并跳过署名行；在首句时间戳前另留 2 秒不确定性余量，再执行 marginSeconds。未提供同版本同步 LRC 时必须改用干说。
- **进唱点本地前置门禁**（check_menu，正式稿）：压歌目标曲必须能按云端同一条回退链推导进唱点——内嵌歌词为带时间戳 LRC 时取首句人声时间戳−2s（跳过署名/纯音乐行，口径同后端 timing），否则须提供 `vocalStartEstimateSeconds`（同样−2s）；两者皆无、或估计值超出参考时长，本地直接拒绝。云端编译对缺进唱点同样拒绝，此门禁把该失败提前到打包前。
- 单段口播正文 ≤2000 字、`menu_id` 必须为 slug-vN：由 Schema 强制，与云端流水线 TTS 单段上限、`-vN` 版本解析同口径。
- **TrackRef 歌单校验**（pack/verify）：对派生 playlist.json 逐曲执行与云端上传一致的机检——provider ∈ {netease, youtube, fixture}、providerTrackId/title/artist 非空、durationSeconds>0、禁止临时播放字段（playbackUrl/url/streamUrl）、musicdl 仅允许 source/identifier。
- **云端编译预演**（check/pack 成功后输出，警告非门禁）：按保守语速（约 4 字/秒另计停顿标记）预估 TTS 时长，复刻云端编译器的锚点排布、两级自愈（口播前移/歌曲顺延）与终检，预演负起点、进唱收声线、人声互压、压歌无约束、非法歌歌重叠。预估≠实测，出现警告须人工复核并预留裕量。
- TTS 时长、歌曲实测时长输入编译器后才解开所有绝对位置；不预设节目总时长。正文停顿计入估算预算，实测超限不得自动加速或压进唱。

## ZIP 与后端能力

ZIP 根目录必需四文件：menu.json、script.json、playlist.json、bundle.json。所有派生内容必须与菜单一致，bundle.json 记录格式、目标能力与 SHA256。可选封面只接受 PNG/JPEG；30MB 是压缩与解压大小共同上限。复验会拒绝重复文件、路径、内容差异和校验和错误。

默认 `--profile kaiseki-v3` 选择可归档的网易云歌曲身份。`--profile portable-v3` 可选网易云或 YouTube，但只适用于已经确认具有相应归档能力的接收端；本仓库导入端会拒绝不支持的身份。Apple/QQ 链接保留用于展示，不自动冒充可归档音源。没有支持的身份则换曲/补源；不退回 fixture。

script.json 是 items 中 voice 的确定性副本，id 与 itemId 相同，不另写时序。playlist.json 是完整歌单快照（含 playlistId/version/createdAt、每项 id/provider/providerTrackId/title/artist/durationSeconds/recordingId）。bundle.json 无需签名服务；校验和用于检测内容不一致，不证明来源真实性。

### 云端上传校验的本地映射

云端 `POST /imports/menu` 在接收时即做全量确定性校验（30MB 上限、ZIP 安全、Schema+机检、bundle/script/playlist 一致性、TrackRef），随后 Worker 编译阶段做时间线终检。本地工具已同口径前置：ZIP 安全与一致性由打包/复验保证，机检增强项见上节。三项云端特有门禁本地无法判定，按下述处置：

| 云端门禁 | 本地处置 |
|---|---|
| 同 menu_id 同版本号已入库 → 409 拒绝 | 重新上传前把 menu_id 升到新 -vN（打包成功输出会提醒） |
| 在线试验模式拒绝含 endConstraint 的压歌菜单 | 压歌菜单只投归档（archive）模式后端（打包输出会提示） |
| 未附 playlist.json 时要求服务端具备搜源能力 | 本契约恒附 playlist.json，不依赖该配置 |

上传被接受不等于发布成功：TTS 合成、音源归档、实测时长编译在云端执行，任一阶段仍可能失败；本地预演警告就是为提前暴露这些风险。

## 异常与验收

命令非零退出即未完成。先读取字段级错误修复源 JSON，重新 finalize/check/pack；不删除事实凑数，不跳过检查。缺少来源或音源不是格式问题，返回调研补齐；无解时清楚交付缺口而不是谎报可导入。

自检使用合成素材、临时目录和结构性反例，不联网、不生成音频、不证明真实节目制作效果。跨环境验收为：独立复制 skill → 自检通过 → 完成真实调研 → finalize → pack → verify；最后导入部署了 v3 支持的电台，观察任务结果，不能把上传接受等同发布完成。
