import json
import logging
import traceback
from urllib.parse import urlparse

import pandas as pd

from common.date_util import DateEncoder

logger = logging.getLogger(__name__)

"""
文件问答服务类
"""


async def read_excel(file_url: str):
    """
    读取excel前两行内容
    :return:
    """
    try:
        # 分割URL以获取文件名部分
        extension = file_url.split("/")[-1].split(".")[-1].split("?")[0]
        if extension in ["xlsx", "xls"]:
            with pd.ExcelFile(file_url) as xls:
                sheets_data = {sheet_name: xls.parse(sheet_name).head(1) for sheet_name in xls.sheet_names}
        elif extension in "csv":
            xls = pd.read_csv(file_url)
            sheets_data = {"sheet1": xls.head(1)}
        else:
            raise ValueError("Unsupported file extension")

        # 遍历每个工作表并转换为所需的列表格式
        sheets_data_list_format = {}
        for sheet_name, df in sheets_data.items():
            sheets_data_list_format[sheet_name] = {"excel表头": df.columns.tolist(), "excel数据": df.values.tolist()}
        return json.dumps(sheets_data_list_format, ensure_ascii=False, cls=DateEncoder)
    except Exception as e:
        traceback.print_exception(e)


async def read_file_columns(file_url: str):
    """
    仅读取并返回文件的第一个工作表或CSV文件的列名称（表头）

    :param file_url: 文件的URL或路径
    :return: 包含列名称的JSON字符串
    """
    try:
        # 确认文件扩展名是否为Excel或CSV文件类型
        parsed = urlparse(file_url)
        path_parts = parsed.path.split(".")
        extension = path_parts[-1] if len(path_parts) > 1 else ""

        if extension not in ["xlsx", "xls", "csv"]:
            raise ValueError("Unsupported file extension")

        if extension in ["xlsx", "xls"]:
            # 只读取Excel文件第一个sheet的表头
            df = pd.read_excel(file_url, sheet_name=0, nrows=0)
        elif extension == "csv":
            # 读取CSV文件的表头
            df = pd.read_csv(file_url, nrows=0)

        # 获取列名称并转换为列表
        columns = df.columns.tolist()

        # 将列名称转为JSON格式返回
        return json.dumps(columns, ensure_ascii=False)

    except Exception as e:
        print(f"An error occurred: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def pyload_build(
    system_prompt,
    user_prompt,
    model,
    stream=False,
    dialog_history=None,
    temperature=None,
    frequency_penalty=None,
    max_tokens=None,
    n=None,
    presence_penalty=None,
    stop=None,
    top_p=None,
):
    """
    构建llm请求参数
    :param system_prompt:
    :param user_prompt:
    :param model:
    :param stream:
    :param dialog_history:
    :param temperature:
    :param frequency_penalty:
    :param max_tokens:
    :param n:
    :param presence_penalty:
    :param stop:
    :param top_p:
    :return:
    """
    msg = []
    if system_prompt:
        msg.append({"role": "system", "content": system_prompt})

    if dialog_history:
        for dialog in dialog_history:
            if dialog.get("role") == "user":
                msg.append({"role": "user", "content": dialog.get("content", "")})
            else:
                msg.append({"role": "assistant", "content": dialog.get("content", "")})
    if user_prompt:
        msg.append({"role": "user", "content": user_prompt})

    payload = {"messages": msg}
    if temperature is not None and temperature >= 0:
        payload.update({"temperature": temperature})
    if top_p is not None and top_p >= 0:
        payload.update({"top_p": top_p})
    if model:
        payload.update({"model": model})
    if stream:
        payload.update({"stream": stream})
    if n:
        payload.update({"n": n})
    if stop:
        payload.update({"stop": stop})
    if max_tokens:
        payload.update({"max_tokens": max_tokens})
    if presence_penalty is not None and presence_penalty >= 0:
        payload.update({"presence_penalty": presence_penalty})
    if frequency_penalty is not None and frequency_penalty >= 0:
        payload.update({"frequency_penalty": frequency_penalty})
    logger.info(f"gpt payload:{json.dumps(payload, ensure_ascii=False)}")
    return payload
