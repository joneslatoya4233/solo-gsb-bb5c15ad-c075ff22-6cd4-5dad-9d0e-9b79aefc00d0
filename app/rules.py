"""内置反应禁配规则引擎。

每条规则是一个对称谓词：接收两个批次（dict），若二者禁配则命中。
规则覆盖实验室废液混配的典型危险情形：酸碱中和放热、氧化-还原、
毒气生成（HCN / H2S / Cl2 / 氯胺）、挥发性蒸气燃爆、爆炸性盐生成等。
"""

# 系统内置的禁配标签（前端据此渲染勾选项）
KNOWN_TAGS = [
    "酸性", "碱性", "氧化剂", "还原剂", "有机溶剂", "氰化物",
    "硫化物", "次氯酸盐", "氨/胺", "重金属", "过氧化物", "叠氮化物", "卤代烃",
]

ACID_PH = 4.5   # pH 不高于此值视为强酸性
BASE_PH = 9.5   # pH 不低于此值视为强碱性

SEVERITY_ORDER = {"低": 0, "中": 1, "高": 2, "极高": 3}


def _tags(b):
    return set(b.get("tags") or [])


def is_acid(b):
    return b["ph"] <= ACID_PH or "酸性" in _tags(b)


def is_base(b):
    return b["ph"] >= BASE_PH or "碱性" in _tags(b)


def is_oxidizer(b):
    return bool(b.get("oxidizing")) or "氧化剂" in _tags(b)


def is_reducer(b):
    return "还原剂" in _tags(b) or "有机溶剂" in _tags(b)


def _has(tag):
    return lambda b: tag in _tags(b)


def _either(pred_a, pred_b):
    """对称组合：a 满足 pred_a 且 b 满足 pred_b，或反之。"""
    return lambda a, b: (pred_a(a) and pred_b(b)) or (pred_b(a) and pred_a(b))


RULES = [
    {
        "id": "R1",
        "name": "酸碱剧烈中和",
        "severity": "高",
        "description": "强酸性与强碱性废液混合剧烈放热，可能沸腾喷溅。",
        "test": _either(is_acid, is_base),
    },
    {
        "id": "R2",
        "name": "氧化剂遇还原性/有机废液",
        "severity": "高",
        "description": "氧化性废液与还原剂或有机溶剂混合，可能起火甚至爆炸。",
        "test": _either(is_oxidizer, is_reducer),
    },
    {
        "id": "R3",
        "name": "氰化物遇酸",
        "severity": "极高",
        "description": "氰化物与酸性废液混合释放剧毒 HCN 气体。",
        "test": _either(_has("氰化物"), is_acid),
    },
    {
        "id": "R4",
        "name": "硫化物遇酸",
        "severity": "极高",
        "description": "硫化物与酸性废液混合释放剧毒 H2S 气体。",
        "test": _either(_has("硫化物"), is_acid),
    },
    {
        "id": "R5",
        "name": "次氯酸盐遇酸",
        "severity": "高",
        "description": "次氯酸盐与酸性废液混合释放氯气（Cl2）。",
        "test": _either(_has("次氯酸盐"), is_acid),
    },
    {
        "id": "R6",
        "name": "次氯酸盐遇氨",
        "severity": "高",
        "description": "次氯酸盐与含氨/胺废液混合生成氯胺类有毒气体。",
        "test": _either(_has("次氯酸盐"), _has("氨/胺")),
    },
    {
        "id": "R7",
        "name": "挥发性废液遇氧化剂",
        "severity": "中",
        "description": "挥发性蒸气与氧化性废液共存，形成可燃爆气氛。",
        "test": _either(lambda b: bool(b.get("volatile")), is_oxidizer),
    },
    {
        "id": "R8",
        "name": "叠氮化物遇重金属",
        "severity": "极高",
        "description": "叠氮化物与重金属离子生成撞击敏感的爆炸性叠氮盐。",
        "test": _either(_has("叠氮化物"), _has("重金属")),
    },
    {
        "id": "R9",
        "name": "过氧化物遇酸/还原剂",
        "severity": "高",
        "description": "过氧化物遇酸或还原剂剧烈分解，可能爆炸。",
        "test": lambda a, b: _either(_has("过氧化物"), is_acid)(a, b)
        or _either(_has("过氧化物"), is_reducer)(a, b),
    },
]


def find_conflicts(batches):
    """对所有批次两两配对检查，返回冲突列表（同一批次对的多条规则合并）。"""
    conflicts = []
    for i in range(len(batches)):
        for j in range(i + 1, len(batches)):
            a, b = batches[i], batches[j]
            hit = [r for r in RULES if r["test"](a, b)]
            if not hit:
                continue
            top = max(hit, key=lambda r: SEVERITY_ORDER[r["severity"]])
            conflicts.append({
                "a_id": a["id"], "a_name": a["name"],
                "b_id": b["id"], "b_name": b["name"],
                "severity": top["severity"],
                "rules": [
                    {"id": r["id"], "name": r["name"],
                     "severity": r["severity"], "description": r["description"]}
                    for r in hit
                ],
            })
    return conflicts
