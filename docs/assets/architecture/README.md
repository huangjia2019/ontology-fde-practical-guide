# 架构图源文件

[云帆项目架构](yunfan-ontology-agent-system-evolution.mmd)采用 Mermaid 文本格式。图的左侧是十站学习与交付顺序，右侧是本地参考实现的执行路径；前者不会逐站解锁后者。

阅读入口：[架构说明](../../architecture.md) · [十站目录](../../book-map.md)。架构说明已内嵌可在 GitHub 显示的 Mermaid 图，学习和运行项目无需安装绘图工具。

需要编辑或导出图片时，可以把 `.mmd` 文件交给支持 Mermaid 的编辑器。若已安装 Mermaid CLI，也可以在仓库根目录运行：

```bash
mmdc -i docs/assets/architecture/yunfan-ontology-agent-system-evolution.mmd \
  -o artifacts/yunfan-architecture.svg -b white
```

导出文件保存在本地 `artifacts/`。仓库不依赖一份预先生成的 PNG；修改图时，请同时核对源码和[实现范围](../../architecture.md)。图中的来源是本地样例，Agent 判断和裁决是确定性程序，企业连接器、真实身份认证与持久化需要另行集成。
