import requests

from bs4 import BeautifulSoup

"""
搜索服务类
"""


async def get_bing_first_href(keyword):
    """
    获取搜索引擎 <div class="b_attribution"> 标签下的第一个 <cite> 标签中的内容   不稳定
    :param keyword:
    :return:
    """
    try:
        # 构建搜索URL
        url = f"https://www.bing.com/search?q={keyword}&mkt=zh-CN"

        # 设置请求头以模拟浏览器访问
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        # 发送GET请求
        response = requests.get(url, headers=headers)

        response.raise_for_status()  # 检查请求是否成功

        # 解析HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # 查找 <div class="b_attribution"> 标签
        b_attribution_div = soup.find("div", class_="b_attribution")
        if b_attribution_div:
            # 查找 <div class="b_attribution"> 下的第一个 <cite> 标签
            first_cite = b_attribution_div.find("cite")
            if first_cite:
                return first_cite.text.strip()

        return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
