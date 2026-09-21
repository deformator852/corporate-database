class TextChunker:
    def __init__(self, size: int = 1000, overlap: int = 200) -> None:
        if overlap >= size:
            raise ValueError("overlap must be smaller than size")
        self.size = size
        self.overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        if len(normalized) <= self.size:
            return [normalized]
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = end - self.overlap
        return chunks
