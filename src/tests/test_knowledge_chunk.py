from knowledge.pipeline import KnowledgePipeline

pipeline = KnowledgePipeline()

chunks = pipeline.run(
    r"C:\Users\34829\PycharmProjects\ai-model\src\data\灵山胜境_景点结构化数据集.docx"
)

print(f"共生成 {len(chunks)} 个 chunk\n")

for i, chunk in enumerate(chunks):
    print(f"\n--- Chunk {i} ---")
    print(chunk.text)