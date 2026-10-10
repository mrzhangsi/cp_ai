"""Agent 多模态输入处理模块。

支持三种输入类型：
- 图片：模型支持视觉时直接发送 base64；否则用 easyocr OCR 提取文字
- 语音：使用 faster-whisper 转写为文字
- 文档：使用 markitdown 统一解析为纯文本
"""
import asyncio
import base64
import io
import logging
import mimetypes
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage

from src.common.config import settings

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".aac", ".wma"}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".html", ".htm", ".md", ".csv", ".txt", ".xml", ".json", ".rst",
}

_ocr_reader = None


def _get_ocr_reader():
    """延迟初始化 easyocr Reader（全局单例）。"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
    return _ocr_reader


def _get_whisper_model():
    """延迟加载 faster-whisper 模型（全局单例）。"""
    from faster_whisper import WhisperModel
    model_path = settings.agent_whisper_model_path
    return WhisperModel(model_path, device="cpu", compute_type="int8")


def classify_file(filename: str) -> str:
    """根据文件扩展名分类文件类型。

    Args:
        filename: 文件名。

    Returns:
        "image"、"audio"、"document" 或 "unknown"。
    """
    import os
    ext = os.path.splitext(filename)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


def _parse_image_vision(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """图片 → base64 data URL（模型原生视觉支持）。"""
    mime = mimetypes.guess_type(filename)[0] or "image/png"
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }


def _parse_image_ocr(file_bytes: bytes, filename: str) -> str:
    """图片 → OCR 文本提取（模型不支持视觉时）。"""
    from PIL import Image
    img = Image.open(io.BytesIO(file_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    import numpy as np
    img_array = np.array(img)
    reader = _get_ocr_reader()
    results = reader.readtext(img_array, detail=0)
    text = "\n".join(results).strip()
    if not text:
        text = f"[图片 {filename}：未识别到文字内容]"
    else:
        text = f"[图片 {filename} OCR 识别结果]\n{text}"
    return text


async def _parse_audio(file_bytes: bytes, filename: str) -> str:
    """音频 → faster-whisper 转写文本。"""
    import asyncio
    import tempfile
    import os

    ext = os.path.splitext(filename)[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        tmp.write(file_bytes)
        tmp.close()
        model = _get_whisper_model()
        segments, info = await asyncio.to_thread(
            model.transcribe, tmp.name, language=None
        )
        parts = []
        for seg in segments:
            parts.append(seg.text.strip())
        text = "\n".join(parts).strip()
        if not text:
            text = f"[音频 {filename}：未识别到语音内容]"
        else:
            text = f"[音频 {filename} 转写结果]\n{text}"
        return text
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _parse_document(file_bytes: bytes, filename: str) -> str:
    """文档 → markitdown 解析为纯文本。"""
    from markitdown import MarkItDown
    md = MarkItDown()
    import tempfile
    import os

    ext = os.path.splitext(filename)[1] or ".txt"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        tmp.write(file_bytes)
        tmp.close()
        result = md.convert(tmp.name)
        text = result.text_content.strip()
        if not text:
            text = f"[文档 {filename}：内容为空]"
        else:
            text = f"[文档 {filename}]\n{text}"
        return text
    except Exception as e:
        logger.warning("markitdown 解析 %s 失败: %s", filename, e)
        return f"[文档 {filename}：解析失败 - {e}]"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


async def parse_file(
    file_bytes: bytes,
    filename: str,
    vision_supported: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """解析单个文件，返回 (content, attachment_info)。

    Args:
        file_bytes: 文件内容。
        filename: 文件名。
        vision_supported: 模型是否原生支持视觉。

    Returns:
        (content_str, attachment_info) 元组。
        content_str 是 LangChain content 块的文本部分。
        attachment_info 包含附件元数据。
    """
    file_type = classify_file(filename)
    file_size = len(file_bytes)

    info = {
        "name": filename,
        "type": file_type,
        "size": file_size,
    }

    if file_type == "image":
        if vision_supported:
            info["render"] = "vision"
            # 返回特殊标记，实际 image_url 块由调用方构建
            return "", {"blocks": [_parse_image_vision(file_bytes, filename)], **info}
        else:
            text = await asyncio.to_thread(_parse_image_ocr, file_bytes, filename)
            info["render"] = "ocr"
            return text, info

    elif file_type == "audio":
        text = await _parse_audio(file_bytes, filename)
        info["render"] = "transcribe"
        return text, info

    elif file_type == "document":
        text = await asyncio.to_thread(_parse_document, file_bytes, filename)
        info["render"] = "markitdown"
        return text, info

    else:
        info["render"] = "unsupported"
        return f"[不支持的文件类型: {filename}]", info


async def process_files(
    files: List[Tuple[bytes, str]],
    vision_supported: bool = False,
) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    """批量处理文件，返回逐文件结果和附件元数据。

    Args:
        files: [(file_bytes, filename), ...] 列表。
        vision_supported: 模型是否原生支持视觉。

    Returns:
        (file_results, attachments) 元组。
        file_results: [(text, info), ...] 每个文件的解析结果。
        attachments: [info, ...] 附件元数据列表。
    """
    file_results: List[Tuple[str, Dict[str, Any]]] = []
    attachments: List[Dict[str, Any]] = []

    for file_bytes, filename in files:
        text, info = await parse_file(file_bytes, filename, vision_supported)
        file_results.append((text, info))
        attachments.append(info)

    return file_results, attachments


def build_multimodal_content(
    message: str,
    file_results: List[Tuple[str, Dict[str, Any]]],
) -> list:
    """构建 LangChain 多模态消息 content 列表。

    Args:
        message: 用户文本消息。
        file_results: [(text, info), ...] parse_file 返回的结果列表。

    Returns:
        LangChain content 列表。如果没有文件，返回空列表（调用方用纯文本）。
    """
    if not file_results:
        return []

    blocks = []

    # 收集所有文本部分
    text_parts = []
    if message.strip():
        text_parts.append(message.strip())

    for text, info in file_results:
        if text:
            text_parts.append(text)
        # vision 图片块单独添加
        if info.get("blocks"):
            blocks.extend(info["blocks"])

    # 添加合并的文本块
    if text_parts:
        blocks.insert(0, {"type": "text", "text": "\n\n".join(text_parts)})

    return blocks
