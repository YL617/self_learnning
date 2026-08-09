from __future__ import annotations

BLACKLIST = {
    "代写论文",
    "代写作业",
    "代考",
    "作弊",
    "卖答案",
    "刷单",
    "赌博",
    "色情",
    "毒品",
    "枪支",
}


def validate_text(*texts: str | None) -> None:
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        for word in BLACKLIST:
            if word in lowered:
                raise ValueError(f"内容包含敏感词「{word}」，请修改后重试")
