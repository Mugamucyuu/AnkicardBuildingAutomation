"""Editable content checks and model feedback, isolated per concurrent word."""
from contextvars import ContextVar
from functools import wraps, lru_cache
import json
from .settings import RESOURCE_ROOT

_active = ContextVar('prompt_validation', default=None)

@lru_cache(maxsize=1)
def defaults():
    return json.loads((RESOURCE_ROOT / 'prompts/validation.txt').read_text(encoding='utf-8'))

def parse_validation(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'rules', 'messages'}:
        raise ValueError('校验配置必须包含 rules 和 messages。')
    rule = value['rules']
    if not isinstance(rule, dict) or set(rule) != set(defaults()['rules']):
        raise ValueError('校验规则字段不完整。')
    examples = rule['minimum_examples']
    if not isinstance(examples, dict) or set(examples) != {'en','ja','ko'} or any(type(v) is not int or not 1 <= v <= 20 for v in examples.values()):
        raise ValueError('各语言最低例句数必须是 1–20。')
    for key in ('check_language','check_japanese_forms','check_emphasis','check_paragraphs','check_collocations'):
        if type(rule[key]) is not bool: raise ValueError('校验开关必须是布尔值。')
    if type(rule['max_bold_ratio']) not in (int,float) or not 0 < rule['max_bold_ratio'] <= 1:
        raise ValueError('粗体比例必须大于 0 且不超过 1。')
    if type(rule['minimum_collocation_length']) is not int or not 0 <= rule['minimum_collocation_length'] <= 500:
        raise ValueError('搭配解释最低长度无效。')
    messages=value['messages']
    if not isinstance(messages,dict) or set(messages)!=set(defaults()['messages']) or any(not isinstance(v,str) or not v.strip() for v in messages.values()):
        raise ValueError('纠错消息必须保留完整字段和非空文本。')
    return value

def rules(): return (_active.get() or defaults())['rules']

def message(key, **values):
    text=(_active.get() or defaults())['messages'][key]
    for name,value in values.items(): text=text.replace('{'+name+'}',str(value))
    return text

def validation_scope(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        text=kwargs.pop('_validation', None)
        if text is None:return function(*args,**kwargs)
        token=_active.set(parse_validation(text))
        try:return function(*args,**kwargs)
        finally:_active.reset(token)
    return wrapped
