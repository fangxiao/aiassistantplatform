# {plugin_name}(模板:starter)

由 `agentplatform init <name> --template starter` 生成。

## 改哪里
- `plugin.yaml`:名称/描述/依赖
- `skills/`:领域逻辑(prompt 与参数)——文件内"改这里"注释标注了调整点
- `test/test_cases.yaml`:补充你的冒烟用例

## 下一步
```bash
agentplatform validate .    # 校验(应零错误)
agentplatform test .        # 冒烟
agentplatform deploy .      # 部署(准入:validate+test 强制)
```
