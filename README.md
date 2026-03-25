# infinite：用“实体图”承载无限上下文（Markdown → Passage/Entity Graph）

这个项目把文件夹里的大量 Markdown（可视作“无限长度上下文”）切分成 passages，并用 LLM 从每个 passage 中抽取核心实体，构建 `Passage -> Entity` 的有向图；再用 PageRank 计算重要性，最后导出 JSON 并用 HTML 页面做可视化浏览。

## 主要能力

- 扫描 Markdown 文件并按 token 长度切片为 passages
- 调用 LLM 为每个 passage 抽取核心实体（人、地点、组织、事件、高频名词短语等）
- 构建有向图：`passage -> entity`（边类型：`mention`）
- PageRank 计算节点重要性（`importance`）
- 用虚拟 `root` 节点把不连通子图串起来（边类型：`related_to`）
- 导出 `entity_graph.json` 并通过 `graph_viewer.html` 交互查看

## 目录结构（关键文件）

- `run.py`：主流程（扫描 md → chunk → 实体抽取 → 建图 → PageRank → 导出 JSON）
- `chunk.py`：按 token 数切片（依赖本地 tokenizer）
- `entity_graph.json`：导出产物（图数据）
- `graph_viewer.html`：前端可视化（从本地选择 JSON 文件加载）
- `count_graph.py`：命令行查看节点/边数量与 Top 节点
- `data/`：默认放 Markdown 数据的目录（存在则优先使用）

## 环境要求

- Python 3.10+（Windows 测试更友好）
- 一个可用的 OpenAI 兼容 Chat Completions 接口 Key（项目默认走 `https://api.siliconflow.cn`）

## 安装依赖

先装基础依赖（仓库自带）：

```bash
pip install -r requirements.txt
```

`run.py` 还用到了 `pydantic`（用于校验模型输出 JSON），建议补装：

```bash
pip install pydantic
```

## 配置环境变量

在项目根目录新建 `.env`（或在系统环境变量里设置）：

```env
OPENAI_API_KEY=你的key
```

说明：

- `run.py` 默认 `BASE_URL = "https://api.siliconflow.cn"`
- `MODEL_NAME = "Qwen/Qwen3-8B"`
- 如需替换模型/网关，直接改 `run.py` 顶部配置区即可

## 准备数据（Markdown）

两种方式任选其一：

- 推荐：把要分析的 Markdown 文件放到 `data/` 目录下（`run.py` 会优先扫描这里）
- 或者：直接放在项目根目录/子目录（`run.py` 会递归扫描）

`run.py` 会默认排除：`产品功能.md`、`README.md`

## 生成实体图（导出 JSON）

在项目根目录运行：

```bash
python run.py
```

成功后会生成（或覆盖）：

- `entity_graph.json`

## 可视化浏览图谱

用浏览器直接打开：

- `graph_viewer.html`

在页面左上角选择刚生成的 `entity_graph.json` 文件即可加载；支持：

- 搜索节点
- 点击节点查看内容（passage 节点会显示原文片段）
- 缩放、拖拽、居中聚焦

## 常见问题

### 1) 运行时提示 tokenizer 路径不存在 / 切片失败

`chunk.py` 里 `DEFAULT_MODEL_PATH` 是一个本地路径（Windows）：

- `C:\Users\z1881\Downloads\graph encoder\qwen3-0.6b`

你需要把它改成你机器上真实存在的 tokenizer 模型目录（或确保该目录存在且可被 `modelscope.AutoTokenizer.from_pretrained()` 加载）。

### 2) LLM 输出不是严格 JSON 导致解析失败

`run.py` 已做了两层兜底：

- 先用 Pydantic 按 schema 校验
- 若模型把 JSON 包在 Markdown 代码块里，会用正则抽取 `{...}` 再校验

如果仍失败，优先检查：模型端是否支持 `response_format={"type":"json_object"}`，或换更稳定的模型。