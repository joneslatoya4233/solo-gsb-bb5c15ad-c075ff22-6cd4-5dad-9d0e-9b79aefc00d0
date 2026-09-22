"""化学废液反应禁配规则引擎。

每个批次由属性推导出若干"类别"（category），规则以类别对的形式定义：
只要两个批次（或同一批次自身）的类别命中规则两端，即判定为禁配冲突。
"""

# 危险等级（数值越大越危险）
LEVELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}

LEVEL_LABELS = {
    "critical": "极危",
    "high": "高危",
    "medium": "中危",
    "low": "低危",
}

# 可选禁配标签（前端多选）
TAG_LABELS = {
    "cyanide": "氰化物",
    "sulfide": "硫化物",
    "hypochlorite": "次氯酸盐",
    "ammonia": "氨/铵盐",
    "organic": "有机溶剂",
    "flammable": "易燃液体",
    "heavy_metal": "重金属",
    "peroxide": "过氧化物",
    "nitrate": "硝酸盐",
    "chlorate": "氯酸盐",
    "halogenated": "卤代有机物",
    "reactive_metal": "活泼金属",
}

# 由理化性质推导出的类别标签
DERIVED_LABELS = {
    "acid": "酸性(pH<4)",
    "base": "碱性(pH>10)",
    "neutral": "近中性",
    "oxidizer": "氧化性",
    "volatile": "挥发性",
}

CATEGORY_LABELS = {**DERIVED_LABELS, **TAG_LABELS}

# 禁配规则表：a/b 为类别，两端无序
RULES = [
    {"id": "R01", "a": "acid", "b": "base", "level": "high",
     "hazard": "中和放热",
     "desc": "酸碱中和剧烈放热，可能导致飞溅、容器超压"},
    {"id": "R02", "a": "acid", "b": "cyanide", "level": "critical",
     "hazard": "剧毒气体",
     "desc": "酸与氰化物反应释放氰化氢(HCN)剧毒气体"},
    {"id": "R03", "a": "acid", "b": "sulfide", "level": "critical",
     "hazard": "剧毒气体",
     "desc": "酸与硫化物反应释放硫化氢(H2S)剧毒气体"},
    {"id": "R04", "a": "acid", "b": "hypochlorite", "level": "critical",
     "hazard": "有毒气体",
     "desc": "酸与次氯酸盐反应释放氯气(Cl2)"},
    {"id": "R05", "a": "hypochlorite", "b": "ammonia", "level": "high",
     "hazard": "有毒气体",
     "desc": "次氯酸盐与氨反应生成氯胺类有毒气体"},
    {"id": "R06", "a": "oxidizer", "b": "organic", "level": "critical",
     "hazard": "火灾爆炸",
     "desc": "氧化剂与有机物接触可能引发火灾甚至爆炸"},
    {"id": "R07", "a": "oxidizer", "b": "flammable", "level": "critical",
     "hazard": "火灾爆炸",
     "desc": "氧化剂与易燃液体混合可剧烈燃烧"},
    {"id": "R08", "a": "oxidizer", "b": "cyanide", "level": "high",
     "hazard": "剧烈氧化",
     "desc": "氧化剂剧烈氧化氰化物，放热并释放气体"},
    {"id": "R09", "a": "oxidizer", "b": "sulfide", "level": "high",
     "hazard": "剧烈氧化",
     "desc": "氧化剂剧烈氧化硫化物，大量放热"},
    {"id": "R10", "a": "oxidizer", "b": "volatile", "level": "high",
     "hazard": "蒸气燃爆",
     "desc": "氧化剂气氛下挥发性蒸气更易燃爆"},
    {"id": "R11", "a": "peroxide", "b": "organic", "level": "critical",
     "hazard": "分解爆炸",
     "desc": "过氧化物与有机物混合可能发生分解爆炸"},
    {"id": "R12", "a": "peroxide", "b": "heavy_metal", "level": "high",
     "hazard": "催化分解",
     "desc": "重金属离子催化过氧化物剧烈分解"},
    {"id": "R13", "a": "nitrate", "b": "acid", "level": "high",
     "hazard": "有毒气体",
     "desc": "硝酸盐遇酸释放氮氧化物(NOx)有毒烟雾"},
    {"id": "R14", "a": "chlorate", "b": "acid", "level": "critical",
     "hazard": "爆炸风险",
     "desc": "氯酸盐遇酸生成不稳定氯酸，有爆炸风险"},
    {"id": "R15", "a": "chlorate", "b": "organic", "level": "critical",
     "hazard": "爆炸风险",
     "desc": "氯酸盐与有机物可形成爆炸性混合物"},
    {"id": "R16", "a": "reactive_metal", "b": "acid", "level": "high",
     "hazard": "易燃气体",
     "desc": "活泼金属与酸反应放出氢气，遇火爆炸"},
    {"id": "R17", "a": "reactive_metal", "b": "base", "level": "medium",
     "hazard": "易燃气体",
     "desc": "两性活泼金属与强碱反应放出氢气"},
    {"id": "R18", "a": "ammonia", "b": "heavy_metal", "level": "low",
     "hazard": "络合放热",
     "desc": "氨与重金属离子络合放热，可能形成敏感络合物"},
    {"id": "R19", "a": "volatile", "b": "flammable", "level": "medium",
     "hazard": "蒸气积聚",
     "desc": "挥发性易燃蒸气在密闭容器内积聚，遇点火源燃爆",
     "self": False},
    {"id": "R20", "a": "halogenated", "b": "reactive_metal", "level": "high",
     "hazard": "剧烈反应",
     "desc": "卤代烃与活泼金属可发生剧烈放热反应"},
]


def categories_of(batch):
    """由批次属性推导类别集合。"""
    cats = set()
    ph = batch["ph"]
    if ph < 4:
        cats.add("acid")
    elif ph > 10:
        cats.add("base")
    else:
        cats.add("neutral")
    if batch.get("oxidizing"):
        cats.add("oxidizer")
    if batch.get("volatile"):
        cats.add("volatile")
    for tag in batch.get("tags") or []:
        if tag in TAG_LABELS:
            cats.add(tag)
    return cats


def _rule_hit(rule, cats_x, cats_y):
    return (rule["a"] in cats_x and rule["b"] in cats_y) or \
           (rule["b"] in cats_x and rule["a"] in cats_y)


def find_pair_conflicts(batch_a, batch_b):
    """返回两个批次之间命中的全部规则（列表）。"""
    cats_a, cats_b = categories_of(batch_a), categories_of(batch_b)
    hits = []
    for rule in RULES:
        if _rule_hit(rule, cats_a, cats_b):
            hits.append(rule)
    return hits


def find_self_conflicts(batch):
    """同一批次自身类别命中规则 → 自反应风险（self=False 的规则跳过）。"""
    cats = categories_of(batch)
    hits = []
    for rule in RULES:
        if rule.get("self", True) and rule["a"] in cats and rule["b"] in cats:
            hits.append(rule)
    return hits
