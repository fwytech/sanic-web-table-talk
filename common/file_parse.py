"""
文件解析工具类
"""

import logging
from io import BytesIO

import pymupdf

from common.minio_util import MinioUtils
import requests
from docx import Document
import pymupdf4llm

logger = logging.getLogger(__name__)


def parse_file(bucket_name, file_key):
    """
    从minio下载文件并读取文件内容
    :param file_key:
    :param bucket_name:
    :return:
    """
    company_file_url = MinioUtils().get_file_url_by_key(bucket_name=bucket_name, object_key=file_key)
    response = requests.get(company_file_url)
    response.raise_for_status()
    content = BytesIO(response.content)

    # 根据文件类型选择不同的方式读取内容
    if file_key.endswith(".docx") or file_key.endswith(".doc"):
        doc = Document(content)
        full_text = "\n".join([para.text for para in doc.paragraphs])
        return full_text
    elif file_key.endswith(".txt"):
        content.seek(0)  # 将指针移回开头
        return content.read().decode("utf-8")
    elif file_key.endswith(".xlsx") or file_key.endswith(".xls"):
        # 此处可以添加 Excel 文件的读取逻辑
        content.seek(0)
        excl_text = read_pdf_text_from_bytes(content.getvalue())
        return excl_text
    elif file_key.endswith(".pptx") or file_key.endswith(".ppt"):
        # 此处可以添加 Excel 文件的读取逻辑
        content.seek(0)
        excl_text = read_pdf_text_from_bytes(content.getvalue())
        return excl_text
    elif file_key.endswith(".pdf"):
        # todo 如果pdf文件中包含图片，则需要使用OCR处理图片 私有化部署mineru支持
        content.seek(0)
        pdf_text = read_pdf_text_from_bytes(content.getvalue())
        return pdf_text
    else:
        raise ValueError("不支持的文件格式")


def read_pdf_text_from_bytes(file_bytes):
    """
    从字节数据中读取文件返回markdown文本 缺点不支持图片解析 如果开启需要走公网服务
    :param file_bytes: bytes, PDF 文件的二进制内容
    :return: str, 提取的文本内容
    """
    try:
        doc = pymupdf.open(stream=file_bytes)
        md_text = pymupdf4llm.to_markdown(doc=doc, ignore_images=True)
        return md_text
    except Exception as e:
        logger.error(f"读取文本时出错: {e}")
        raise e
