# 仓库协作说明

- 面向用户与维护者的说明以中文为主；Skill 本体可以按其使用场景采用中英混合内容。
- 当前仅发布 `skills/kaiseki-podcast-producer/`，不要在此仓库加入其他 Skill。
- 版本号只以 `skills/kaiseki-podcast-producer/VERSION` 为准；变更时同步更新 `CHANGELOG.md` 与 Skill frontmatter 中的版本。
- 更新器必须校验下载内容和版本，失败时保留当前可用版本；不得执行未经校验的远程代码。
- 新版本使用 `producer-vX.Y.Z` tag 发布。发布工作流必须校验 tag 与 VERSION 一致、运行自检及可移植性/更新测试、生成 ZIP 和 latest 元数据，并确认 Release 资产存在后再更新 main 的 `latest.json`。
- 常规分支推送只运行 CI，不得触发 Release。
- GitHub Actions 默认仅有 `contents: read`；只有确实创建 Release 并更新 latest 元数据的发布 job 可以拥有 `contents: write`。
- Python 依赖优先使用阿里云 PyPI 镜像；当前质量检查应尽量使用标准库并保持离线可运行。
