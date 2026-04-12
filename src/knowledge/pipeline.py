from knowledge.loader.text_loader import TextLoader
from knowledge.chunker.structured_chunker import StructuredDocxChunker


class KnowledgePipeline:

    def __init__(self):
        self.loader = TextLoader()
        self.chunker = StructuredDocxChunker()

    def run(self, file_path: str):
        document = self.loader.load(file_path)
        return self.chunker.split(document)