"""索引构建工具。

传入文档文件夹路径，自动完成文档加载、向量索引构建和持久化存储。
可作为脚本独立运行，也可作为函数被其它模块调用。

使用方式:
    # 命令行
    python -m tools.index_builder --docs ./data --output ./storage

    # 代码调用
    from tools.index_builder import build_and_store_index
    build_and_store_index("./data", "./storage")
"""
import argparse
import sys
import time
from pathlib import Path
from typing import Any, Optional, Union

# 将项目根目录加入 sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def build_and_store_index(
    docs_folder: Union[str, Path],
    storage_folder: Union[str, Path] = "./storage",
    **kwargs: Any,
) -> dict:
    """从文档文件夹构建向量索引并存储到磁盘。

    完整流程：加载文档 → 构建索引 → 持久化存储。

    Args:
        docs_folder: 文档文件夹路径，包含待索引的文件。
        storage_folder: 索引存储目录路径，默认 ./storage。
        **kwargs: 预留扩展参数。

    Returns:
        包含构建结果信息的字典（文档数、存储路径、耗时）。

    Raises:
        FileNotFoundError: 文档文件夹不存在。
        ValueError: 文件夹为空或不包含支持的文件。
        RuntimeError: 索引构建或存储失败。
    """
    from src.RAG.load_data import LoadData
    from src.RAG.embedding_index import build_index_by_documents
    from src.RAG.storage import Storage

    docs_path = Path(docs_folder)
    storage_path = Path(storage_folder)

    if not docs_path.exists():
        raise FileNotFoundError(f"文档文件夹不存在: {docs_path}")
    if not docs_path.is_dir():
        raise ValueError(f"路径不是文件夹: {docs_path}")

    # 1. 加载文档
    print(f"[1/3] 加载文档: {docs_path}")
    load_data = LoadData()
    documents = load_data.load_documents_by_folder(docs_path)
    print(f"      已加载 {len(documents)} 个文档")

    # 2. 构建索引
    print("[2/3] 构建向量索引...")
    t0 = time.time()
    index = build_index_by_documents(documents)
    elapsed = time.time() - t0
    print(f"      索引构建完成，耗时 {elapsed:.1f}s")

    # 3. 存储索引
    print(f"[3/3] 存储索引到: {storage_path}")
    storage = Storage()
    storage.store_by_index(index, storage_path)
    print("      存储完成")

    return {
        "docs_folder": str(docs_path.resolve()),
        "storage_folder": str(storage_path.resolve()),
        "document_count": len(documents),
        "build_time_seconds": round(elapsed, 2),
    }


def main():
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="从文档文件夹构建向量索引并存储",
    )
    parser.add_argument(
        "--docs",
        type=str,
        required=True,
        help="文档文件夹路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./storage",
        help="索引存储目录路径（默认 ./storage）",
    )
    args = parser.parse_args()

    try:
        result = build_and_store_index(args.docs, args.output)
        print(f"\n完成! 文档数={result['document_count']}, "
              f"存储路径={result['storage_folder']}, "
              f"耗时={result['build_time_seconds']}s")
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
