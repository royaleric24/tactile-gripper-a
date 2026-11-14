# 团队开发

仓库发布后，将下面的 OWNER 替换为仓库所属账号。硬件任务从 feat/hardware-acquisition 起步，软件任务从 feat/dashboard-zh-v1 起步。已有 worktree 直接使用 git worktree list 定位。

```sh
gh repo clone OWNER/tactile-gripper-a
cd tactile-gripper-a
git fetch origin
git worktree add -b hw/sample-check ../gripper-sample origin/feat/hardware-acquisition
cd ../gripper-sample
uv sync --locked
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
```

硬件组另外运行对应工具套件，例如 `PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tools/tactile_acq/tests`。对模拟器、伪终端与网页端口的检查须标注环境。采样和运动均不属于 CI。

```sh
git status --short
git add -- <本次修改的文件>
git diff --cached --check
git commit -m "test(sensor): cover sample ordering"
git push -u origin HEAD
gh pr create --base feat/hardware-acquisition --fill
```

组内合并后，准备集成时，以组分支为 head、main 为 base 开 PR。先用 git log main..HEAD 和 git diff --stat main...HEAD 检查整个差异；若只交付部分功能，基于 main 单独建集成分支，带入经过核验的提交及其依赖。外部贡献者可用 fork 提交 PR。维护者为需要推送组分支的成员授予仓库写权限。

PR 请记录修改前后行为、复现命令、实际结果、当前限制。协议字段/单位、错误处理、引脚或时序、真实控制权限变更由两组审阅，说明旧版本行为与迁移路径。负责人验证后合入 main。建议 main 要求 PR、至少一名审阅者及 offline 测试通过。

真实实验保留 Trial ID、来源、板型/固件/配置、原始帧、命令与 ACK、失败/中断及独立观察。公开只提交获准且脱敏的样例；保留原件，勿强制添加被忽略的日志或备份。
