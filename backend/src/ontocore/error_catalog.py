from __future__ import annotations

FAULTS: dict[str, dict] = {
    "OC-1101": {"kind": "business", "http_status": 400, "detail": "请选择供应商"},
    "OC-1102": {"kind": "business", "http_status": 400, "detail": "请选择抽取模型"},
    "OC-1103": {"kind": "business", "http_status": 400, "detail": "请选择嵌入模型"},
    "OC-1104": {"kind": "business", "http_status": 400, "detail": "请选择嵌入供应商"},
    "OC-1105": {
        "kind": "business",
        "http_status": 400,
        "detail": "未找到所选供应商，请先在设置中添加",
    },
    "OC-1106": {
        "kind": "business",
        "http_status": 400,
        "detail": "未找到所选嵌入供应商，请先在设置中添加",
    },
    "OC-1107": {"kind": "business", "http_status": 400, "detail": "当前状态不能启动抽取"},
    "OC-1108": {"kind": "business", "http_status": 400, "detail": "上传文件已丢失，请重新新建作业"},
    "OC-1109": {"kind": "business", "http_status": 400, "detail": "当前状态不能修改作业"},
    "OC-1004": {"kind": "business", "http_status": 404, "detail": "未找到"},
    "OC-2001": {"kind": "business", "http_status": 400, "detail": "不符合对象关系约束"},
    "OC-2002": {"kind": "business", "http_status": 400, "detail": "无法写入对象、属性或关系"},
    "OC-2003": {"kind": "business", "http_status": 409, "detail": "与已有数据冲突"},
    "OC-2004": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该对象"},
    "OC-2005": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该属性"},
    "OC-2006": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该关系"},
    "OC-2007": {
        "kind": "business",
        "http_status": 400,
        "detail": "请选择要对齐的已有对象或关系",
    },
    "OC-3001": {"kind": "business", "http_status": 400, "detail": "无法提取文本"},
    "OC-3101": {"kind": "business", "http_status": 400, "detail": "模型调用失败"},
    "OC-3102": {
        "kind": "business",
        "http_status": 400,
        "detail": "密钥无效或未填写，请检查 API Key",
    },
    "OC-3103": {"kind": "business", "http_status": 400, "detail": "判重失败"},
    "OC-3104": {
        "kind": "business",
        "http_status": 400,
        "detail": "连接超时，请检查 Base URL 或网络",
    },
    "OC-3105": {"kind": "business", "http_status": 400, "detail": "无法连接服务，请检查网络"},
    "OC-3106": {
        "kind": "business",
        "http_status": 400,
        "detail": "接口不存在，请检查 Base URL 和模型名称",
    },
    "OC-3107": {"kind": "business", "http_status": 400, "detail": "请求过于频繁，请稍后再试"},
    "OC-3108": {"kind": "business", "http_status": 400, "detail": "服务已重启，请重新抽取"},
    "OC-4001": {"kind": "system", "http_status": 503, "detail": "图不可用"},
    "OC-5001": {"kind": "business", "http_status": 400, "detail": "请填写 Base URL"},
    "OC-5002": {"kind": "business", "http_status": 400, "detail": "请填写 API Key"},
    "OC-5003": {"kind": "business", "http_status": 400, "detail": "请选择具体模型"},
    "OC-5004": {
        "kind": "business",
        "http_status": 400,
        "detail": "密钥无效或未填写，请检查 API Key",
    },
    "OC-5005": {
        "kind": "business",
        "http_status": 400,
        "detail": "连接超时，请检查 Base URL 或网络",
    },
    "OC-5006": {"kind": "business", "http_status": 400, "detail": "无法连接服务，请检查网络"},
    "OC-5007": {
        "kind": "business",
        "http_status": 400,
        "detail": "接口不存在，请检查 Base URL 和模型名称",
    },
    "OC-5008": {"kind": "business", "http_status": 400, "detail": "请求过于频繁，请稍后再试"},
    "OC-5009": {"kind": "business", "http_status": 400, "detail": "模型调用失败"},
    "OC-9001": {"kind": "system", "http_status": 500, "detail": "服务出错，请查看日志"},
}


def fault_entry(code: str) -> dict:
    return FAULTS[code]


def fault_detail(code: str) -> str:
    return FAULTS[code]["detail"]
