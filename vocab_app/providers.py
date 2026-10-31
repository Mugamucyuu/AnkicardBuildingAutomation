"""DeepSeek Chat Completions and OpenAI Responses adapters."""
import os
from .transport import ServiceError, request_json

KEY_VARIABLES = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY"}

class ModelClient:
    enforce_readability = True
    def __init__(self, settings, transport=request_json):
        self.settings = settings
        self.transport = transport

    def generate(self, system, user, *, json_output=False):
        self.settings.require_model()
        provider = self.settings.provider
        variable = KEY_VARIABLES[provider]
        key = os.getenv(variable, "").strip()
        if not key:
            raise ValueError("尚未设置 " + variable + "；请在界面设置中输入密钥，或设置同名环境变量。")
        if provider == "openai":
            url = "https://api.openai.com/v1/responses"
            payload = {
                "model": self.settings.model, "instructions": system, "input": user,
                "max_output_tokens": self.settings.max_output_tokens, "store": False,
            }
            if json_output:
                payload["text"] = {"format": {"type": "json_object"}}
        else:
            url = "https://api.deepseek.com/chat/completions"
            payload = {
                "model": self.settings.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": self.settings.max_output_tokens,
            }
            if self.settings.model in ("deepseek-flash", "deepseek-v4-pro"):
                payload["thinking"] = {"type": "disabled"}
            if json_output:
                payload["response_format"] = {"type": "json_object"}
        data = self.transport(url, payload, headers={"Authorization": "Bearer " + key},
                              timeout=self.settings.timeout)
        if not isinstance(data, dict):
            raise ServiceError("模型响应结构无效；未记录响应正文。")
        try:
            if provider == "openai":
                if data.get("status") != "completed":
                    raise ServiceError("OpenAI 响应未完成；请检查输出预算或内容限制。")
                text = "\n".join(
                    part["text"] for item in data.get("output", [])
                    if item.get("type") == "message"
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
            else:
                choice = data["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ServiceError("DeepSeek 响应未完整结束；请检查输出预算或内容限制。")
                text = choice["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ServiceError("模型未返回可用文本。")
            return text.strip()
        except (KeyError, TypeError, IndexError, AttributeError):
            raise ServiceError("模型响应结构无效；未记录响应正文。") from None
