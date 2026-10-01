# 怀石电台 Skills

本仓库发布怀石电台的节目创作 Skill。当前只提供 `kaiseki-podcast-producer`，用于调研主题、策划曲目、撰写口播，并生成可导入怀石电台的菜单包。

## 在 ChatGPT 网页端安装

1. 从 [Releases](https://github.com/Eis4TY/kaiseki-skills/releases/latest) 下载 `kaiseki-podcast-producer-vX.Y.Z.zip`。
2. 在 ChatGPT 网页端打开 **Plugins → Skills → Create → Upload from your computer**，上传 ZIP，并按 ChatGPT 的提示审阅、安装。
3. 安装后在 ChatGPT 网页端新建对话，描述你想制作的节目主题；也可以在消息中明确提到 `kaiseki-podcast-producer`。

这是 ChatGPT 自带的 Skills 安装入口，不是把 ZIP 附加到普通对话。OpenAI 目前说明 Skills 仅向符合条件的 Business、Enterprise、Healthcare 和 Edu 用户开放，且仍受工作区管理员设置和产品可用性影响；个人版等账户若看不到 Skills 或上传入口，当前无法按此方式安装。详见 [ChatGPT 中的技能](https://help.openai.com/zh-hans-cn/articles/20001066)。安装后的 Skill 由 ChatGPT 在工作区中调用；对话中的文件、联网研究和脚本执行能力仍受当前账户、工作区策略及 ChatGPT 会话工具限制。它不能保证访问任意网站、下载任意内容或在用户电脑上永久写入文件。

若当前账户没有 Skills 入口，可尝试在一个新对话中附上完整 ZIP，并提示 ChatGPT 阅读其中的 `SKILL.md` 和配套文件，再按该流程协助创作。普通文件上传并不等于安装 Skill，也不保证 ChatGPT 能解开 ZIP 或运行其中的脚本；若 ZIP 无法读取，可先在本机解压，再附上 `SKILL.md` 和本次任务需要的参考文件。此方式只为当前对话提供材料，不会安装 Skill、跨对话保留或自动更新；对话结束后需要重新提供材料。ChatGPT 文件上传目前说明支持的常见文档类型见[文件类型说明](https://help.openai.com/zh-hans-cn/articles/8983675)。

## 使用与交付

给出主题与偏好后，Skill 会依照流程建立调研材料、核实来源、形成节目结构和曲目安排、撰写口播，运行可用的结构检查，最后生成菜单 JSON 与 ZIP。研究与写作可能需要多轮对话；请在同一对话中继续，避免丢失此前形成的材料。完成后，将菜单包 ZIP 上传到怀石电台「创作」页，按页面提示完成导入。

Skill 会在每次新创作开始时尝试查询最新版本并更新自身文件。自动更新需要当前执行环境能联网，并允许 Skill 脚本写入其文件目录。若 ChatGPT 禁用脚本执行或禁止写入，更新可能失败；此时继续使用当前已安装版本。需要手动更新时，从 Releases 下载最新版 ZIP，再通过 Skills 页面提供的更新/上传流程操作。更新状态以对话内实际执行结果为准。

## 版本与发布

- `skills/kaiseki-podcast-producer/VERSION` 是版本号来源，使用语义化版本。
- 每次发布创建 `producer-vX.Y.Z` tag，且 tag 必须与 `VERSION` 一致。
- 发布工作流会运行 Skill 自检与可移植性/更新测试，构建 ZIP、`latest.json` 和校验文件，创建 GitHub Release；只有确认 Release 资产已上传后，才把新版本写入 `main` 分支的 `latest.json`。
- 推送普通分支提交不会发布版本。发布由 `producer-v*` tag 触发。

## 本地检查

```bash
python3 skills/kaiseki-podcast-producer/scripts/self_test.py
python3 scripts/build_producer_release.py --output-dir dist
```

## 许可

本仓库使用 MIT License，详见 [LICENSE](LICENSE)。
