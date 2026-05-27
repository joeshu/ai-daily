"""飞书推送平台"""

import os
from typing import Dict

import aiohttp

from .base import PushPlatform


class FeishuPlatform(PushPlatform):
    """飞书 Webhook 推送"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key_name = config.get("apiKeyName", "FEISHU_WEBHOOK_URL")
        self.webhook_url = os.environ.get(self.api_key_name, "")

    def validate_config(self, config: Dict) -> bool:
        """检查飞书配置是否有效"""
        if not config.get("enabled", False):
            return False
        api_key_name = config.get("apiKeyName", "FEISHU_WEBHOOK_URL")
        webhook = os.environ.get(api_key_name, "")
        return bool(webhook)

    async def send(self, content: str, title: str = None, metadata: Dict = None):
        """发送到飞书，优先渲染 metadata 的 lead/highlights"""
        chunks = self._split_content(content, limit=8000)

        async with aiohttp.ClientSession() as session:
            for i, chunk in enumerate(chunks):
                payload = self._build_payload(
                    chunk,
                    title,
                    metadata=metadata,
                    is_first=(i == 0),
                    is_multi=(len(chunks) > 1),
                    index=i + 1,
                    total=len(chunks),
                )
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"飞书推送失败: {resp.status} - {text}")
                    data = await resp.json()
                    if data.get("code") != 0:
                        raise RuntimeError(f"飞书推送失败: {data.get('msg')}")

    def _build_payload(
        self,
        content: str,
        title: str = None,
        metadata: Dict = None,
        is_first: bool = True,
        is_multi: bool = False,
        index: int = 1,
        total: int = 1,
    ) -> Dict:
        """构建飞书卡片消息 payload，首屏突出标题/导语/要点。"""
        metadata = metadata or {}
        lead = (metadata.get("lead") or "").strip()
        highlights = metadata.get("highlights") or []
        display_title = title or "AI Daily"
        if is_multi:
            display_title = f"{display_title}（{index}/{total}）"

        elements = []
        if is_first and lead:
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"> {lead}",
                    "text_align": "left",
                }
            )
        if is_first and highlights:
            bullet_lines = [f"- **速览**：{item}" for item in highlights[:3] if item]
            if bullet_lines:
                elements.append(
                    {
                        "tag": "markdown",
                        "content": "\n".join(bullet_lines),
                        "text_align": "left",
                    }
                )
        elements.append(
            {
                "tag": "markdown",
                "content": content,
                "text_align": "left",
            }
        )

        return {
            "msg_type": "interactive",
            "card": {
                "schema": "2.0",
                "header": {
                    "title": {"content": display_title, "tag": "plain_text"},
                    "template": "blue",
                },
                "body": {
                    "elements": elements,
                },
            },
        }

    def _split_content(self, content: str, limit: int = 8000) -> list:
        """飞书卡片消息 markdown 元素限制 8000 字符"""
        if len(content) <= limit:
            return [content]

        chunks = []
        lines = content.split("\n")
        current = ""

        for line in lines:
            if len(current) + len(line) + 1 > limit:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line

        if current:
            chunks.append(current)

        return chunks
